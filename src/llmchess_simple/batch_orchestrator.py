"""
BatchOrchestrator: run many games in lockstep and batch LLM turns.

- Builds N GameRunner instances vs Random or Stockfish opponents.
- Each cycle: finalize ended games, step engine where needed, collect active LLM prompts,
  submit as a batch via either the parallel Responses API (interactive) or the Batches API (offline),
  then feed raw replies back to the corresponding runners.
- prefer_batches/items_per_batch control transport; see README env knobs.
- On completion, dumps per-game artifacts (conversation/history) and returns summaries.
"""
from __future__ import annotations
import logging, math, os
from typing import List, Dict, Optional
from .game import GameRunner, GameConfig
from .engine_opponent import EngineOpponent
from .random_opponent import RandomOpponent
from .llm_client import submit_responses_blocking_all

log = logging.getLogger("batch_orchestrator")

class BatchOrchestrator:
    def __init__(self, model: str, num_games: int, opponent: str = "engine", depth: Optional[int] = 6, movetime_ms: Optional[int] = None, engine: Optional[str] = "Stockfish", base_cfg: Optional[GameConfig] = None, prefer_batches: Optional[bool] = None, items_per_batch: Optional[int] = None, per_game_colors: Optional[List[bool]] = None):
        self.model = model
        self.runners: List[GameRunner] = []
        self._build_games(num_games, opponent, depth, movetime_ms, engine, base_cfg, per_game_colors)
        self._cycle = 0
        # Transport selection for each LLM turn across all active games:
        self.prefer_batches = prefer_batches
        self.items_per_batch = items_per_batch

    def _build_games(self, n: int, opponent: str, depth: Optional[int], movetime_ms: Optional[int], engine: Optional[str], base_cfg: Optional[GameConfig], per_game_colors: Optional[List[bool]] = None):
        for i in range(n):
            if opponent == "random":
                opp = RandomOpponent()
            else:
                opp = EngineOpponent(depth=depth, movetime_ms=movetime_ms, engine_path=None)
                
            # Use a copy of config per game to avoid shared state; shallow copy is fine
            cfg = GameConfig(**vars(base_cfg)) if base_cfg else GameConfig()
            # If caller provided explicit color per game, apply it
            if per_game_colors is not None and i < len(per_game_colors):
                cfg.color = "white" if bool(per_game_colors[i]) else "black"
            # Make output paths unique per game if a base path is provided
            p = cfg.conversation_log_path
            if p:
                try:
                    root, ext = os.path.splitext(p)
                    is_dir_like = os.path.isdir(p) or (ext == "")
                    if is_dir_like:
                        # Create per-game subdir under the base directory
                        subdir = os.path.join(p, f"g{i+1:03d}")
                        os.makedirs(subdir, exist_ok=True)
                        cfg.conversation_log_path = subdir
                    else:
                        # File-like: inject per-game suffix before extension
                        base = os.path.basename(p)
                        name, ext = os.path.splitext(base)
                        new_base = f"{name}_g{i+1:03d}{ext or '.json'}"
                        cfg.conversation_log_path = os.path.join(os.path.dirname(p), new_base)
                except Exception:
                    # If anything goes wrong, leave path as-is but it's per-runner instance anyway
                    pass
            r = GameRunner(model=self.model, opponent=opp, cfg=cfg)
            self.runners.append(r)

    def _active_indices(self) -> List[int]:
        return [i for i, r in enumerate(self.runners) if r.ref.status() == "*"]

    def run(self, max_cycles: Optional[int] = None) -> List[dict]:
        """Run all games to completion (or until max_cycles), batching LLM prompts each cycle.
        Returns: list of per-game summaries.
        """
        while True:
            log.debug("Cycle %d start", self._cycle + 1)
            # Finalize any games that hit termination conditions in prior cycle
            for r in self.runners:
                r.finalize_if_terminated()
            active = self._active_indices()
            if not active:
                break
            self._cycle += 1
            if max_cycles and self._cycle > max_cycles:
                log.info("Stopping after max_cycles=%d", max_cycles)
                break

            # 1) Step engine once where it's engine's turn
            for i in active:
                r = self.runners[i]
                if not r.needs_llm_turn():
                    # Engine to move
                    r.step_opponent()

            # 2) Recompute active, finalize again (in case engine move ended a game), and gather LLM prompts
            for r in self.runners:
                r.finalize_if_terminated()
            active = self._active_indices()
            items: List[Dict] = []
            index_map: Dict[str, int] = {}
            for i in active:
                r = self.runners[i]
                if r.needs_llm_turn():
                    msgs = r.build_llm_messages()
                    cid = f"g{i}_ply{len(r.records)+1}"
                    items.append({"custom_id": cid, "messages": msgs, "model": self.model})
                    index_map[cid] = i

            if not items:
                # Nothing to ask this cycle (e.g., all became terminal after engine move)
                continue

            # 3) Submit one request per active LLM turn this cycle using chosen transport
            log.debug("Cycle %d submitting %d LLM turns (prefer_batches=%s)", self._cycle, len(items), self.prefer_batches)
            outputs = submit_responses_blocking_all(items, prefer_batches=self.prefer_batches, items_per_batch=self.items_per_batch)
            for cid, text in outputs.items():
                i = index_map.get(cid)
                if i is None:
                    continue
                r = self.runners[i]
                r.step_llm_with_raw(text)

            # 4) Finalize after LLM moves (e.g., illegal threshold)
            for r in self.runners:
                r.finalize_if_terminated()

        # Close opponents, dump final artifacts, and collect summaries
        summaries: List[dict] = []
        for r in self.runners:
            try:
                r.finalize_if_terminated()
                # Always write final logs once per game
                r.dump_conversation_json()
                r.dump_structured_history_json()
            except Exception:
                pass
            try:
                r.opp.close()
            except Exception:
                pass
            summaries.append(r.summary())
        return summaries

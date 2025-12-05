"""
Single-game runner and config.

- GameConfig: knobs for max plies, side, prompting mode, and logging.
- GameRunner: orchestrates one game between an LLM and an opponent (LLM or human) using python-chess.
  - Builds prompts (plaintext/FEN) via prompting.py, calls llm_client, normalizes via agent_normalizer,
    validates/salvages with move_validator, and applies moves through Referee.
  - Logs per-turn conversation and structured history JSON for visualization.
  - Exposes step_* helpers for orchestrated runs and summary/metrics at the end.

"""
from __future__ import annotations
import time, logging, statistics, json, threading
import chess
from dataclasses import dataclass, field
import os
from datetime import datetime
from .referee import Referee
from .llm_client import ask_for_best_move_conversation, SYSTEM
from .llm_play import build_prompt_messages_for_board, process_llm_raw_move
from .llm_opponent import LLMOpponent
from .user_opponent import UserOpponent
from .prompting import PromptConfig


@dataclass
class GameConfig:
    max_plies: int = 240
    pgn_tail_plies: int = 20 
    verbose_llm: bool = False
    salvage_with_validator: bool = True  # attempt salvage if agent output illegal
    # Conversation/trace logging
    conversation_log_path: str | None = None  # optional path or directory to dump reconstructed conversation JSON
    conversation_log_every_turn: bool = True  # write conversation and structured history after every ply
    # Side and validation
    # Preferred color configuration: 'white' | 'black'.
    # Back-compat: if older configs set llm_is_white, we derive color from it via a helper in GameRunner.
    color: str = "white"
    llm_is_white: bool = True            # DEPRECATED
    # Optional provider label for logging/routing when using a multi-target Vercel Gateway.
    provider: str | None = None
    provider_options: dict | None = None
    opponent_provider_options: dict | None = None
    # Modular prompting configuration
    prompt_cfg: PromptConfig = field(default_factory=PromptConfig)
    opponent_prompt_cfg: PromptConfig | None = None
    # Console logging of moves as they happen
    game_log: bool = False
    cancel_event: threading.Event | None = None


class GameRunner:
    def __init__(self, model: str, opponent, cfg: GameConfig | None = None):
        self.log = logging.getLogger("GameRunner")
        self.model = model
        self.opp = opponent
        self.cfg = cfg or GameConfig()
        self.provider = getattr(self.cfg, "provider", None)
        self.provider_options = getattr(self.cfg, "provider_options", None)
        self.ref = Referee()
        self.cancel_event = getattr(self.cfg, "cancel_event", None)
        
        # Helper: determine if LLM plays white (prefers cfg.color, falls back to cfg.llm_is_white)
        def _derive_is_white() -> bool:
            c = getattr(self.cfg, "color", None)
            if c is not None:
                return str(c).lower() == "white"
            return bool(getattr(self.cfg, "llm_is_white", True))
        self._is_white = _derive_is_white()
        # Decide headers based on side
        if (self._is_white):
            self.ref.set_headers(white=self.model, black=self._opp_name())
        else:
            self.ref.set_headers(white=self._opp_name(), black=self.model)
        self.records: list[dict] = []  # list of dicts per ply
        self.termination_reason: str | None = None
        self.start_ts = time.time()
        # Prepare conversation log path: treat path as directory or file
        self._prepare_conv_log_path()
        self._global_ply = 0  # counts total plies executed in this runner

    def _cancelled(self) -> bool:
        return bool(self.cancel_event and self.cancel_event.is_set())

    def _llm_is_white(self) -> bool:
        """Return True if the LLM plays White, based on cfg.color (preferred) or legacy cfg.llm_is_white."""
        c = getattr(self.cfg, "color", None)
        if c is not None:
            return str(c).lower() == "white"
        return bool(getattr(self.cfg, "llm_is_white", True))

    def _prepare_conv_log_path(self):
        p = self.cfg.conversation_log_path
        if not p:
            return
        try:
            base, ext = os.path.splitext(p)
            is_dir_like = os.path.isdir(p) or (ext == "")
            if is_dir_like:
                dir_path = p
                os.makedirs(dir_path, exist_ok=True)
                ts = datetime.now().strftime("%Y%m%d-%H%M%S")
                side = "w" if self._llm_is_white() else "b"
                # Include prompting mode in filename for clarity
                pmode = (self.cfg.prompt_cfg.mode or "custom").lower()
                fname = f"conv_{ts}_{pmode}_{side}.json"
                resolved = os.path.join(dir_path, fname)
            else:
                dir_path = os.path.dirname(p)
                if dir_path:
                    os.makedirs(dir_path, exist_ok=True)
                resolved = p
            self.cfg.conversation_log_path = resolved
        except Exception:
            self.log.exception("Failed to prepare conversation log path; disabling conversation logging")
            self.cfg.conversation_log_path = None

    # --------------- Structured history export ---------------
    def export_structured_history(self) -> dict:
        """Return a structured representation of the chess game suitable for visualization.
        Includes headers, result, termination reason, and per-ply entries with SAN, UCI, FENs.
        """
        start_fen = chess.STARTING_FEN
        board = chess.Board()
        moves = []
        ply_idx = 0
        for rec in self.records:
            uci = rec.get("uci")
            if not uci:
                continue
            try:
                mv = chess.Move.from_uci(uci)
            except Exception:
                continue
            san = None
            legal = mv in board.legal_moves
            if legal:
                san = board.san(mv)
                board.push(mv)
            fen_after = board.fen()
            meta = rec.get("meta") or {}
            moves.append({
                "ply": ply_idx + 1,
                "side": "white" if (ply_idx % 2 == 0) else "black",
                "uci": uci,
                "san": san,
                "legal": bool(legal),
                "fen": fen_after,
                "raw": meta.get("raw"),
                "model": meta.get("model") or (self.model if rec.get("actor") == "LLM" else getattr(self.opp, "model", None)),
            })
            ply_idx += 1
        # After building moves list, derive last_illegal_raw from records
        last_illegal_raw = None
        for rec in reversed(self.records):
            if rec.get("actor") == "LLM" and rec.get("ok") is False:
                last_illegal_raw = (rec.get("meta") or {}).get("raw")
                break
        data = {
            "headers": getattr(self.ref, "_headers", {}),
            "initial_fen": start_fen,
            "result": self.ref.status(),
            "termination_reason": self.termination_reason,
            "moves": moves,
            "model": self.model,
            # Explicit player-color mapping for clarity in outputs
            "players": {
                "LLM": "White" if self._llm_is_white() else "Black",
                "OPP": "Black" if self._llm_is_white() else "White",
            },
        }
        opp_prompt_mode = None
        if isinstance(self.opp, LLMOpponent):
            opp_prompt_mode = (self.cfg.opponent_prompt_cfg or self.cfg.prompt_cfg).mode
        data["participants"] = {
            "LLM": {"model": self.model, "prompt_mode": self.cfg.prompt_cfg.mode},
            "OPP": {
                "model": getattr(self.opp, "model", self._opp_name()),
                "prompt_mode": opp_prompt_mode,
                "type": self._opp_type(),
            },
        }
        # Enrich with explicit termination markers
        terminated = data["result"] != "*" or bool(self.termination_reason)
        data["terminated"] = terminated
        data["termination_at_ply"] = len(moves) if terminated else None
        if terminated:
            evt = {
                "event": "termination",
                "ply": len(moves),
                "result": data["result"],
                "reason": self.termination_reason or "normal_game_end",
            }
            if (self.termination_reason == "illegal_llm_move") and last_illegal_raw:
                evt["last_illegal_raw"] = last_illegal_raw
            data["moves"].append(evt)
        return data

    def _structured_history_path(self) -> str | None:
        p = self.cfg.conversation_log_path
        if not p:
            return None
        # If conversation_log_path is a directory, write history.json inside; if file, create a sibling with hist_ prefix
        if os.path.isdir(p) or os.path.splitext(p)[1] == "":
            try:
                os.makedirs(p, exist_ok=True)
            except Exception:
                pass
            return os.path.join(p, "history.json")
        dir_path = os.path.dirname(p)
        base = os.path.basename(p)
        if base.startswith("conv_"):
            base = "hist_" + base[len("conv_"):]
        else:
            name, ext = os.path.splitext(base)
            base = f"{name}_history{ext or '.json'}"
        return os.path.join(dir_path, base)

    def dump_structured_history_json(self):
        path = self._structured_history_path()
        if not path:
            return
        try:
            d = self.export_structured_history()
            dir_path = os.path.dirname(path)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
            self.log.info("Wrote structured history to %s", path)
        except Exception:
            self.log.exception("Failed writing structured history")

    def _opp_name(self) -> str:
        # Prefer explicit label/model for LLM opponents
        if isinstance(self.opp, LLMOpponent):
            return self.opp.label()
        named = getattr(self.opp, "name", None)
        if named:
            return named
        return "Opponent"

    def _opp_type(self) -> str:
        if isinstance(self.opp, LLMOpponent):
            return "llm"
        if isinstance(self.opp, UserOpponent):
            return "human"
        return "other"

    # New helpers for orchestrated runs
    def needs_llm_turn(self) -> bool:
        if self.ref.status() != "*":
            return False
        return (self.ref.board.turn == chess.WHITE and self._llm_is_white()) or (self.ref.board.turn == chess.BLACK and not self._llm_is_white())

    def build_llm_messages(self) -> list[dict]:
        """Build the messages for the next LLM turn according to prompt config."""
        side = "white" if self.ref.board.turn == chess.WHITE else "black"
        # Starting context if LLM is white and no moves yet
        is_starting = self._llm_is_white() and len(self.ref.board.move_stack) == 0
        return build_prompt_messages_for_board(
            board=self.ref.board,
            side=side,
            prompt_cfg=self.cfg.prompt_cfg,
            pgn_tail_plies=self.cfg.pgn_tail_plies,
            is_starting=is_starting,
        )

    def step_llm_with_raw(self, raw: str):
        """Process a provided raw LLM reply as the current move, record it, and handle termination state."""
        fen = self.ref.board.fen()
        # Recover prompts for metadata
        msgs = self.build_llm_messages()
        if self.cfg.conversation_log_path:
            pending_prompt = {
                "system": msgs[0]["content"] if msgs else "",
                "prompt": msgs[-1]["content"] if msgs else "",
                "model": self.model,
            }
            self.dump_conversation_json(pending_prompt=pending_prompt)
        user_prompt_text = msgs[-1]["content"] if msgs else ""
        sys_prompt_text = msgs[0]["content"] if msgs else ""
        ok, uci, san, ms, meta, _ = process_llm_raw_move(
            raw,
            fen,
            apply_uci_fn=self.ref.apply_uci,
            salvage_with_validator=self.cfg.salvage_with_validator,
            verbose_llm=self.cfg.verbose_llm,
            log=self.log,
            meta_extra={
                "mode": "standard",
                "prompt": user_prompt_text,
                "system": sys_prompt_text,
                "prompt_mode": self.cfg.prompt_cfg.mode,
                "prompt_template": getattr(self.cfg.prompt_cfg, "template", None),
            },
            expected_notation=getattr(self.cfg.prompt_cfg, "expected_notation", "san"),
        )
        self.records.append({"actor": "LLM", "uci": uci, "ok": ok, "ms": ms, "san": san, "meta": meta})
        # Console-friendly log of LLM action
        if self.cfg.game_log:
            disp = san or (uci or "(no-move)")
            raw_short = (raw or "").replace("\n", " ")
            if len(raw_short) > 140:
                raw_short = raw_short[:140] + "…"
            self.log.info("[ply %d] LLM: move=%s legal=%s time_ms=%d raw='%s'", self._global_ply+1, disp, ok, ms, raw_short)
        else:
            self.log.debug("Ply %d LLM move %s ok=%s san=%s ms=%d", self._global_ply+1, uci, ok, san, ms)
        if self.cfg.conversation_log_path and self.cfg.conversation_log_every_turn:
            self.dump_conversation_json()
            self.dump_structured_history_json()
        if not ok:
            # first illegal LLM move loses immediately
            self.termination_reason = "illegal_llm_move"
            result = "0-1" if self._llm_is_white() else "1-0"
            self.ref.force_result(result, self.termination_reason)
            self.log.error("Terminating due to illegal LLM move at ply %d", self._global_ply+1)
        self._global_ply += 1
        return ok

    def step_opponent(self):
        ok, uci, san, meta = self._opp_turn()
        ms = None
        if meta:
            ms = meta.get("latency_ms")
        self.records.append({"actor": "OPP", "uci": uci, "ok": ok, "san": san, "ms": ms, "meta": meta})
        if self.cfg.game_log:
            raw_short = ""
            if meta and meta.get("raw"):
                raw_short = (meta["raw"] or "").replace("\n", " ")
                if len(raw_short) > 140:
                    raw_short = raw_short[:140] + "…"
            self.log.info("[ply %d] OPP: move=%s (%s) raw='%s'", self._global_ply+1, san or uci, uci, raw_short)
        else:
            self.log.debug("Ply %d OPP move %s san=%s", self._global_ply+1, uci, san)
        if self.cfg.conversation_log_path and self.cfg.conversation_log_every_turn:
            self.dump_conversation_json()
            self.dump_structured_history_json()
        if not ok:
            self.termination_reason = self.termination_reason or "illegal_opponent_move"
            result = "1-0" if self._llm_is_white() else "0-1"
            self.ref.force_result(result, self.termination_reason)
        self._global_ply += 1
        return ok

    # ---------------- LLM Turn (modular prompt modes) -----------------
    def _llm_turn_standard(self):
        if self._cancelled():
            return False, None, None, None, {}
        messages = self.build_llm_messages()
        if self.cfg.conversation_log_path:
            pending_prompt = {
                "system": messages[0]["content"] if messages else "",
                "prompt": messages[-1]["content"] if messages else "",
                "model": self.model,
            }
            self.dump_conversation_json(pending_prompt=pending_prompt)
        raw = ask_for_best_move_conversation(messages, model=self.model, provider=self.provider, provider_options=self.provider_options)
        fen = self.ref.board.fen()
        user_prompt_text = messages[-1]["content"] if messages else ""
        sys_prompt_text = messages[0]["content"] if messages else ""
        ok, uci, san, agent_ms, meta, _ = process_llm_raw_move(
            raw,
            fen,
            apply_uci_fn=self.ref.apply_uci,
            salvage_with_validator=self.cfg.salvage_with_validator,
            verbose_llm=self.cfg.verbose_llm,
            log=self.log,
            meta_extra={
                "mode": "standard",
                "prompt": user_prompt_text,
                "system": sys_prompt_text,
                "prompt_mode": self.cfg.prompt_cfg.mode,
            },
            expected_notation=getattr(self.cfg.prompt_cfg, "expected_notation", "san"),
        )
        return ok, uci, san, agent_ms, meta

    # ---------------- Opponent Turn -----------------
    def _opp_turn(self):
        if self._cancelled():
            return False, None, None, {}
        if isinstance(self.opp, LLMOpponent):
            ok, uci, san, meta = self.opp.choose_llm(
                board=self.ref.board,
                apply_uci_fn=self.ref.apply_uci,
                pgn_tail_plies=self.cfg.pgn_tail_plies,
                salvage_with_validator=self.cfg.salvage_with_validator,
                verbose_llm=self.cfg.verbose_llm,
                log=self.log,
                prompt_cfg=self.cfg.opponent_prompt_cfg or self.cfg.prompt_cfg,
                provider_options=self.cfg.opponent_provider_options,
                on_prompt=(lambda pending: self.dump_conversation_json(pending_prompt=pending)) if self.cfg.conversation_log_path else None,
            )
            return ok, uci, san, meta
        if isinstance(self.opp, UserOpponent):
            mv = self.opp.choose(self.ref.board)
            san = self.ref.engine_apply(mv)
            return True, mv.uci(), san, {"actor": "human", "raw": mv.uci()}
        mv = self.opp.choose(self.ref.board)
        san = self.ref.engine_apply(mv)
        return True, mv.uci(), san, {}

    # ---------------- Export / Verification -----------------
    def export_conversation(self, pending_prompt: dict | None = None) -> list[dict]:
        """Return a chat-style list of messages representing the interaction.
        Reconstruct from stored prompts and raw replies collected in meta for each actor.
        """
        messages: list[dict] = []
        llm_sys_added = False
        opp_sys_added = False
        for rec in self.records:
            meta = rec.get("meta", {})
            actor = rec.get("actor")
            prompt = meta.get("prompt")
            raw = meta.get("raw") or meta.get("assistant_raw") or ""
            sys_text = meta.get("system")
            model_name = meta.get("model") or (self.model if actor == "LLM" else getattr(self.opp, "model", None))

            if actor == "LLM":
                if not llm_sys_added:
                    messages.append({"role": "system", "content": sys_text or SYSTEM, "model": model_name})
                    llm_sys_added = True
                if prompt:
                    messages.append({"role": "user", "content": prompt})
                if raw:
                    messages.append({"role": "assistant", "content": raw, "model": model_name})
            elif actor == "OPP" and raw:
                if not opp_sys_added and sys_text:
                    messages.append({"role": "system", "content": sys_text, "model": model_name})
                    opp_sys_added = True
                if prompt:
                    messages.append({"role": "user", "content": prompt})
                messages.append({"role": "assistant", "content": raw, "model": model_name})
        if pending_prompt:
            sys_text = pending_prompt.get("system")
            prompt_text = pending_prompt.get("prompt")
            model_name = pending_prompt.get("model") or self.model
            # Only add system once per model
            if sys_text and not any(m.get("role") == "system" and m.get("model") == model_name for m in messages):
                messages.append({"role": "system", "content": sys_text, "model": model_name})
            if prompt_text:
                messages.append({"role": "user", "content": prompt_text, "model": model_name})
        return messages

    def dump_conversation_json(self, pending_prompt: dict | None = None):
        path = self.cfg.conversation_log_path
        if not path:
            return
        try:
            dir_path = os.path.dirname(path)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.export_conversation(pending_prompt=pending_prompt), f, ensure_ascii=False, indent=2)
            self.log.info("Wrote conversation log to %s", path)
        except Exception:
            self.log.exception("Failed writing conversation log")

    def verify_history_result(self) -> dict:
        """Rebuild board from recorded moves to cross-check final status.
        Returns dict with keys: reconstructed_result, referee_result, mismatch(bool)
        """
        board = chess.Board()
        for rec in self.records:
            uci = rec.get("uci")
            if not uci:
                continue
            try:
                mv = chess.Move.from_uci(uci)
            except Exception:
                return {"error": f"bad_uci_in_history:{uci}"}
            if mv in board.legal_moves:
                board.push(mv)
            else:
                return {"error": f"illegal_sequence_at:{uci}"}
        reconstructed = board.result() if board.is_game_over() else "*"
        referee_res = self.ref.status()
        return {"reconstructed_result": reconstructed, "referee_result": referee_res, "mismatch": reconstructed != referee_res}

    # ---------------- Finalization for orchestrated runs -----------------
    def finalize_if_terminated(self):
        """Ensure referee result is set when termination conditions are met in orchestrated mode.
        Also enforce max_plies.
        """
        # If already has a result, ensure termination_reason at least set to normal
        if self.ref.status() != "*":
            if not self.termination_reason:
                self.termination_reason = "normal_game_end"
            self.ref.set_result(self.ref.status(), self.termination_reason)
            return
        # Illegal LLM threshold => LLM loses
        if self.termination_reason == "illegal_llm_move":
            result = "0-1" if self._llm_is_white() else "1-0"
            self.ref.force_result(result, self.termination_reason)
            return
        if self.termination_reason == "illegal_opponent_move":
            result = "1-0" if self._llm_is_white() else "0-1"
            self.ref.force_result(result, self.termination_reason)
            return
        # Max plies
        if len(self.records) >= self.cfg.max_plies:
            self.termination_reason = self.termination_reason or "max_plies_reached"
            self.ref.set_result("1/2-1/2", self.termination_reason)
            return

    def play(self) -> str:
        ply = 0
        while self.ref.status() == "*" and ply < self.cfg.max_plies:
            if self._cancelled():
                self.termination_reason = self.termination_reason or "cancelled"
                break
            llm_turn_now = (self.ref.board.turn == chess.WHITE and self._llm_is_white()) or (self.ref.board.turn == chess.BLACK and not self._llm_is_white())
            if llm_turn_now:
                ok, uci, san, ms, meta = self._llm_turn_standard()
                self.records.append({"actor": "LLM", "uci": uci, "ok": ok, "ms": ms, "san": san, "meta": meta})
                self.log.debug("Ply %d LLM move %s ok=%s san=%s ms=%d", ply+1, uci, ok, san, ms)
                # Save after each LLM move if enabled
                if self.cfg.conversation_log_path and self.cfg.conversation_log_every_turn:
                    self.dump_conversation_json()
                    self.dump_structured_history_json()
                if not ok:
                    if self._cancelled():
                        self.termination_reason = self.termination_reason or "cancelled"
                        break
                    self.termination_reason = "illegal_llm_move"
                    result = "0-1" if self._llm_is_white() else "1-0"
                    self.ref.force_result(result, self.termination_reason)
                    self.log.error("Terminating due to illegal LLM move at ply %d", ply+1)
                    break
            else:
                ok, uci, san, meta = self._opp_turn()
                ms = meta.get("latency_ms") if meta else None
                self.records.append({"actor": "OPP", "uci": uci, "ok": ok, "ms": ms, "san": san, "meta": meta})
                self.log.debug("Ply %d OPP move %s san=%s", ply+1, uci, san)
                if not ok and not self.termination_reason:
                    if self._cancelled():
                        self.termination_reason = self.termination_reason or "cancelled"
                        break
                    self.termination_reason = "illegal_opponent_move"
                    result = "1-0" if self._llm_is_white() else "0-1"
                    self.ref.force_result(result, self.termination_reason)
                    break
                # Save after each OPP move if enabled
                if self.cfg.conversation_log_path and self.cfg.conversation_log_every_turn:
                    self.dump_conversation_json()
                    self.dump_structured_history_json()
            ply += 1
        result = self.ref.status()
        if self.termination_reason == "cancelled":
            result = self.ref.status() if self.ref.status() != "*" else "*"
            self.ref.set_result(result, self.termination_reason)
        elif self.termination_reason == "illegal_llm_move" and result == "*":
            # LLM loses regardless of color
            result = "0-1" if self._llm_is_white() else "1-0"
            self.ref.force_result(result, self.termination_reason)
        elif self.termination_reason == "illegal_opponent_move" and result == "*":
            result = "1-0" if self._llm_is_white() else "0-1"
            self.ref.force_result(result, self.termination_reason)
        elif result != "*":
            self.termination_reason = self.termination_reason or "normal_game_end"
            self.ref.set_result(result, self.termination_reason)
        elif ply >= self.cfg.max_plies and self.termination_reason is None:
            self.termination_reason = "max_plies_reached"
            self.ref.set_result("1/2-1/2", self.termination_reason)  # declare draw by truncation
            result = "1/2-1/2"
        self.log.info("Game finished result=%s reason=%s plies=%d", result, self.termination_reason, ply)
        self.dump_conversation_json()
        self.dump_structured_history_json()
        return result

    # ---------------- Metrics -----------------
    def metrics(self) -> dict:
        llm_moves = [r for r in self.records if r["actor"] == "LLM"]
        opp_moves = [r for r in self.records if r["actor"] == "OPP"]
        latencies = [r.get("ms", 0) for r in llm_moves if r.get("ms") is not None]
        legal = [r for r in llm_moves if r.get("ok")]
        illegal = [r for r in llm_moves if not r.get("ok")]
        opp_illegal = [r for r in opp_moves if not r.get("ok")]
        salvage_success = sum(1 for r in llm_moves if r.get("meta", {}).get("salvage_used"))
        return {
            "plies_total": len(self.records),
            "plies_llm": len(llm_moves),
            "llm_legal_moves": len(legal),
            "llm_illegal_moves": len(illegal),
            "llm_salvage_successes": salvage_success,
            "llm_legal_rate": (len(legal) / len(llm_moves)) if llm_moves else 0.0,
            "latency_ms_avg": statistics.mean(latencies) if latencies else 0,
            "latency_ms_p95": statistics.quantiles(latencies, n=100)[94] if len(latencies) >= 20 else (max(latencies) if latencies else 0),
            "result": self.ref.status(),
            "termination_reason": self.termination_reason,
            "duration_s": round(time.time() - self.start_ts, 2),
            "mode": self.cfg.prompt_cfg.mode,
            "opponent_type": self._opp_type(),
            "opponent_label": self._opp_name(),
            "opponent_model": getattr(self.opp, "model", None) if isinstance(self.opp, LLMOpponent) else None,
            "opponent_illegal_moves": len(opp_illegal),
        }

    def summary(self) -> dict:
        m = self.metrics()
        m["pgn"] = self.ref.pgn()
        m["history_verification"] = self.verify_history_result()
        # Also include a small preview of the structured history path if available
        m["structured_history_path"] = self._structured_history_path()
        return m

from __future__ import annotations
import time, asyncio, logging, statistics, json
import chess
from dataclasses import dataclass, field
from .referee import Referee
from .llm_client import ask_for_best_move_raw, ask_for_best_move_conversation, ask_for_best_move_plain, SYSTEM_CONV, SYSTEM
from .agent_normalizer import normalize_with_agent
from .move_validator import normalize_move
import os
from datetime import datetime
from .prompting import PromptConfig, build_plaintext_messages, build_fen_messages

@dataclass
class GameConfig:
    max_plies: int = 240
    pgn_tail_plies: int = 20
    verbose_llm: bool = False
    salvage_with_validator: bool = True  # attempt salvage if agent output illegal
    fail_on_illegal: bool = True         # terminate immediately on illegal LLM move
    conversation_mode: bool = False      # if True, use chat history (no FEN shown to model)
    conversation_log_path: str | None = None  # optional path to dump reconstructed conversation JSON
    max_illegal_moves: int = 1           # number of illegal LLM moves allowed before termination
    llm_is_white: bool = True            # if False, LLM plays Black
    # New: write conversation log after every turn if a path is provided
    conversation_log_every_turn: bool = False
    # Modular prompting configuration
    prompt_cfg: PromptConfig = field(default_factory=PromptConfig)
    # Console logging of moves as they happen
    game_log: bool = False

class GameRunner:
    def __init__(self, model: str, opponent, cfg: GameConfig | None = None):
        self.log = logging.getLogger("GameRunner")
        self.model = model
        self.opp = opponent
        self.cfg = cfg or GameConfig()
        self.ref = Referee()
        # Decide headers based on side
        if (self.cfg.llm_is_white):
            self.ref.set_headers(white=self.model, black=self._opp_name())
        else:
            self.ref.set_headers(white=self._opp_name(), black=self.model)
        self.records: list[dict] = []  # list of dicts per ply
        self.termination_reason: str | None = None
        self.start_ts = time.time()
        # Conversation history (used only if conversation_mode)
        self.chat_messages: list[dict] = []
        # Prepare conversation log path: treat --conv-log as directory or file
        self._prepare_conv_log_path()
        self._global_ply = 0  # counts total plies executed in this runner

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
                side = "w" if self.cfg.llm_is_white else "b"
                mode = "conv" if self.cfg.conversation_mode else "std"
                fname = f"conv_{ts}_{mode}_{side}.json"
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
            fen_before = board.fen()
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
            moves.append({
                "ply": ply_idx + 1,
                "side": "white" if (ply_idx % 2 == 0) else "black",
                "uci": uci,
                "san": san,
                "legal": bool(legal),
                "fen_before": fen_before,
                "fen_after": fen_after,
                "actor": rec.get("actor"),
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
            "start_fen": start_fen,
            "result": self.ref.status(),
            "termination_reason": self.termination_reason,
            "moves": moves,
            "model": self.model,
            "llm_is_white": self.cfg.llm_is_white,
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
        # Prefer explicit name attribute if provided (e.g., RandomOpponent)
        if hasattr(self.opp, 'name'):
            return getattr(self.opp, 'name')
        label = "Stockfish"
        depth = getattr(self.opp, "depth", None)
        mt = getattr(self.opp, "movetime_ms", None)
        if mt:
            return f"{label}({mt}ms)"
        if depth:
            return f"{label}(d{depth})"
        return label

    def _pgn_tail(self) -> str:
        # Produce a clean SAN move list without headers.
        max_plies = self.cfg.pgn_tail_plies
        if max_plies <= 0:
            return ""
        board = chess.Board()  # start pos
        sans: list[str] = []
        for idx, mv in enumerate(self.ref.board.move_stack):
            san = board.san(mv)
            board.push(mv)
            move_no = (idx // 2) + 1
            if idx % 2 == 0:  # white move, include move number
                sans.append(f"{move_no}. {san}")
            else:
                sans.append(san)
        tail = sans[-max_plies:]
        return " ".join(tail)

    def _annotated_history(self) -> str:
        """Return history as one move per line: 'White Pawn e4' / 'Black Knight f6'. No numbering."""
        lines: list[str] = []
        board = chess.Board()
        for mv in self.ref.board.move_stack:
            piece = board.piece_at(mv.from_square)
            san = board.san(mv)
            color = "White" if board.turn == chess.WHITE else "Black"
            piece_name = chess.piece_name(piece.piece_type).capitalize() if piece else "Piece"
            lines.append(f"{color} {piece_name} {san}")
            board.push(mv)
        return "\n".join(lines)

    # New helpers for batched orchestration
    def needs_llm_turn(self) -> bool:
        if self.ref.status() != "*":
            return False
        return (self.ref.board.turn == chess.WHITE and self.cfg.llm_is_white) or (self.ref.board.turn == chess.BLACK and not self.cfg.llm_is_white)

    def build_llm_messages(self) -> list[dict]:
        """Build the messages for the next LLM turn according to prompt config (standard mode only)."""
        side = "white" if self.ref.board.turn == chess.WHITE else "black"
        history = self._annotated_history()
        is_starting = self.cfg.llm_is_white and len(self.ref.board.move_stack) == 0
        if self.cfg.prompt_cfg.mode == "fen":
            fen = self.ref.board.fen()
            pgn_tail = self._pgn_tail()
            return build_fen_messages(fen=fen, pgn_tail=pgn_tail, side=side, is_starting=is_starting, cfg=self.cfg.prompt_cfg)
        else:
            return build_plaintext_messages(side=side, history_text=history, is_starting=is_starting, cfg=self.cfg.prompt_cfg)

    def step_llm_with_raw(self, raw: str):
        """Process a provided raw LLM reply as the current move, record it, and handle termination state."""
        fen = self.ref.board.fen()
        # Recover prompts for metadata
        msgs = self.build_llm_messages()
        user_prompt_text = msgs[-1]["content"] if msgs else ""
        sys_prompt_text = msgs[0]["content"] if msgs else ""
        ok, uci, san, ms, meta, _ = self._process_llm_raw(raw, fen, meta_extra={"mode": "standard", "prompt": user_prompt_text, "system": sys_prompt_text, "prompt_mode": self.cfg.prompt_cfg.mode})
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
            # increment illegal counter and possibly terminate
            # Note: keep same semantics as play()
            # We track via a local counter derived from recorded moves
            illegal_llm = sum(1 for r in self.records if r.get("actor") == "LLM" and not r.get("ok"))
            if illegal_llm >= self.cfg.max_illegal_moves and self.cfg.fail_on_illegal:
                self.termination_reason = "illegal_llm_move"
                self.log.error("Terminating due to illegal LLM move at ply %d (count=%d)", self._global_ply+1, illegal_llm)
        self._global_ply += 1
        return ok

    def step_opponent(self):
        ok, uci, san = self._opp_turn()
        self.records.append({"actor": "OPP", "uci": uci, "ok": ok, "san": san})
        if self.cfg.game_log:
            self.log.info("[ply %d] OPP: move=%s (%s)", self._global_ply+1, san or uci, uci)
        else:
            self.log.debug("Ply %d OPP move %s san=%s", self._global_ply+1, uci, san)
        if self.cfg.conversation_log_path and self.cfg.conversation_log_every_turn:
            self.dump_conversation_json()
            self.dump_structured_history_json()
        self._global_ply += 1
        return ok

    # ---------------- LLM Turn (FEN/PGN mode) -----------------
    def _llm_turn_standard(self):
        messages = self.build_llm_messages()
        raw = ask_for_best_move_conversation(messages, model=self.model)
        fen = self.ref.board.fen()
        user_prompt_text = messages[-1]["content"] if messages else ""
        sys_prompt_text = messages[0]["content"] if messages else ""
        ok, uci, san, agent_ms, meta, _ = self._process_llm_raw(
            raw, fen, meta_extra={"mode": "standard", "prompt": user_prompt_text, "system": sys_prompt_text, "prompt_mode": self.cfg.prompt_cfg.mode}
        )
        return ok, uci, san, agent_ms, meta

    # ---------------- LLM Turn (Conversation mode) -----------------
    def _init_conversation_if_needed(self):
        if not self.chat_messages:
            self.chat_messages.append({"role": "system", "content": SYSTEM_CONV})
            self.chat_messages.append({"role": "user", "content": "Game start. You are White. Make your first move. Respond ONLY with the move in SAN."})

    def _conversation_user_prompt(self):
        # Called when it's white (LLM) turn, after opponent possibly moved.
        if len(self.chat_messages) <= 2:  # first move already has prompt
            return
        # Last opponent move SAN is last record with actor OPP
        opp_moves = [r for r in self.records if r.get("actor") == "OPP"]
        if opp_moves:
            last_san = opp_moves[-1].get("san")
            self.chat_messages.append({"role": "user", "content": f"Black plays {last_san}. Your move."})
        else:
            # Should not happen except first move handled earlier
            self.chat_messages.append({"role": "user", "content": "Your move."})

    def _format_history_lines(self) -> str:
        lines = []
        move_pairs: dict[int, dict[str, str]] = {}
        ply_index = 0
        board = chess.Board()
        for rec in self.records:
            if not rec.get("san"):
                continue
            mv_color = "white" if ply_index % 2 == 0 else "black"
            move_no = (ply_index // 2) + 1
            move_pairs.setdefault(move_no, {})[mv_color] = rec["san"]
            ply_index += 1
        for num in sorted(move_pairs.keys()):
            pair = move_pairs[num]
            w = pair.get("white")
            b = pair.get("black")
            if w and b:
                lines.append(f"{num}. White: {w} Black: {b}")
            elif w:
                lines.append(f"{num}. White: {w}")
        return "\n".join(lines)

    def _ensure_conversation_initialized(self):
        if self.chat_messages:
            return
        # System prompt generic
        side = "White" if self.cfg.llm_is_white else "Black"
        self.chat_messages.append({"role": "system", "content": "You are playing a serious chess game. Provide only the best legal move each turn in SAN (short algebraic). No commentary."})
        if self.cfg.llm_is_white:
            self.chat_messages.append({"role": "user", "content": "You play White. Provide only your first move in SAN."})
        # If LLM is black we delay first user message until after white's first move

    def _build_turn_prompt(self) -> str:
        side = "White" if self.cfg.llm_is_white else "Black"
        moving_side = "White" if self.ref.board.turn == chess.WHITE else "Black"
        history = self._format_history_lines()
        base = "You are playing a chess game. What's your next move?"
        if history:
            base += f"\nMoves so far:\n{history}"
        base += f"\n{moving_side} to move. Provide only the move in SAN."  # always ends with instruction
        return base

    def _llm_turn_conversation(self):
        self._ensure_conversation_initialized()
        # If LLM is black and no user prompt yet (after white moved)
        if not self.cfg.llm_is_white and len(self.chat_messages) == 1:
            # Add first prompt after opponent's initial white move exists
            history = self._format_history_lines()
            self.chat_messages.append({"role": "user", "content": f"You play Black. Game has started.\nMoves so far:\n{history}\nProvide only your first move in SAN."})
        else:
            # Regular subsequent prompt
            self.chat_messages.append({"role": "user", "content": self._build_turn_prompt()})
        raw = ask_for_best_move_conversation(self.chat_messages, model=self.model)
        fen = self.ref.board.fen()
        ok, uci, san, agent_ms, meta, salvage_used = self._process_llm_raw(raw, fen, meta_extra={"mode": "conversation"})
        assistant_reply = san if san else (raw.split()[0] if raw else "(no-move)")
        self.chat_messages.append({"role": "assistant", "content": assistant_reply})
        return ok, uci, san, agent_ms, meta

    # ---------------- Shared processing -----------------
    def _process_llm_raw(self, raw: str, fen: str, meta_extra: dict | None = None):
        t0 = time.time()
        # Extract candidate move string (agent just extracts, independent of board)
        try:
            candidate = asyncio.run(normalize_with_agent(raw))  # now returns raw candidate token
        except Exception:
            candidate = ""
        agent_ms = int((time.time() - t0) * 1000)

        salvage_used = False
        validator_info = None

        def _apply_and_record(candidate_uci: str):
            ok, san = self.ref.apply_uci(candidate_uci)
            return ok, san

        ok = False
        san = None

        uci = ""
        if candidate:
            # Validate candidate via move validator
            validator_info = normalize_move(candidate, fen)
            if validator_info.get("ok"):
                uci = validator_info["uci"]
                ok, san = _apply_and_record(uci)
            else:
                self.log.debug("Candidate not legal: %s", validator_info.get("reason"))
        else:
            self.log.warning("No candidate extracted from LLM reply")

        if (not ok) and self.cfg.salvage_with_validator:
            # Try salvage on full raw reply
            v2 = normalize_move(raw, fen)
            if v2.get("ok"):
                salvage_used = True
                uci = v2["uci"]
                ok, san = _apply_and_record(uci)
                if ok:
                    self.log.info("Salvaged move from raw reply: %s", uci)
            else:
                validator_info = v2

        if self.cfg.verbose_llm:
            self.log.info("LLM raw='%s' agent_uci='%s' ok=%s", raw, uci, ok)

    # Termination decision handled in play() based on counters

        meta = {
            "raw": raw,
            "salvage_used": salvage_used,
            "validator": validator_info,
        }
        if meta_extra:
            meta.update(meta_extra)
        return ok, uci, san, agent_ms, meta, salvage_used

    # ---------------- Opponent Turn -----------------
    def _opp_turn(self):
        mv = self.opp.choose(self.ref.board)
        san = self.ref.engine_apply(mv)
        return True, mv.uci(), san

    # ---------------- Export / Verification -----------------
    def export_conversation(self) -> list[dict]:
        """Return a chat-style list of messages representing the interaction.
        Standard mode: reconstruct from stored prompts and raw replies.
        Conversation mode: return the live chat history.
        """
        if self.cfg.conversation_mode:
            return list(self.chat_messages)
        # Prefer exact system prompt captured in meta on first LLM turn
        sys_text = None
        for rec in self.records:
            if rec.get("actor") == "LLM":
                sys_text = rec.get("meta", {}).get("system")
                if sys_text:
                    break
        messages: list[dict] = [{"role": "system", "content": sys_text or SYSTEM}]
        for rec in self.records:
            if rec.get("actor") != "LLM":
                continue
            meta = rec.get("meta", {})
            prompt = meta.get("prompt")
            raw = meta.get("raw") or meta.get("assistant_raw") or ""
            if prompt:
                messages.append({"role": "user", "content": prompt})
            messages.append({"role": "assistant", "content": raw})
        return messages

    def dump_conversation_json(self):
        path = self.cfg.conversation_log_path
        if not path:
            return
        try:
            dir_path = os.path.dirname(path)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.export_conversation(), f, ensure_ascii=False, indent=2)
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

    # ---------------- Finalization for batched orchestrator -----------------
    def finalize_if_terminated(self):
        """Ensure referee result is set when termination conditions are met in batched mode.
        Also enforce max_plies.
        """
        # If already has a result, ensure termination_reason at least set to normal
        if self.ref.status() != "*":
            if not self.termination_reason:
                self.termination_reason = "normal_game_end"
            self.ref.set_result(self.ref.status(), self.termination_reason)
            return
        # Illegal LLM threshold => LLM loses
        if self.termination_reason == "illegal_llm_move" and self.cfg.fail_on_illegal:
            result = "0-1" if self.cfg.llm_is_white else "1-0"
            self.ref.force_result(result, self.termination_reason)
            return
        # Max plies
        if len(self.records) >= self.cfg.max_plies:
            self.termination_reason = self.termination_reason or "max_plies_reached"
            self.ref.set_result("1/2-1/2", self.termination_reason)
            return

    def play(self) -> str:
        ply = 0
        illegal_moves = 0
        while self.ref.status() == "*" and ply < self.cfg.max_plies:
            llm_turn_now = (self.ref.board.turn == chess.WHITE and self.cfg.llm_is_white) or (self.ref.board.turn == chess.BLACK and not self.cfg.llm_is_white)
            if llm_turn_now:
                if self.cfg.conversation_mode:
                    ok, uci, san, ms, meta = self._llm_turn_conversation()
                else:
                    ok, uci, san, ms, meta = self._llm_turn_standard()
                self.records.append({"actor": "LLM", "uci": uci, "ok": ok, "ms": ms, "san": san, "meta": meta})
                self.log.debug("Ply %d LLM move %s ok=%s san=%s ms=%d", ply+1, uci, ok, san, ms)
                # New: save conversation snapshot after each LLM move if enabled
                if self.cfg.conversation_log_path and self.cfg.conversation_log_every_turn:
                    self.dump_conversation_json()
                    self.dump_structured_history_json()
                if not ok:
                    illegal_moves += 1
                    if illegal_moves >= self.cfg.max_illegal_moves and self.cfg.fail_on_illegal:
                        self.termination_reason = "illegal_llm_move"
                        self.log.error("Terminating due to illegal LLM move at ply %d (count=%d)", ply+1, illegal_moves)
                        break
            else:
                ok, uci, san = self._opp_turn()
                self.records.append({"actor": "OPP", "uci": uci, "ok": ok, "san": san})
                self.log.debug("Ply %d OPP move %s san=%s", ply+1, uci, san)
                # In conversation mode, add user message describing engine move for next LLM prompt
                if self.cfg.conversation_mode:
                    # We'll add the user prompt only right before asking next time to avoid duplicates
                    pass
                # New: save conversation snapshot after each OPP move if enabled
                if self.cfg.conversation_log_path and self.cfg.conversation_log_every_turn:
                    self.dump_conversation_json()
                    self.dump_structured_history_json()
            ply += 1
        result = self.ref.status()
        if self.termination_reason == "illegal_llm_move" and result == "*":
            # LLM loses regardless of color
            result = "0-1" if self.cfg.llm_is_white else "1-0"
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
        latencies = [r.get("ms", 0) for r in llm_moves if r.get("ms") is not None]
        legal = [r for r in llm_moves if r.get("ok")]
        illegal = [r for r in llm_moves if not r.get("ok")]
        salvage_success = sum(1 for r in llm_moves if r.get("meta", {}).get("salvage_used"))
        return {
            "plies_total": len(self.records),
            "plies_llm": len(llm_moves),
            "llm_legal_moves": len(legal),
            "llm_illegal_moves": len(illegal),
            "llm_illegal_limit": self.cfg.max_illegal_moves,
            "llm_salvage_successes": salvage_success,
            "llm_legal_rate": (len(legal) / len(llm_moves)) if llm_moves else 0.0,
            "latency_ms_avg": statistics.mean(latencies) if latencies else 0,
            "latency_ms_p95": statistics.quantiles(latencies, n=100)[94] if len(latencies) >= 20 else (max(latencies) if latencies else 0),
            "result": self.ref.status(),
            "termination_reason": self.termination_reason,
            "duration_s": round(time.time() - self.start_ts, 2),
            "mode": "conversation" if self.cfg.conversation_mode else "standard",
        }

    def summary(self) -> dict:
        m = self.metrics()
        m["pgn"] = self.ref.pgn()
        if self.cfg.conversation_mode:
            m["conversation_messages"] = self.chat_messages
        m["history_verification"] = self.verify_history_result()
        # Also include a small preview of the structured history path if available
        m["structured_history_path"] = self._structured_history_path()
        return m

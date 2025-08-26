from __future__ import annotations
import time, asyncio, logging, statistics, json
import chess
from dataclasses import dataclass, field
from .referee import Referee
from .llm_client import ask_for_best_move_raw, ask_for_best_move_conversation, ask_for_best_move_plain, SYSTEM_CONV, SYSTEM
from .agent_normalizer import normalize_with_agent
from .move_validator import normalize_move

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

    # ---------------- LLM Turn (FEN/PGN mode) -----------------
    def _llm_turn_standard(self):
        side = "white" if self.ref.board.turn == chess.WHITE else "black"
        history = self._annotated_history()
        raw = ask_for_best_move_plain(side=side, history_text=history, model=self.model)
        fen = self.ref.board.fen()
        ok, uci, san, agent_ms, meta, _ = self._process_llm_raw(
            raw, fen, meta_extra={"mode": "standard", "prompt": f"Side to move: {side}\n{history}"}
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
        messages: list[dict] = [{"role": "system", "content": SYSTEM}]
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
            ply += 1
        result = self.ref.status()
        if self.termination_reason == "illegal_llm_move" and result == "*":
            result = "0-1"  # white (LLM) loses
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
        return m

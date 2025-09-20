#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time
from typing import List, Optional

import chess

# Windows non-blocking keyboard support
MSVCRT = None
if os.name == "nt":
    try:
        import msvcrt  # type: ignore
        MSVCRT = msvcrt
    except Exception:
        MSVCRT = None


def clear_screen():
    if os.name == "nt":
        os.system("cls")
    else:
        os.system("clear")


def load_history(path: str):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    headers = data.get("headers", {})
    start_fen = data.get("start_fen", chess.STARTING_FEN)
    result = data.get("result")
    termination_reason = data.get("termination_reason")
    all_moves = data.get("moves", [])
    moves = [m for m in all_moves if isinstance(m, dict) and "uci" in m]
    return headers, start_fen, result, termination_reason, moves


def build_boards(start_fen: str, moves: List[dict]) -> List[chess.Board]:
    boards: List[chess.Board] = []
    board = chess.Board(start_fen)
    boards.append(board.copy(stack=False))  # position before any move
    for m in moves:
        uci = m["uci"]
        try:
            board.push_uci(uci)
        except Exception as e:
            # If the history contains an illegal move, stop building further
            # but keep current boards so far. This lets the viewer see up to failure.
            print(f"Warning: could not apply move {uci}: {e}")
            break
        boards.append(board.copy(stack=False))
    return boards


def format_header(headers: dict, result: Optional[str]) -> str:
    parts = []
    if headers.get("Event"):
        parts.append(f"Event: {headers['Event']}")
    if headers.get("White") or headers.get("Black"):
        parts.append(f"White: {headers.get('White', '?')}  vs  Black: {headers.get('Black', '?')}")
    if headers.get("Date"):
        parts.append(f"Date: {headers['Date']}")
    if result:
        parts.append(f"Result: {result}")
    return " | ".join(parts)


def render(board: chess.Board, headers: dict, result: Optional[str], term_reason: Optional[str],
           moves: List[dict], idx: int, delay: float, autoplay: bool):
    """
    idx: number of plies already applied (0..len(moves))
    """
    clear_screen()
    print(format_header(headers, result))
    print("-")
    # Board printout
    print(board)  # ASCII board from python-chess
    print("-")
    # Move info line
    total = len(moves)
    if idx == 0:
        print("Start position")
    else:
        cur = moves[idx - 1]
        move_no = (idx + 1) // 2
        side = cur.get("side", "?")
        san = cur.get("san", cur.get("uci"))
        actor = cur.get("actor", "?")
        print(f"Ply {idx}/{total}  Move {move_no} ({side})  {san}  by {actor}")
    # Controls
    status = "PLAYING" if autoplay else "PAUSED"
    print(f"Status: {status} | Delay: {delay:.2f}s")
    if idx >= total and result:
        extra = f" | Termination: {term_reason}" if term_reason else ""
        print(f"Game over: {result}{extra}")
    print("Commands: [Enter] next | p prev | a autoplay | s pause | r restart | g <ply> goto | + faster | - slower | q quit")


def getchar_nonblocking(timeout: float) -> Optional[str]:
    """Wait up to timeout seconds for a keypress; return the char or None."""
    if MSVCRT:
        # Poll in small intervals to allow Ctrl+C as well
        end = time.time() + timeout
        while time.time() < end:
            if MSVCRT.kbhit():
                ch = MSVCRT.getwch()  # get wide char
                # On Windows, Enter can be '\r'
                if ch == "\r":
                    ch = "\n"
                return ch
            time.sleep(0.02)
        return None
    else:
        # Fallback: just sleep and return None
        time.sleep(timeout)
        return None


def main():
    parser = argparse.ArgumentParser(description="Rewatch a logged LLM Chess game from history JSON.")
    parser.add_argument("history", help="Path to hist_*.json produced by a run")
    parser.add_argument("--autoplay", action="store_true", help="Start in autoplay mode")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between moves in autoplay")
    args = parser.parse_args()

    headers, start_fen, result, term_reason, moves = load_history(args.history)
    boards = build_boards(start_fen, moves)

    idx = 0  # how many plies applied
    autoplay = bool(args.autoplay)
    delay = max(0.05, float(args.delay))

    while True:
        board = boards[min(idx, len(boards) - 1)]
        render(board, headers, result, term_reason, moves, idx, delay, autoplay)

        total = len(moves)
        if autoplay:
            # Allow pause or control during autoplay
            ch = getchar_nonblocking(delay)
            if ch is None:
                # advance one step after delay
                if idx < total:
                    idx += 1
                else:
                    autoplay = False
                continue
            # If key pressed, handle it immediately
            cmd = ch.strip()
            if cmd == "q":
                break
            elif cmd in ("s", "S"):
                autoplay = False
            elif cmd in ("+", ">"):
                delay = max(0.05, delay * 0.7)
            elif cmd in ("-", "<"):
                delay = min(10.0, delay / 0.7)
            elif cmd in ("p", "P"):
                if idx > 0:
                    idx -= 1
            elif cmd == "\n":
                if idx < total:
                    idx += 1
            elif cmd in ("r", "R"):
                idx = 0
            # ignore others in autoplay
            continue
        else:
            try:
                inp = input("")
            except (EOFError, KeyboardInterrupt):
                print()
                break
            inp = inp.strip()
            if inp == "q":
                break
            elif inp in ("a", "A"):
                autoplay = True
            elif inp in ("s", "S"):
                autoplay = False
            elif inp in ("p", "P"):
                if idx > 0:
                    idx -= 1
            elif inp in ("+", ">"):
                delay = max(0.05, delay * 0.7)
            elif inp in ("-", "<"):
                delay = min(10.0, delay / 0.7)
            elif inp in ("r", "R"):
                idx = 0
            elif inp.startswith("g "):
                try:
                    target = int(inp.split()[1])
                    if 0 <= target <= len(moves):
                        idx = target
                except Exception:
                    pass
            else:
                # default: next
                if idx < total:
                    idx += 1
                else:
                    # stay at end
                    pass


if __name__ == "__main__":
    main()

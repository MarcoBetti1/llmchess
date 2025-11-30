"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Chess } from "chess.js";
import { fetchGameHistory } from "@/lib/api";
import { ChessBoard } from "./chess-board";

type Props = {
  gameId: string;
  whiteModel: string;
  blackModel: string;
  size?: number;
};

type MoveEntry = {
  uci?: string;
  san?: string;
  event?: string;
  reason?: string;
  result?: string;
  fen_after?: string;
};

type BoardMove = { from: string; to: string };
type Mode = "live" | "replay";

const REPLAY_SPEED_MS = 1800;

function normalizeStartFen(raw?: string | null) {
  if (!raw || raw === "startpos") return new Chess().fen();
  return raw;
}

function applyMoveToBoard(board: Chess, move: MoveEntry): BoardMove | null {
  if (move.event === "termination") return null;
  let res: any = null;
  if (move.uci && move.uci.length >= 4) {
    try {
      const clean = move.uci.trim().toLowerCase();
      const parsed: { from: string; to: string; promotion?: string } = {
        from: clean.slice(0, 2),
        to: clean.slice(2, 4)
      };
      if (clean.length >= 5) {
        parsed.promotion = clean[4].toLowerCase();
      }
      res = board.move(parsed);
    } catch {
      res = null;
    }
  }
  if (!res && move.san) {
    try {
      res = board.move(move.san);
    } catch {
      res = null;
    }
  }
  if (res) return { from: res.from, to: res.to };
  return null;
}

function deriveSnapshot(startFen: string, mvs: MoveEntry[]) {
  let fen = startFen;
  let lastMove: BoardMove | undefined;
  let chess: Chess | null = null;
  try {
    chess = new Chess(startFen);
  } catch {
    chess = null;
  }

  for (const mv of mvs) {
    if (mv.event === "termination") break;
    let applied: BoardMove | null = null;
    if (chess) {
      applied = applyMoveToBoard(chess, mv);
      fen = chess.fen();
    }
    if (!applied && mv.fen_after) {
      // Fallback to provided fen in case SAN/UCI parsing fails
      fen = mv.fen_after;
      if (mv.uci && mv.uci.length >= 4) {
        applied = { from: mv.uci.slice(0, 2), to: mv.uci.slice(2, 4) };
      }
    }
    if (applied) {
      lastMove = applied;
    }
  }
  return { fen, lastMove };
}

export function LiveBoard({ gameId, whiteModel, blackModel, size = 260 }: Props) {
  const [moves, setMoves] = useState<MoveEntry[]>([]);
  const [initialFen, setInitialFen] = useState<string>(new Chess().fen());
  const [liveFen, setLiveFen] = useState<string>(new Chess().fen());
  const [displayFen, setDisplayFen] = useState<string>(new Chess().fen());
  const [liveLastMove, setLiveLastMove] = useState<BoardMove | undefined>(undefined);
  const [displayLastMove, setDisplayLastMove] = useState<BoardMove | undefined>(undefined);
  const [termination, setTermination] = useState<{ result?: string; reason?: string } | null>(null);
  const [mode, setMode] = useState<Mode>("live");
  const [boardKey, setBoardKey] = useState(0);

  const replayIdxRef = useRef(0);
  const replayTimerRef = useRef<NodeJS.Timeout | null>(null);
  const replayStartTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const replayChessRef = useRef<Chess | null>(null);
  const pollRef = useRef<NodeJS.Timeout | null>(null);
  const modeRef = useRef<Mode>("live");
  const liveFenRef = useRef<string>(liveFen);
  const liveLastMoveRef = useRef<BoardMove | undefined>(liveLastMove);
  const playableMovesRef = useRef<MoveEntry[]>([]);

  const playableMoves = useMemo(() => moves.filter((m) => m.event !== "termination"), [moves]);

  useEffect(() => {
    modeRef.current = mode;
  }, [mode]);
  useEffect(() => {
    liveFenRef.current = liveFen;
  }, [liveFen]);
  useEffect(() => {
    liveLastMoveRef.current = liveLastMove;
  }, [liveLastMove]);
  useEffect(() => {
    playableMovesRef.current = playableMoves;
  }, [playableMoves]);

  useEffect(() => {
    // Reset when switching to a new game id
    setMoves([]);
    setTermination(null);
    modeRef.current = "live";
    setMode("live");
    setInitialFen(new Chess().fen());
    setLiveFen(new Chess().fen());
    setDisplayFen(new Chess().fen());
    setLiveLastMove(undefined);
    setDisplayLastMove(undefined);
    setBoardKey((k) => k + 1);
    if (replayTimerRef.current) {
      clearInterval(replayTimerRef.current);
      replayTimerRef.current = null;
    }
    if (replayStartTimeoutRef.current) {
      clearTimeout(replayStartTimeoutRef.current);
      replayStartTimeoutRef.current = null;
    }
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, [gameId]);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const hist = await fetchGameHistory(gameId);
        if (!hist || cancelled) return;
        const startFen = normalizeStartFen((hist as any).start_fen || hist.initial_fen);
        const mvs = (hist.moves || []).map((m: any) => ({
          uci: m.uci,
          san: m.san,
          event: m.event,
          reason: m.reason,
          result: m.result,
          fen_after: m.fen_after
        }));
        const termMove = [...mvs].reverse().find((m) => m.event === "termination");
        const histResult = (hist as any).result;
        const histReason = (hist as any).termination_reason;
        const derivedTermination =
          termMove ||
          (histResult && histResult !== "*") ||
          (histReason && String(histReason).trim().length > 0)
            ? {
                result: (termMove && termMove.result) || (histResult !== "*" ? histResult : undefined),
                reason: (termMove && termMove.reason) || histReason
              }
            : null;

        setInitialFen(startFen);
        setMoves(mvs);
        setTermination(derivedTermination);
        const snapshot = deriveSnapshot(startFen, mvs);
        setLiveFen(snapshot.fen);
        setLiveLastMove(snapshot.lastMove);
        if (modeRef.current === "live") {
          setDisplayFen(snapshot.fen);
          setDisplayLastMove(snapshot.lastMove);
        } else if (!derivedTermination) {
          // If the game resumed or we somehow were in replay while live data arrived, snap back to live.
          modeRef.current = "live";
          setMode("live");
          setDisplayFen(snapshot.fen);
          setDisplayLastMove(snapshot.lastMove);
        }
      } catch {
        // ignore errors for now; mock data handles empty states
      }
    };

    load();
    pollRef.current = setInterval(load, 1000);
    return () => {
      cancelled = true;
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [gameId]);

  useEffect(() => {
    return () => {
      if (replayTimerRef.current) clearInterval(replayTimerRef.current);
      if (replayStartTimeoutRef.current) clearTimeout(replayStartTimeoutRef.current);
    };
  }, []);

  const stopReplay = () => {
    if (replayTimerRef.current) {
      clearInterval(replayTimerRef.current);
      replayTimerRef.current = null;
    }
    if (replayStartTimeoutRef.current) {
      clearTimeout(replayStartTimeoutRef.current);
      replayStartTimeoutRef.current = null;
    }
    replayIdxRef.current = 0;
    replayChessRef.current = null;
    modeRef.current = "live";
    setMode("live");
    setDisplayFen(liveFenRef.current);
    setDisplayLastMove(liveLastMoveRef.current);
  };

  const startReplay = () => {
    if (!playableMovesRef.current.length) return;
    if (replayTimerRef.current) {
      clearInterval(replayTimerRef.current);
      replayTimerRef.current = null;
    }
    const replayChess = new Chess(initialFen);
    replayChessRef.current = replayChess;
    replayIdxRef.current = 0;
    modeRef.current = "replay";
    setMode("replay");
    setDisplayFen(initialFen);
    setDisplayLastMove(undefined);

    const tick = () => {
      const mv = playableMovesRef.current[replayIdxRef.current];
      if (!mv || !replayChessRef.current) {
        stopReplay();
        return;
      }
      const applied = applyMoveToBoard(replayChessRef.current, mv);
      replayIdxRef.current += 1;

      if (applied) {
        setDisplayFen(replayChessRef.current.fen());
        setDisplayLastMove(applied);
      }

      if (replayIdxRef.current >= playableMovesRef.current.length) {
        stopReplay();
      }
    };

    // Show the starting position briefly before the first move, then tick on an interval
    replayStartTimeoutRef.current = setTimeout(() => {
      tick();
      replayTimerRef.current = setInterval(tick, REPLAY_SPEED_MS);
    }, REPLAY_SPEED_MS);
  };

  const waitingOn = useMemo(() => {
    try {
      const c = new Chess(displayFen);
      return c.turn() === "w" ? "white" : "black";
    } catch {
      return null;
    }
  }, [displayFen]);

  return (
    <div className="card p-3 space-y-2 inline-block" style={{ width: size + 32 }}>
      <div className="flex items-center justify-between text-sm text-white/70">
        <div>
          <p className="text-white text-sm font-semibold">{gameId}</p>
          <p className="text-xs text-white/70">
            White: {whiteModel} <span className="text-white/50">•</span> Black: {blackModel}
          </p>
        </div>
        {waitingOn && !termination && (
          <div className="chip">
            Waiting on <span className="font-semibold text-white ml-1">{waitingOn}</span>
          </div>
        )}
        {termination && (
          <div className="chip bg-accent text-canvas-900">
            {termination.result || "?"} - {termination.reason || "ended"}
          </div>
        )}
      </div>

      <div className="relative">
        <div>
          <ChessBoard key={boardKey} fen={displayFen} lastMove={displayLastMove} size={size} />
        </div>
        {mode === "replay" && (
          <div className="absolute top-2 right-2 chip bg-black/60 border border-white/20 text-white">Replaying</div>
        )}
        {termination && mode === "live" && (
          <button className="absolute inset-0 grid place-items-center text-white" onClick={startReplay}>
            <div className="px-4 py-2 rounded-full bg-black/60 border border-white/20">
              Tap to replay
            </div>
          </button>
        )}
      </div>
    </div>
  );
}

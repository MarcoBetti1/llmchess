"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Chess } from "chess.js";
import { fetchGameConversation, fetchGameHistory } from "@/lib/api";
import { ChessBoard } from "./chess-board";
import { ConversationDialog } from "./conversation-dialog";
import { ConversationData } from "@/types";

type Props = {
  gameId: string;
  whiteModel: string;
  blackModel: string;
  size?: number;
  winner?: "white" | "black" | "draw" | null;
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

export function LiveBoard({ gameId, whiteModel, blackModel, size = 260, winner }: Props) {
  const [moves, setMoves] = useState<MoveEntry[]>([]);
  const [initialFen, setInitialFen] = useState<string>(new Chess().fen());
  const [liveFen, setLiveFen] = useState<string>(new Chess().fen());
  const [displayFen, setDisplayFen] = useState<string>(new Chess().fen());
  const [liveLastMove, setLiveLastMove] = useState<BoardMove | undefined>(undefined);
  const [displayLastMove, setDisplayLastMove] = useState<BoardMove | undefined>(undefined);
  const [termination, setTermination] = useState<{ result?: string; reason?: string } | null>(null);
  const [mode, setMode] = useState<Mode>("live");
  const [boardKey, setBoardKey] = useState(0);
  const [conversationOpen, setConversationOpen] = useState(false);
  const [conversation, setConversation] = useState<ConversationData | null>(null);
  const [convLoading, setConvLoading] = useState(false);
  const [renderSize, setRenderSize] = useState(size);
  const wrapperRef = useRef<HTMLDivElement | null>(null);

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
    setConversation(null);
    setConversationOpen(false);
    setConvLoading(false);
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
        const termIdx = mvs.findIndex((m) => m.event === "termination");
        const termMove = termIdx >= 0 ? mvs[termIdx] : undefined;
        const histResult = (hist as any).result;
        const histReason = (hist as any).termination_reason;
        const terminatedFlag = (hist as any).terminated;
        const derivedTermination =
          terminatedFlag &&
          ((termMove && termIdx === mvs.length - 1) ||
            (histResult && histResult !== "*") ||
            (histReason && String(histReason).trim().length > 0))
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

  useEffect(() => {
    const recalc = () => {
      const width = wrapperRef.current?.clientWidth || size;
      const inner = Math.max(220, width - 32); // account for padding
      setRenderSize(Math.min(size, inner));
    };
    recalc();
    window.addEventListener("resize", recalc);
    return () => window.removeEventListener("resize", recalc);
  }, [size]);

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

  const winnerSide = useMemo(() => {
    if (winner === "white" || winner === "black") return winner;
    if (termination?.result) {
      if (termination.result === "1-0") return "white";
      if (termination.result === "0-1") return "black";
      if (termination.result === "1/2-1/2") return "draw";
    }
    return null;
  }, [winner, termination]);

  const gameDone = useMemo(() => Boolean(winnerSide) || Boolean(termination), [winnerSide, termination]);

  const formattedTerminationReason = useMemo(() => {
    const reason = termination?.reason;
    if (!reason) return "ended";
    if (reason === "illegal_opponent_move") return "illegal_llm_move";
    return reason;
  }, [termination]);

  const sideClasses = (side: "white" | "black") => {
    const isWinner = winnerSide === side;
    const isTurn = waitingOn === side && !winnerSide;
    if (isWinner) return "bg-emerald-500/20 text-emerald-900 dark:text-emerald-100 border border-emerald-400/50 shadow-sm";
    if (isTurn) return "bg-accent/20 text-[var(--ink-900)] border border-accent/40 shadow-sm";
    return "bg-[var(--field-bg)] text-[var(--ink-700)] border border-[var(--border-soft)]";
  };

  const sideHighlight = (side: "white" | "black") => {
    const isWinner = winnerSide === side;
    const isLoser = winnerSide && winnerSide !== side;
    const isTurn = waitingOn === side && !gameDone;
    if (!isWinner && !isLoser && !isTurn) return null;

    let color = "rgba(148,163,184,0.2)"; // subtle neutral, slightly stronger
    if (isWinner) color = "rgba(16,185,129,0.32)"; // emerald
    if (isLoser) color = "rgba(248,113,113,0.26)"; // red

    const gradient =
      side === "black"
        ? `linear-gradient(180deg, ${color} 0%, rgba(0,0,0,0) 90%)`
        : `linear-gradient(0deg, ${color} 0%, rgba(0,0,0,0) 90%)`;
    const posClass = side === "black" ? "-top-8" : "-bottom-8";
    return { gradient, posClass };
  };

  const loadConversation = async () => {
    setConvLoading(true);
    setConversationOpen(true);
    try {
      const data = await fetchGameConversation(gameId);
      setConversation(data);
    } catch {
      setConversation({ game_id: gameId, messages: [] });
    } finally {
      setConvLoading(false);
    }
  };

  return (
    <div className="card p-4 space-y-3 w-full" ref={wrapperRef}>
      <div className="flex items-center justify-between gap-2 text-sm text-[var(--ink-700)]">
        <div>
          <p className="text-[var(--ink-900)] text-sm font-semibold">{gameId}</p>
          <p className="text-xs text-[var(--ink-500)]">
            White: {whiteModel} | Black: {blackModel}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {waitingOn && !termination && (
            <div className="chip">
              Waiting on <span className="font-semibold text-[var(--ink-900)] ml-1">{waitingOn}</span>
            </div>
          )}
          {termination && (
            <div className="chip bg-accent text-canvas-900">
              {formattedTerminationReason}
            </div>
          )}
          <button className="btn secondary text-xs" onClick={loadConversation}>
            Conversation
          </button>
        </div>
      </div>

      <div className="relative flex flex-col items-center space-y-3">
        <div className={`chip text-xs ${sideClasses("black")}`}>{blackModel}</div>
        <div className="relative w-full flex justify-center py-2">
          {(() => {
            const h = sideHighlight("black");
            if (!h) return null;
            return (
              <div
                className={`pointer-events-none absolute left-6 right-6 ${h.posClass} h-20 rounded-full blur-[12px] transition-all`}
                style={{ backgroundImage: h.gradient }}
              />
            );
          })()}
          <ChessBoard key={boardKey} fen={displayFen} lastMove={displayLastMove} size={renderSize} />
          {(() => {
            const h = sideHighlight("white");
            if (!h) return null;
            return (
              <div
                className={`pointer-events-none absolute left-6 right-6 ${h.posClass} h-20 rounded-full blur-[12px] transition-all`}
                style={{ backgroundImage: h.gradient }}
              />
            );
          })()}
        </div>
        <div className={`chip text-xs ${sideClasses("white")}`}>{whiteModel}</div>
        {mode === "replay" && (
          <div className="absolute top-2 right-2 chip bg-[var(--overlay-bg)] border border-[var(--border-soft)] text-[var(--ink-900)] shadow-sm">
            Replaying
          </div>
        )}
        {termination && mode === "live" && (
          <button className="absolute inset-0 grid place-items-center text-[var(--ink-900)]" onClick={startReplay}>
            <div className="px-4 py-2 rounded-full bg-[var(--overlay-bg)] border border-[var(--border-soft)] shadow-sm">
              Tap to replay
            </div>
          </button>
        )}
      </div>
      <ConversationDialog
        open={conversationOpen}
        onClose={() => setConversationOpen(false)}
        log={convLoading ? null : conversation}
      />
    </div>
  );
}

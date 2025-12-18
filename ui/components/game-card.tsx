"use client";

import { GameSummary } from "@/types";
import { ChessBoard } from "@/components/chess-board";
import clsx from "clsx";

type Props = {
  game: GameSummary;
  onConversation: (gameId: string) => void;
  onInspect?: (gameId: string) => void;
};

const statusColor: Record<GameSummary["status"], string> = {
  queued: "text-[var(--badge-queued-text)] bg-[var(--badge-queued-bg)]",
  running: "text-canvas-900 bg-accent",
  finished: "text-[var(--badge-finished-text)] bg-[var(--badge-finished-bg)]"
};

export function GameCard({ game, onConversation, onInspect }: Props) {
  return (
    <div className="card fade-in p-4 flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-[var(--ink-500)]">Game #{game.game_id}</p>
          <p className="text-lg font-semibold text-[var(--ink-900)]">
            {game.players.white.model} <span className="text-[var(--ink-500)]">vs</span> {game.players.black.model}
          </p>
        </div>
        <span className={clsx("chip", statusColor[game.status])}>
          {game.status === "running" ? "Running" : game.status === "queued" ? "Queued" : "Finished"}
        </span>
      </div>

      <ChessBoard fen={game.current_fen} lastMove={game.last_move || undefined} size={320} />

      <div className="flex flex-wrap gap-2 text-sm text-[var(--ink-700)]">
        <div className="chip">
          Move <strong className="ml-1 text-[var(--ink-900)]">{game.move_number}</strong>
        </div>
        {game.last_move && (
          <div className="chip">
            Last move <strong className="ml-1 text-[var(--ink-900)]">{game.last_move.san}</strong>
          </div>
        )}
        <div className="chip">
          Illegal moves W/B{" "}
          <strong className="ml-1 text-[var(--ink-900)]">
            {game.illegal_moves?.white ?? 0}/{game.illegal_moves?.black ?? 0}
          </strong>
        </div>
        {game.winner && (
          <div className="chip">
            Result <strong className="ml-1 text-[var(--ink-900)] capitalize">{game.winner}</strong>
          </div>
        )}
      </div>

      <div className="flex justify-end gap-2">
        {onInspect && (
          <button className="btn secondary" onClick={() => onInspect(game.game_id)}>
            Inspect
          </button>
        )}
        <button className="btn" onClick={() => onConversation(game.game_id)}>
          View Conversation
        </button>
      </div>
    </div>
  );
}

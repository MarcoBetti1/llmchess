"use client";

import dynamic from "next/dynamic";
import { CSSProperties, useMemo } from "react";

const DynamicBoard = dynamic(
  () =>
    import("react-chessboard").then((mod: any) => {
      return mod.Chessboard || mod.default;
    }),
  { ssr: false }
);

type Props = {
  fen: string;
  lastMove?: { from: string; to: string } | null;
  orientation?: "white" | "black";
  size?: number;
};

export function ChessBoard({ fen, lastMove, orientation = "white", size = 360 }: Props) {
  const boardSize = Math.max(200, Math.floor(size));
  const customSquareStyles = useMemo<Record<string, CSSProperties>>(() => {
    if (!lastMove) return {};
    return {
      [lastMove.from]: {
        backgroundColor: "rgba(247, 201, 72, 0.3)"
      },
      [lastMove.to]: {
        backgroundColor: "rgba(124, 231, 172, 0.35)"
      }
    };
  }, [lastMove]);

  return (
    <div
      className="rounded-2xl border border-[var(--border-soft)] bg-[var(--card-bg)] overflow-hidden"
      style={{ maxWidth: boardSize, width: "100%", margin: "0 auto", boxShadow: "none" }}
    >
      <DynamicBoard
        position={fen}
        boardOrientation={orientation}
        arePiecesDraggable={false}
        boardWidth={boardSize}
        customSquareStyles={customSquareStyles}
        customBoardStyle={{
          borderRadius: "14px",
          border: "1px solid var(--board-border)",
          boxShadow: "none",
          background: "var(--board-surface)",
          color: "var(--ink-900)",
          fontWeight: 600
        }}
        customNotationStyle={{
          color: "var(--ink-900)",
          fontWeight: 600,
          fontSize: 12,
          mixBlendMode: "difference"
        }}
        customLightSquareStyle={{ backgroundColor: "var(--board-light)" }}
        customDarkSquareStyle={{ backgroundColor: "var(--board-dark)" }}
        animationDuration={400}
      />
    </div>
  );
}

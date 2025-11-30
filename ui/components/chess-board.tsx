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
    <div className="overflow-hidden rounded-2xl border border-white/10 shadow-glow">
      <DynamicBoard
        position={fen}
        boardOrientation={orientation}
        arePiecesDraggable={false}
        boardWidth={size}
        customSquareStyles={customSquareStyles}
        customBoardStyle={{
          borderRadius: "20px",
          boxShadow: "0 10px 35px rgba(0, 0, 0, 0.45)"
        }}
        customLightSquareStyle={{ backgroundColor: "#f7f7fb" }}
        customDarkSquareStyle={{ backgroundColor: "#0f172a" }}
        animationDuration={400}
      />
    </div>
  );
}

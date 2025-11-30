"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef, useState } from "react";
import { Chess, Move, Square } from "chess.js";
import clsx from "clsx";

const InteractiveBoard = dynamic(
  () =>
    import("react-chessboard").then((mod: any) => {
      return mod.Chessboard || mod.default;
    }),
  { ssr: false }
);

const models = ["openai/gpt-4o", "anthropic/claude-4.5", "meta/llama-3.1-70b"];

type Side = "white" | "black";

export default function PlayPage() {
  const gameRef = useRef(new Chess());
  const [fen, setFen] = useState(gameRef.current.fen());
  const [humanSide, setHumanSide] = useState<Side>("white");
  const [aiModel, setAiModel] = useState(models[0]);
  const [promptMode, setPromptMode] = useState("fen+plaintext");
  const [illegalLimit, setIllegalLimit] = useState(3);
  const [status, setStatus] = useState("Your move.");
  const [waitingOnAI, setWaitingOnAI] = useState(false);

  useEffect(() => {
    resetGame(humanSide);
  }, [humanSide]);

  const resetGame = (side: Side) => {
    const next = new Chess();
    gameRef.current = next;
    setFen(next.fen());
    setStatus(side === "white" ? "Your move." : "AI to open.");
    setWaitingOnAI(false);
    if (side === "black") {
      setTimeout(() => makeAIMove(), 450);
    }
  };

  const makeAIMove = () => {
    const game = gameRef.current;
    const over = typeof game.isGameOver === "function" ? game.isGameOver() : (game as any).game_over?.();
    if (over) {
      setStatus("Game finished.");
      return;
    }
    const moves = game.moves({ verbose: true }) as Move[];
    if (!moves.length) {
      setStatus("No legal moves left.");
      return;
    }
    const choice = moves[Math.floor(Math.random() * moves.length)];
    game.move(choice.san);
    setFen(game.fen());
    setWaitingOnAI(false);
    setStatus(`AI (${aiModel}) played ${choice.san}`);
  };

  const onDrop = (source: Square, target: Square) => {
    const game = gameRef.current;
    const turnSide: Side = game.turn() === "w" ? "white" : "black";
    if (turnSide !== humanSide || waitingOnAI) return false;
    const move = game.move({ from: source, to: target, promotion: "q" });
    if (move === null) {
      setStatus("Illegal move. Try again.");
      return false;
    }
    setFen(game.fen());
    setStatus(`You played ${move.san}. Waiting for AI...`);
    setWaitingOnAI(true);
    setTimeout(() => makeAIMove(), 500);
    return true;
  };

  const promptSummary = useMemo(
    () => `POST /api/human-games with model=${aiModel}, mode=${promptMode}, limit=${illegalLimit}`,
    [aiModel, promptMode, illegalLimit]
  );

  return (
    <div className="space-y-6 fade-in">
      <div className="flex flex-col gap-2">
        <p className="text-sm uppercase tracking-[0.3em] text-white/60">Human vs LLM</p>
        <h1 className="text-3xl font-semibold text-white font-display">Play a game</h1>
        <p className="text-white/70 text-sm">
          The board enforces legality locally via chess.js. Wire the `onDrop` to POST `/api/human-games/:gameId/move`
          and hydrate replies to animate AI moves.
        </p>
      </div>

      <div className="grid gap-6 md:grid-cols-[2fr,1fr] items-start">
        <div className="card p-4 flex flex-col gap-4">
          <InteractiveBoard
            position={fen}
            boardOrientation={humanSide}
            onPieceDrop={(sourceSquare: Square, targetSquare: Square) => onDrop(sourceSquare, targetSquare)}
            animationDuration={250}
            arePiecesDraggable
            customBoardStyle={{
              borderRadius: "24px",
              boxShadow: "0 10px 35px rgba(0, 0, 0, 0.45)"
            }}
            customLightSquareStyle={{ backgroundColor: "#f7f7fb" }}
            customDarkSquareStyle={{ backgroundColor: "#0f172a" }}
          />
          <div className="flex flex-wrap gap-2 text-sm text-white/70">
            <span className="chip">{status}</span>
            <span className={clsx("chip", waitingOnAI && "bg-accent text-canvas-900")}>
              {waitingOnAI ? "Waiting for AI" : "Your turn"}
            </span>
          </div>
        </div>

        <div className="card p-5 space-y-4">
          <div>
            <p className="text-sm uppercase tracking-[0.25em] text-white/60">Match setup</p>
            <p className="text-lg font-semibold text-white">Configure the AI</p>
          </div>
          <div className="space-y-3">
            <label className="text-sm text-white/70">AI model</label>
            <select
              className="w-full rounded-xl bg-white/5 border border-white/10 px-3 py-2 text-white/90"
              value={aiModel}
              onChange={(e) => setAiModel(e.target.value)}
            >
              {models.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-3">
            <label className="text-sm text-white/70">You play</label>
            <div className="flex gap-2">
              {(["white", "black"] as Side[]).map((side) => (
                <button
                  key={side}
                  className={clsx(
                    "flex-1 rounded-xl px-4 py-2 border border-white/10",
                    humanSide === side ? "bg-accent text-canvas-900" : "bg-white/5 text-white/80"
                  )}
                  onClick={() => setHumanSide(side)}
                >
                  {side}
                </button>
              ))}
            </div>
          </div>
          <div className="space-y-3">
            <label className="text-sm text-white/70">Prompt mode</label>
            <select
              className="w-full rounded-xl bg-white/5 border border-white/10 px-3 py-2 text-white/90"
              value={promptMode}
              onChange={(e) => setPromptMode(e.target.value)}
            >
              <option value="plaintext">plaintext</option>
              <option value="fen">fen</option>
              <option value="fen+plaintext">fen+plaintext</option>
            </select>
          </div>
          <div className="space-y-3">
            <label className="text-sm text-white/70">Illegal move limit</label>
            <input
              type="number"
              min={1}
              className="w-full rounded-xl bg-white/5 border border-white/10 px-3 py-2 text-white/90"
              value={illegalLimit}
              onChange={(e) => setIllegalLimit(Number(e.target.value))}
            />
          </div>
          <div className="flex gap-2">
            <button className="btn flex-1" onClick={() => resetGame(humanSide)}>
              New game
            </button>
            <button
              className="btn secondary flex-1"
              onClick={() => setStatus("You resigned. Reset to play again.")}
            >
              Resign
            </button>
          </div>
          <p className="text-xs text-white/60">{promptSummary}</p>
        </div>
      </div>
    </div>
  );
}

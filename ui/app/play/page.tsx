"use client";

import dynamic from "next/dynamic";
import { useMemo, useRef, useState } from "react";
import { Chess, Move, Square } from "chess.js";
import clsx from "clsx";
import { CSSProperties } from "react";

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
  const [status, setStatus] = useState("Ready to start a game.");
  const [waitingOnAI, setWaitingOnAI] = useState(false);
  const [inGame, setInGame] = useState(false);
  const [gameOverReason, setGameOverReason] = useState<string | null>(null);
  const [selectedSquare, setSelectedSquare] = useState<Square | null>(null);
  const [moveHints, setMoveHints] = useState<Square[]>([]);

  const startGame = (side: Side) => {
    const next = new Chess();
    gameRef.current = next;
    setFen(next.fen());
    setStatus(side === "white" ? "Your move." : "AI to open.");
    setWaitingOnAI(false);
    setGameOverReason(null);
    setInGame(true);
    if (side === "black") {
      setTimeout(() => makeAIMove(), 450);
    }
  };

  const concludeGame = (label: string) => {
    setStatus(label);
    setGameOverReason(label);
    setInGame(false);
    setWaitingOnAI(false);
    setSelectedSquare(null);
    setMoveHints([]);
  };

  const handleGameEndIfNeeded = (winner: string) => {
    const game = gameRef.current;
    const over = typeof game.isGameOver === "function" ? game.isGameOver() : (game as any).game_over?.();
    if (!over) return false;
    const reason = game.isCheckmate()
      ? `${winner} won by checkmate.`
      : game.isStalemate()
      ? "Draw by stalemate."
      : game.isThreefoldRepetition()
      ? "Draw by repetition."
      : game.isInsufficientMaterial()
      ? "Draw by material."
      : game.isDraw()
      ? "Drawn game."
      : "Game finished.";
    concludeGame(reason);
    return true;
  };

  const resetSelection = () => {
    setSelectedSquare(null);
    setMoveHints([]);
  };

  const loadHints = (square: Square) => {
    const game = gameRef.current;
    const verboseMoves = game.moves({ square, verbose: true }) as Move[];
    setSelectedSquare(square);
    setMoveHints(verboseMoves.map((m) => m.to as Square));
  };

  const isHumanTurn = () => {
    const turnSide: Side = gameRef.current.turn() === "w" ? "white" : "black";
    return turnSide === humanSide;
  };

  const canInteract = () => inGame && !waitingOnAI && !gameOverReason && isHumanTurn();

  const makeAIMove = () => {
    const game = gameRef.current;
    if (!inGame) return;
    if (handleGameEndIfNeeded("AI")) return;
    const moves = game.moves({ verbose: true }) as Move[];
    if (!moves.length) {
      concludeGame("No legal moves left.");
      return;
    }
    const choice = moves[Math.floor(Math.random() * moves.length)];
    game.move(choice.san);
    setFen(game.fen());
    setWaitingOnAI(false);
    if (handleGameEndIfNeeded("AI")) return;
    setStatus(`AI (${aiModel}) played ${choice.san}`);
  };

  const attemptMove = (source: Square, target: Square) => {
    if (gameOverReason || !inGame || waitingOnAI || !isHumanTurn()) return false;
    const game = gameRef.current;
    const move = game.move({ from: source, to: target, promotion: "q" });
    if (move === null) {
      setStatus("Illegal move. Try again.");
      return false;
    }
    setFen(game.fen());
    resetSelection();
    if (handleGameEndIfNeeded("You")) return true;
    setStatus(`You played ${move.san}. Waiting for AI...`);
    setWaitingOnAI(true);
    setTimeout(() => makeAIMove(), 500);
    return true;
  };

  const onSquareClick = (square: Square) => {
    if (!canInteract()) return;
    const game = gameRef.current;
    const piece = game.get(square);
    const isOwnPiece = piece?.color === (humanSide === "white" ? "w" : "b");

    if (selectedSquare) {
      if (square === selectedSquare) {
        resetSelection();
        return;
      }

      const selectedPiece = game.get(selectedSquare);
      const isKingToOwnRook =
        selectedPiece?.type === "k" && piece?.type === "r" && piece.color === selectedPiece.color;

      if (isKingToOwnRook) {
        const kingFile = selectedSquare[0];
        const rookFile = square[0];
        const rank = selectedSquare[1];
        const destSquare = `${rookFile > kingFile ? "g" : "c"}${rank}` as Square;
        if (attemptMove(selectedSquare, destSquare)) return;
      }

      if (isOwnPiece) {
        loadHints(square);
        return;
      }

      const moved = attemptMove(selectedSquare, square);
      if (!moved) resetSelection();
      return;
    }

    if (isOwnPiece) {
      loadHints(square);
    } else {
      resetSelection();
    }
  };

  const squareStyles = useMemo(() => {
    const styles: Record<string, CSSProperties> = {};
    if (selectedSquare) {
      styles[selectedSquare] = {
        boxShadow: "inset 0 0 0 3px rgba(124, 231, 172, 0.9)",
        background: "radial-gradient(circle at 50% 50%, rgba(124,231,172,0.22), transparent 65%)"
      };
    }
    moveHints.forEach((sq) => {
      styles[sq] = {
        boxShadow: "inset 0 0 0 3px rgba(163, 191, 250, 0.9)",
        background: "radial-gradient(circle at 50% 50%, rgba(163,191,250,0.22), transparent 65%)"
      };
    });
    return styles;
  }, [selectedSquare, moveHints]);

  const promptSummary = useMemo(
    () => `POST /api/human-games with model=${aiModel}, mode=${promptMode}`,
    [aiModel, promptMode]
  );

  const resign = () => {
    if (!inGame) return;
    concludeGame("You resigned. Reset to play again.");
  };

  return (
    <div className="space-y-6 fade-in">
      <div className="flex flex-col gap-2">
        <p className="text-sm uppercase tracking-[0.3em] text-white/60">Human vs LLM</p>
        <h1 className="text-3xl font-semibold text-white font-display">Play a game</h1>
        <p className="text-white/70 text-sm">
          The board enforces legality locally via chess.js. Wire move submissions to POST `/api/human-games/:gameId/move`
          and hydrate replies to animate AI moves.
        </p>
      </div>

      <div
        className={clsx(
          "grid gap-6 items-start transition-all duration-500",
          inGame ? "md:grid-cols-[minmax(0,3fr)_minmax(0,0.9fr)]" : "md:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]"
        )}
      >
        <div
          className={clsx(
            "card p-4 flex flex-col gap-4 transition-all duration-500",
            inGame && "md:p-6 md:scale-[1.02]"
          )}
        >
          <div className="relative">
            <InteractiveBoard
              position={fen}
              boardOrientation={humanSide}
              onSquareClick={(square: Square) => onSquareClick(square)}
              animationDuration={200}
              arePiecesDraggable={false}
              customSquareStyles={squareStyles}
              customBoardStyle={{
                borderRadius: "24px",
                boxShadow: "0 10px 35px rgba(0, 0, 0, 0.45)"
              }}
              customLightSquareStyle={{ backgroundColor: "#f7f7fb" }}
              customDarkSquareStyle={{ backgroundColor: "#1d253a" }}
            />
            {gameOverReason && (
              <div className="absolute inset-0 bg-black/60 backdrop-blur-[2px] flex items-center justify-center text-center px-6">
                <div className="space-y-3">
                  <p className="text-lg font-semibold text-white">{gameOverReason}</p>
                  <button className="btn" onClick={() => startGame(humanSide)}>
                    Play again
                  </button>
                </div>
              </div>
            )}
          </div>
          <div className="flex flex-wrap gap-2 text-sm text-white/70">
            <span className="chip">{status}</span>
            <span className={clsx("chip", waitingOnAI && "bg-accent text-canvas-900")}>
              {waitingOnAI ? "Waiting for AI" : "Your turn"}
            </span>
          </div>
          </div>

        <div
          className={clsx(
            "card transition-all duration-500",
            inGame ? "p-4 md:max-w-xs md:ml-auto md:scale-[0.95]" : "p-5 space-y-4 md:max-w-md"
          )}
        >
          {inGame ? (
            <div className="flex flex-col items-stretch gap-3">
              <button className="btn secondary w-full" onClick={resign}>
                Resign
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              <p className="text-lg font-semibold text-white">Configure the AI</p>
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
              <div className="flex gap-2">
                <button className="btn flex-1" onClick={() => startGame(humanSide)}>
                  Start game
                </button>
              </div>
              <p className="text-xs text-white/60">{promptSummary}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

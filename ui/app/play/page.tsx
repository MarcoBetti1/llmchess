"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef, useState } from "react";
import { Chess, Move, Square } from "chess.js";
import clsx from "clsx";
import { CSSProperties } from "react";
import { createHumanGame, postHumanMove } from "@/lib/api";
import { ConversationMessage } from "@/types";
import { ConversationThread } from "@/components/conversation-thread";
import { PromptDialog } from "@/components/prompt-dialog";

const InteractiveBoard = dynamic(
  () =>
    import("react-chessboard").then((mod: any) => {
      return mod.Chessboard || mod.default;
    }),
  { ssr: false }
);

const models = [
  "openai/gpt-5-chat",
  "openai/gpt-5-mini",
  "openai/gpt-4o",
  "openai/gpt-4.1",
  "anthropic/claude-3.7-sonnet",
  "anthropic/claude-haiku-4.5",
  "google/gemini-2.5-pro",
  "mistral/mistral-large-3"
];
const DEFAULT_SYSTEM = "You are a strong chess player. When asked for a move, provide only the best legal move in SAN.";
const DEFAULT_TEMPLATE = `Side to move: {SIDE_TO_MOVE}
Position (FEN): {FEN}
SAN history: {SAN_HISTORY}
Plaintext history:
{PLAINTEXT_HISTORY}
Respond with only your best legal move in SAN.`;

type Side = "white" | "black";

export default function PlayPage() {
  const gameRef = useRef(new Chess());
  const [fen, setFen] = useState(gameRef.current.fen());
  const [humanSide, setHumanSide] = useState<Side>("white");
  const [aiModel, setAiModel] = useState(models[0]);
  const [promptConfig, setPromptConfig] = useState({ systemInstructions: DEFAULT_SYSTEM, template: DEFAULT_TEMPLATE });
  const [status, setStatus] = useState("Ready to start a game.");
  const [waitingOnAI, setWaitingOnAI] = useState(false);
  const [starting, setStarting] = useState(false);
  const [inGame, setInGame] = useState(false);
  const [gameId, setGameId] = useState<string | null>(null);
  const [gameOverReason, setGameOverReason] = useState<string | null>(null);
  const [aiIllegalMoveCount, setAiIllegalMoveCount] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [conversation, setConversation] = useState<ConversationMessage[]>([]);
  const [selectedSquare, setSelectedSquare] = useState<Square | null>(null);
  const [moveHints, setMoveHints] = useState<Square[]>([]);
  const [boardWidth, setBoardWidth] = useState(540);
  const boardContainerRef = useRef<HTMLDivElement | null>(null);
  const inGameRef = useRef(inGame);
  const [promptDialogOpen, setPromptDialogOpen] = useState(false);

  useEffect(() => {
    const computeWidth = () => {
      const containerWidth = boardContainerRef.current?.clientWidth ?? window.innerWidth - 48;
      const maxBoard = inGame ? 900 : 920;
      const usableWidth = Math.max(0, containerWidth - 24); // leave room for borders/padding
      const nextWidth = Math.max(320, Math.min(usableWidth, maxBoard));
      setBoardWidth(nextWidth);
    };

    computeWidth();
    const observer = new ResizeObserver(() => computeWidth());
    const node = boardContainerRef.current;
    if (node) observer.observe(node);
    window.addEventListener("resize", computeWidth);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", computeWidth);
    };
  }, [inGame]);

  useEffect(() => {
    inGameRef.current = inGame;
  }, [inGame]);

  const resetSelection = () => {
    setSelectedSquare(null);
    setMoveHints([]);
  };

  const sideToMoveFromFen = (value: string): Side => {
    try {
      const chess = new Chess(value);
      return chess.turn() === "w" ? "white" : "black";
    } catch {
      return "white";
    }
  };

  const resetBoardToFen = (value: string) => {
    try {
      const next = new Chess(value);
      gameRef.current = next;
      setFen(next.fen());
      return true;
    } catch {
      setError("Received invalid FEN from backend.");
      return false;
    }
  };

  const concludeGame = (label: string) => {
    setStatus(label);
    setGameOverReason(label);
    setInGame(false);
    setWaitingOnAI(false);
    setSelectedSquare(null);
    setMoveHints([]);
    setGameId(null);
  };

  const finishFromResponse = (
    resp: { game_status?: string; status?: string; winner?: string | null; termination_reason?: string | null },
    aiMoveLabel?: string
  ) => {
    const done = (resp.game_status || resp.status) === "finished";
    if (!done) return false;
    let label = "Game finished";
    if (resp.winner === "human") label = "You won";
    else if (resp.winner === "ai") label = "AI won";
    else if (resp.winner === "draw") label = "Draw";
    if (resp.termination_reason) {
      label += ` (${resp.termination_reason.replace(/_/g, " ")})`;
    } else if (aiMoveLabel && resp.winner === "ai") {
      label += ` after ${aiMoveLabel}`;
    }
    concludeGame(label);
    return true;
  };

  const startGame = async (side: Side) => {
    setStarting(true);
    setHumanSide(side);
    setError(null);
    setSelectedSquare(null);
    setMoveHints([]);
    setGameOverReason(null);
    setAiIllegalMoveCount(0);
    setConversation([]);
    const fresh = new Chess();
    gameRef.current = fresh;
    setFen(fresh.fen());
    setStatus("Starting game...");
    setWaitingOnAI(true);
    try {
      const res = await createHumanGame({
        model: aiModel,
        prompt: { system_instructions: promptConfig.systemInstructions, template: promptConfig.template },
        human_plays: side
      });
      setConversation(res.conversation || []);
      const nextFen = res.fen_after_ai || res.current_fen || res.initial_fen || gameRef.current.fen();
      resetBoardToFen(nextFen);
      setGameId(res.human_game_id);
      setAiIllegalMoveCount(res.ai_illegal_move_count ?? 0);
      setInGame(true);
      const aiLabel = res.ai_move?.san || res.ai_move?.uci || undefined;
      if (!finishFromResponse(res, aiLabel)) {
        const humanToMove = sideToMoveFromFen(nextFen) === side;
        setWaitingOnAI(!humanToMove);
        if (aiLabel) {
          setStatus(`AI (${aiModel}) opened with ${aiLabel}`);
        } else {
          setStatus(humanToMove ? "Your move." : "AI thinking...");
        }
      }
    } catch (err) {
      console.error(err);
      setStatus("Failed to start game.");
      setError("Could not reach backend. Check API base and server logs.");
      setInGame(false);
      setWaitingOnAI(false);
      setGameId(null);
      resetBoardToFen(new Chess().fen());
    } finally {
      setStarting(false);
    }
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

  const canInteract = () => inGame && !waitingOnAI && !gameOverReason && !!gameId && isHumanTurn();

  const sendMoveToBackend = async (move: Move, rollbackFen: string, afterHumanFen: string) => {
    if (!gameId) {
      setWaitingOnAI(false);
      return;
    }
    try {
      const uci = `${move.from}${move.to}${move.promotion || ""}`;
      const res = await postHumanMove(gameId, { human_move: uci });
      setAiIllegalMoveCount(res.ai_illegal_move_count ?? 0);
      if (res.conversation) {
        setConversation(res.conversation);
      }
      const nextFen = res.fen_after_ai || res.current_fen || res.fen_after_human || afterHumanFen;
      resetBoardToFen(nextFen);
      const aiLabel = res.ai_move?.san || res.ai_move?.uci;
      if (!finishFromResponse(res, aiLabel)) {
        setStatus(aiLabel ? `AI (${aiModel}) played ${aiLabel}` : `AI (${aiModel}) moved`);
        setWaitingOnAI(false);
      }
    } catch (err) {
      console.error(err);
      if (!inGameRef.current) return;
      setError("Failed to submit move. Reverting.");
      setStatus("Move failed; reverted to previous position.");
      resetBoardToFen(rollbackFen);
      setWaitingOnAI(false);
    }
  };

  const attemptMove = (source: Square, target: Square) => {
    if (gameOverReason || !inGame || waitingOnAI || !isHumanTurn() || !gameId) return false;
    const game = gameRef.current;
    const rollbackFen = game.fen();
    const move = game.move({ from: source, to: target, promotion: "q" });
    if (move === null) {
      setStatus("Illegal move. Try again.");
      return false;
    }
    const afterHumanFen = game.fen();
    setFen(afterHumanFen);
    resetSelection();
    setStatus(`You played ${move.san}. Waiting for AI...`);
    setWaitingOnAI(true);
    void sendMoveToBackend(move, rollbackFen, afterHumanFen);
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
    () =>
      `POST /api/human-games -> /api/human-games/:id/move (model=${aiModel}, prompt=custom template with {FEN}/{SAN_HISTORY})`,
    [aiModel, promptConfig.template]
  );

  const resign = () => {
    if (!inGame) return;
    concludeGame("You resigned. Reset to play again.");
  };

  return (
    <>
      <div className="space-y-6 fade-in">
        <div className="flex flex-col gap-2">
          <p className="text-sm uppercase tracking-[0.3em] text-[var(--ink-500)]">Human vs LLM</p>
          <h1 className="text-3xl font-semibold text-[var(--ink-900)] font-display">Play a game</h1>
        <p className="text-[var(--ink-700)] text-sm">
          Moves are executed through the backend: games start at POST `/api/human-games` and each turn is sent to
          `/api/human-games/:gameId/move` to fetch the AI reply.
        </p>
        {error && <p className="text-sm text-red-500">{error}</p>}
      </div>

      {inGame && (
        <div className="flex justify-end">
          <button className="btn secondary" onClick={resign}>
            Resign
          </button>
        </div>
      )}

      <div
        className={clsx(
          "grid gap-6 items-start transition-all duration-500",
          inGame ? "md:grid-cols-[minmax(0,1.15fr)_minmax(340px,1fr)]" : "md:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)]"
        )}
      >
        <div
          className={clsx(
            "card p-4 flex flex-col gap-4 transition-all duration-500 w-full",
            inGame ? "md:p-7 lg:p-8 md:scale-[1.01] max-w-6xl mx-auto" : ""
          )}
        >
          <div
            ref={boardContainerRef}
            className={clsx("relative w-full overflow-hidden flex justify-center", inGame && "mx-auto max-w-6xl")}
          >
            <InteractiveBoard
              position={fen}
              boardOrientation={humanSide}
              onSquareClick={(square: Square) => onSquareClick(square)}
              animationDuration={200}
            arePiecesDraggable={false}
            boardWidth={boardWidth}
            customSquareStyles={squareStyles}
            customBoardStyle={{
              borderRadius: "16px",
              border: "1px solid var(--board-border)",
              boxShadow: "var(--board-shadow)",
              background: "var(--board-surface)",
              color: "var(--board-notation)",
              margin: "0 auto",
              maxWidth: "100%",
              width: `${boardWidth}px`,
              height: `${boardWidth}px`,
              boxSizing: "border-box"
            }}
            customLightSquareStyle={{ backgroundColor: "var(--board-light)" }}
            customDarkSquareStyle={{ backgroundColor: "var(--board-dark)" }}
            customNotationStyle={{
              color: "var(--board-notation)",
              fontWeight: 700,
              fontSize: 12,
              textShadow: "0 0 3px rgba(0,0,0,0.4), 0 0 2px rgba(255,255,255,0.15)"
            }}
          />
            {gameOverReason && (
              <div className="absolute inset-0 bg-[var(--overlay-bg)] backdrop-blur-[2px] flex items-center justify-center text-center px-6">
                <div className="space-y-3">
                  <p className="text-lg font-semibold text-[var(--ink-900)]">{gameOverReason}</p>
                  <button className="btn" onClick={() => startGame(humanSide)}>
                    Play again
                  </button>
                </div>
              </div>
            )}
          </div>
          <div className="flex flex-wrap gap-2 text-sm text-[var(--ink-700)]">
            <span className="chip">{status}</span>
            <span className={clsx("chip", waitingOnAI && "bg-accent text-canvas-900")}>
              {waitingOnAI ? "Waiting for AI" : "Your turn"}
            </span>
            {aiIllegalMoveCount > 0 && <span className="chip">AI illegal moves: {aiIllegalMoveCount}</span>}
          </div>
        </div>

        <div className={clsx("transition-all duration-500 w-full h-full space-y-4", inGame && "max-w-6xl mx-auto")}>
          {inGame ? (
            <ConversationThread
              messages={conversation}
              className="md:min-h-[500px] max-h-[70vh]"
              title="Conversation"
            />
          ) : (
            <>
              <div className="card transition-all duration-500 w-full p-5 space-y-4">
                <div className="space-y-4">
                  <p className="text-lg font-semibold text-[var(--ink-900)]">Configure the AI</p>
                  <div className="space-y-3">
                    <label className="text-sm text-[var(--ink-700)]">AI model</label>
                    <select
                      className="select-field w-full px-3 py-2 text-[var(--ink-900)] shadow-sm focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition"
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
                    <label className="text-sm text-[var(--ink-700)]">You play</label>
                    <div className="flex gap-2">
                      {(["white", "black"] as Side[]).map((side) => (
                        <button
                          key={side}
                          className={clsx(
                            "flex-1 rounded-xl px-4 py-2 border border-[var(--border-soft)]",
                            humanSide === side
                              ? "bg-accent text-canvas-900 shadow-sm"
                              : "bg-[var(--field-bg)] text-[var(--ink-700)]"
                          )}
                          onClick={() => setHumanSide(side)}
                        >
                          {side}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="space-y-3">
                    <label className="text-sm text-[var(--ink-700)]">Prompt</label>
                    <button
                      type="button"
                      className="btn secondary w-full justify-center"
                      onClick={() => setPromptDialogOpen(true)}
                    >
                      Edit prompt
                    </button>
                  </div>
                  <div className="flex gap-2">
                    <button className="btn flex-1" onClick={() => startGame(humanSide)} disabled={starting}>
                      {starting ? "Starting..." : "Start game"}
                    </button>
                  </div>
                  <p className="text-xs text-[var(--ink-500)]">{promptSummary}</p>
                </div>
              </div>
              {conversation.length > 0 && (
                <ConversationThread messages={conversation} className="md:min-h-[400px]" title="Conversation" />
              )}
            </>
          )}
        </div>
      </div>
      </div>
      <PromptDialog
        open={promptDialogOpen}
        systemInstructions={promptConfig.systemInstructions}
        template={promptConfig.template}
        onChange={(value) =>
          setPromptConfig((prev) => ({
            systemInstructions: value.systemInstructions ?? prev.systemInstructions,
            template: value.template ?? prev.template
          }))
        }
        onClose={() => setPromptDialogOpen(false)}
      />
    </>
  );
}

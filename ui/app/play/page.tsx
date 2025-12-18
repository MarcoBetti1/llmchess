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
const DEFAULT_SYSTEM_SAN = "You are a strong chess player. When asked for a move, provide only the best legal move in SAN.";
const DEFAULT_TEMPLATE_SAN = `{FEN}`;

type PromptState = { systemInstructions: string; template: string; expectedNotation: "san" | "uci" | "fen" };

type Side = "white" | "black";

export default function PlayPage() {
  const gameRef = useRef(new Chess());
  const [fen, setFen] = useState(gameRef.current.fen());
  const [humanSide, setHumanSide] = useState<Side>("white");
  const [aiModel, setAiModel] = useState(models[0]);
  const [promptConfig, setPromptConfig] = useState<PromptState>({
    systemInstructions: DEFAULT_SYSTEM_SAN,
    template: DEFAULT_TEMPLATE_SAN,
    expectedNotation: "san"
  });
  const [status, setStatus] = useState("Ready to start a game.");
  const [waitingOnAI, setWaitingOnAI] = useState(false);
  const [starting, setStarting] = useState(false);
  const [inGame, setInGame] = useState(false);
  const [gameId, setGameId] = useState<string | null>(null);
  const [gameOverReason, setGameOverReason] = useState<string | null>(null);
  const [lastMoveLabel, setLastMoveLabel] = useState<string | null>(null);
  const [aiIllegalMoveCount, setAiIllegalMoveCount] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [conversation, setConversation] = useState<ConversationMessage[]>([]);
  const [selectedSquare, setSelectedSquare] = useState<Square | null>(null);
  const [moveHints, setMoveHints] = useState<Square[]>([]);
  const [boardWidth, setBoardWidth] = useState(720);
  const boardContainerRef = useRef<HTMLDivElement | null>(null);
  const inGameRef = useRef(inGame);
  const [promptDialogOpen, setPromptDialogOpen] = useState(false);

  useEffect(() => {
    const computeWidth = () => {
      const containerWidth = boardContainerRef.current?.clientWidth ?? window.innerWidth - 64;
      const heightLimit = Math.max(420, (typeof window !== "undefined" ? window.innerHeight - 200 : 1200));
      const maxBoard = inGame ? 1100 : 1040;
      const baseWidth = Math.max(360, containerWidth - 16);
      const nextWidth = Math.min(baseWidth, maxBoard, heightLimit);
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
    setLastMoveLabel(null);
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
        prompt: {
          system_instructions: promptConfig.systemInstructions,
          template: promptConfig.template,
          expected_notation: promptConfig.expectedNotation
        },
        human_plays: side
      });
      setConversation(res.conversation || []);
      const nextFen = res.fen_after_ai || res.current_fen || res.initial_fen || gameRef.current.fen();
      resetBoardToFen(nextFen);
      setGameId(res.human_game_id);
      setAiIllegalMoveCount(res.ai_illegal_move_count ?? 0);
      setInGame(true);
      const aiLabel = res.ai_move?.san || res.ai_move?.uci || undefined;
      setLastMoveLabel(aiLabel || null);
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
      if (aiLabel) {
        setLastMoveLabel(aiLabel);
      }
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
    setLastMoveLabel(move.san);
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

  const resign = () => {
    if (!inGame) return;
    concludeGame("You resigned. Reset to play again.");
  };

  const chatHeight = Math.max(520, Math.round(boardWidth + 240));

  return (
    <>
        <div className="flex flex-col gap-6 fade-in">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="space-y-2">
              <p className="text-sm uppercase tracking-[0.3em] text-[var(--ink-500)]">Human vs LLM</p>
              <h1 className="text-3xl font-semibold text-[var(--ink-900)] font-display">Play a game</h1>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {inGame && (
                <button className="btn secondary" onClick={resign}>
                  Resign
                </button>
              )}
            </div>
        </div>

        {error && (
          <div className="glass border border-red-200 text-red-700 px-4 py-3 rounded-xl text-sm">
            {error}
          </div>
        )}

        <div className="grid items-start gap-5 lg:gap-6 xl:gap-8 lg:grid-cols-[minmax(700px,1.35fr)_minmax(480px,1fr)] xl:grid-cols-[minmax(840px,1.4fr)_minmax(520px,1fr)] min-h-[70vh]">
          <div className="card p-5 lg:p-6 xl:p-7 flex flex-col gap-5 h-full self-start">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="space-y-1">
                <p className="text-lg font-semibold text-[var(--ink-900)]">
                  {aiModel} ({humanSide === "white" ? "B" : "W"}
                  {lastMoveLabel ? `, ${lastMoveLabel}` : ""})
                </p>
                <p className="text-xs text-[var(--ink-600)]">
                  {status} • You play {humanSide} • {waitingOnAI ? "AI thinking" : "Your move"}
                  {aiIllegalMoveCount > 0 ? ` • AI illegal: ${aiIllegalMoveCount}` : ""}
                </p>
              </div>
              <div className="flex items-center gap-2">
                {inGame && <span className="chip text-xs">Live game</span>}
                {gameId && <span className="chip text-xs">Game {gameId.slice(0, 6)}...</span>}
              </div>
            </div>

            <div ref={boardContainerRef} className="relative flex-1 w-full">
              <div className="flex h-full w-full items-center justify-center p-3 md:p-4">
                <div className="relative" style={{ width: boardWidth, height: boardWidth }}>
                  <InteractiveBoard
                    position={fen}
                    boardOrientation={humanSide}
                    onSquareClick={(square: Square) => onSquareClick(square)}
                    animationDuration={200}
                    arePiecesDraggable={false}
                    boardWidth={boardWidth}
                    customSquareStyles={squareStyles}
                    customBoardStyle={{
                      borderRadius: "18px",
                      border: "1px solid var(--board-border)",
                      boxShadow: "var(--board-shadow)",
                      background: "var(--board-surface)",
                      color: "var(--board-notation)"
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
                    <div className="absolute inset-0 rounded-2xl bg-[var(--overlay-bg)] backdrop-blur-[2px] flex items-center justify-center text-center px-6">
                      <div className="space-y-3">
                        <p className="text-lg font-semibold text-[var(--ink-900)]">{gameOverReason}</p>
                        <button className="btn" onClick={() => startGame(humanSide)}>
                          Play again
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>

          </div>

          <div className="flex flex-col gap-4 h-full">
            {inGame ? (
              <ConversationThread
                messages={conversation}
                className="w-full"
                height="min-h-[520px]"
                title="Live conversation"
                /* Keep chat aligned with board height */
                styleOverride={{ minHeight: chatHeight, maxHeight: chatHeight }}
              />
            ) : (
              <div className="card transition-all duration-500 w-full p-5 lg:p-6 space-y-5 h-full self-start">
                <div className="flex items-start justify-between gap-3">
                  <div className="space-y-1">
                    <p className="text-lg font-semibold text-[var(--ink-900)]">Configure the AI</p>
                    <p className="text-sm text-[var(--ink-500)]">Pick a model, choose your color, and adjust the prompt.</p>
                  </div>
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
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
                        "flex-1 rounded-xl px-4 py-3 border border-[var(--border-soft)] transition",
                        humanSide === side
                          ? "bg-accent text-canvas-900 shadow-sm"
                          : "bg-[var(--field-bg)] text-[var(--ink-700)] hover:border-[var(--border-strong)]"
                      )}
                      onClick={() => setHumanSide(side)}
                    >
                      {side === "white" ? "White" : "Black"}
                    </button>
                  ))}
                </div>
              </div>
            </div>
                <div className="space-y-3">
                  <label className="text-sm text-[var(--ink-700)]">Prompt</label>
                  <div className="rounded-xl border border-[var(--border-soft)] bg-[var(--surface-weak)]/80 p-3 space-y-2">
                    <p className="text-xs text-[var(--ink-500)] line-clamp-2">{promptConfig.systemInstructions}</p>
                    <button
                      type="button"
                      className="btn secondary w-full justify-center"
                      onClick={() => setPromptDialogOpen(true)}
                    >
                      Edit prompt
                    </button>
                  </div>
                </div>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <button className="btn" onClick={() => startGame(humanSide)} disabled={starting}>
                    {starting ? "Starting..." : "Start game"}
                  </button>
                </div>
                {conversation.length > 0 && (
                  <div className="space-y-3 pt-2">
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-semibold text-[var(--ink-900)]">Last conversation</p>
                      <span className="chip text-xs">{conversation.length} msgs</span>
                    </div>
                    <ConversationThread
                      messages={conversation}
                      className="w-full"
                      height="min-h-[260px]"
                      styleOverride={{ maxHeight: 360 }}
                      title="Previous"
                    />
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
      <PromptDialog
        open={promptDialogOpen}
        systemInstructions={promptConfig.systemInstructions}
        template={promptConfig.template}
        expectedNotation={promptConfig.expectedNotation}
        onChange={(value) =>
          setPromptConfig((prev) => ({
            systemInstructions: value.systemInstructions ?? prev.systemInstructions,
            template: value.template ?? prev.template,
            expectedNotation: value.expectedNotation ?? prev.expectedNotation
          }))
        }
        onClose={() => setPromptDialogOpen(false)}
      />
    </>
  );
}

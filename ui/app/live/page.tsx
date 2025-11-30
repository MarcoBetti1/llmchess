"use client";

import { useEffect, useMemo, useState } from "react";
import { ConversationLog, GameSummary } from "@/types";
import { fetchGameConversation, fetchLiveGames, subscribeToGameStream } from "@/lib/api";
import { GameCard } from "@/components/game-card";
import { ConversationDialog } from "@/components/conversation-dialog";

export default function LiveGamesPage() {
  const [games, setGames] = useState<GameSummary[]>([]);
  const [conversation, setConversation] = useState<ConversationLog | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchLiveGames()
      .then(setGames)
      .catch((err) => {
        console.error(err);
        setError("Failed to load live games. Check NEXT_PUBLIC_API_BASE or enable mocks.");
      });
  }, []);

  useEffect(() => {
    const unsubscribe = subscribeToGameStream((update) => {
      setGames((prev) => {
        const map = new Map(prev.map((g) => [g.game_id, g]));
        const existing = map.get(update.game_id);
        map.set(update.game_id, { ...(existing || ({} as GameSummary)), ...update } as GameSummary);
        return Array.from(map.values());
      });
    });
    return unsubscribe;
  }, []);

  const runningCount = useMemo(
    () => games.filter((g) => g.status === "running").length,
    [games]
  );

  const handleConversation = async (gameId: string) => {
    setDialogOpen(true);
    try {
      const data = await fetchGameConversation(gameId);
      setConversation(data);
    } catch (err) {
      console.error(err);
      setConversation(null);
      setError("Failed to load conversation for this game.");
    }
  };

  return (
    <div className="space-y-6 fade-in">
      <div className="flex flex-col gap-2">
        <p className="text-sm uppercase tracking-[0.3em] text-white/60">Live monitor</p>
        <h1 className="text-3xl font-semibold text-white font-display">LLM vs LLM games in flight</h1>
        <p className="text-white/70 text-sm">
          Fetched from `/api/games/live` with SSE updates from `/api/stream/games`. Running now:{" "}
          <strong className="text-white">{runningCount}</strong>
        </p>
        {error && <p className="text-sm text-red-300">{error}</p>}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {games.map((game) => (
          <GameCard
            key={game.game_id}
            game={game}
            onConversation={handleConversation}
          />
        ))}
      </div>

      <ConversationDialog open={dialogOpen} onClose={() => setDialogOpen(false)} log={conversation} />
    </div>
  );
}

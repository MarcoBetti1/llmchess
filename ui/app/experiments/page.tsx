"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { ExperimentResults, ExperimentSummary } from "@/types";
import { createExperiment, fetchExperimentResults, fetchExperiments } from "@/lib/api";
import { ProgressBar } from "@/components/progress-bar";
import { LiveBoard } from "@/components/live-board";
import { PromptDialog } from "@/components/prompt-dialog";

const modelOptions = [
  "openai/gpt-4o",
  "anthropic/claude-4.5",
  "openai/gpt-4o-mini",
  "meta/llama-3.1-70b",
  "mistral-large"
];

export default function ExperimentsPage() {
  const [experiments, setExperiments] = useState<ExperimentSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [results, setResults] = useState<ExperimentResults | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showAllExperiments, setShowAllExperiments] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [liveMode, setLiveMode] = useState(false);
  const [liveBoardCount, setLiveBoardCount] = useState(2);
  const [promptDialogOpen, setPromptDialogOpen] = useState(false);
  const pollExperimentsRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollResultsRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [form, setForm] = useState({
    name: "gpt4o_vs_claude",
    playerA: modelOptions[0],
    playerB: modelOptions[1],
    total: 4,
    aAsWhite: 2,
    promptMode: "fen+plaintext"
  });

  useEffect(() => {
    const load = () =>
      fetchExperiments()
        .then(setExperiments)
        .catch((err) => {
          console.error(err);
          setError("Failed to fetch experiments. Check NEXT_PUBLIC_API_BASE or enable mocks.");
        });
    load();
    pollExperimentsRef.current = setInterval(load, 4000);
    return () => {
      if (pollExperimentsRef.current) clearInterval(pollExperimentsRef.current);
    };
  }, []);

  // auto-select a running experiment if none selected
  useEffect(() => {
    if (selectedId) return;
    const running = experiments.find((e) => e.status === "running") || experiments[0];
    if (running) setSelectedId(running.experiment_id);
  }, [experiments, selectedId]);

  useEffect(() => {
    if (!selectedId) return;
    const load = () =>
      fetchExperimentResults(selectedId)
        .then(setResults)
        .catch((err) => {
          console.error(err);
          // If an experiment isn't found (e.g., fresh start with no runs), just clear results without surfacing an error.
          setResults(null);
        });
    load();
    pollResultsRef.current = setInterval(load, 5000);
    return () => {
      if (pollResultsRef.current) clearInterval(pollResultsRef.current);
    };
  }, [selectedId]);

  const selectedExperiment = useMemo(
    () => experiments.find((exp) => exp.experiment_id === selectedId),
    [experiments, selectedId]
  );

  const handleSubmit = async (evt: FormEvent) => {
    evt.preventDefault();
    setSubmitting(true);
    setError(null);
    const payload = {
      name: form.name,
      players: { a: { model: form.playerA }, b: { model: form.playerB } },
      games: { total: form.total, a_as_white: form.aAsWhite, b_as_white: Math.max(form.total - form.aAsWhite, 0) },
      prompt: { mode: form.promptMode as any, instruction_template_id: "san_only_default" }
    } as const;

    try {
      const { experiment_id } = await createExperiment(payload);
      const optimistic: ExperimentSummary = {
        experiment_id,
        name: form.name,
        status: "queued",
        players: { a: { model: form.playerA }, b: { model: form.playerB } },
        games: { total: form.total, completed: 0 },
        wins: { player_a: 0, player_b: 0, draws: 0 }
      };
      setExperiments((prev) => {
        const filtered = prev.filter((p) => p.experiment_id !== experiment_id);
        return [optimistic, ...filtered];
      });
      setSelectedId(experiment_id);
      setResults(null);
    } catch (err) {
      console.error(err);
      setError("Failed to start experiment. Check backend logs and NEXT_PUBLIC_API_BASE.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
    <div className="space-y-8 fade-in">
      <div className="flex flex-col gap-2">
        <p className="text-sm uppercase tracking-[0.3em] text-[var(--ink-500)]">Game master</p>
        <h1 className="text-3xl font-semibold text-[var(--ink-900)] font-display">Run and watch games</h1>
        <p className="text-[var(--ink-700)] text-sm">
          Start batches of games and monitor them live. POST `/api/experiments` on submit and poll `/api/experiments/:id/results`.
        </p>
        {error && <p className="text-sm text-red-500">{error}</p>}
      </div>

      <div className="card p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="section-title">New games</h2>
          <button className="btn secondary" onClick={() => setShowAdvanced((v) => !v)}>
            {showAdvanced ? "Hide extras" : "More settings"}
          </button>
        </div>
        <form className="grid gap-4 md:grid-cols-4" onSubmit={handleSubmit}>
          <div className="space-y-2">
            <label className="text-sm text-[var(--ink-700)]">Player A model</label>
            <select
              className="w-full rounded-xl bg-[var(--field-bg)] border border-[var(--border-soft)] px-3 py-2 text-[var(--ink-900)]/90"
              value={form.playerA}
              onChange={(e) => setForm((f) => ({ ...f, playerA: e.target.value }))}
            >
              {modelOptions.map((opt) => (
                <option key={opt} value={opt}>
                  {opt}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-2">
            <label className="text-sm text-[var(--ink-700)]">Player B model</label>
            <select
              className="w-full rounded-xl bg-[var(--field-bg)] border border-[var(--border-soft)] px-3 py-2 text-[var(--ink-900)]/90"
              value={form.playerB}
              onChange={(e) => setForm((f) => ({ ...f, playerB: e.target.value }))}
            >
              {modelOptions.map((opt) => (
                <option key={opt} value={opt}>
                  {opt}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-2">
            <label className="text-sm text-[var(--ink-700)]">Games total</label>
            <input
              type="number"
              min={2}
              className="w-full rounded-xl bg-[var(--field-bg)] border border-[var(--border-soft)] px-3 py-2 text-[var(--ink-900)]/90"
              value={form.total}
              onChange={(e) => setForm((f) => ({ ...f, total: Number(e.target.value) }))}
            />
          </div>
          <div className="flex items-end">
            <button className="btn w-full" type="submit" disabled={submitting}>
              {submitting ? "Scheduling..." : "Start games"}
            </button>
          </div>

          {showAdvanced && (
            <>
              <div className="space-y-2">
                <label className="text-sm text-[var(--ink-700)]">Experiment name</label>
                <input
                  className="w-full rounded-xl bg-[var(--field-bg)] border border-[var(--border-soft)] px-3 py-2 text-[var(--ink-900)]/90"
                  value={form.name}
                  onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm text-[var(--ink-700)]">Prompt</label>
                <button className="btn secondary w-full justify-center" onClick={() => setPromptDialogOpen(true)}>
                  Edit prompt
                </button>
              </div>
              <div className="space-y-2">
                <label className="text-sm text-[var(--ink-700)]">Player A as white</label>
                <input
                  type="number"
                  min={0}
                  className="w-full rounded-xl bg-[var(--field-bg)] border border-[var(--border-soft)] px-3 py-2 text-[var(--ink-900)]/90"
                  value={form.aAsWhite}
                  onChange={(e) => setForm((f) => ({ ...f, aAsWhite: Number(e.target.value) }))}
                />
              </div>
            </>
          )}
        </form>
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="section-title">Experiments</h2>
          <button className="btn secondary" onClick={() => setShowAllExperiments((v) => !v)}>
            {showAllExperiments ? "Show fewer" : "Show all"}
          </button>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          {(showAllExperiments ? experiments : experiments.slice(0, 1)).map((exp) => {
            const progress = (exp.games.completed / exp.games.total) * 100;
            return (
              <div
                key={exp.experiment_id}
                className="card p-5 hover:border-accent/50 transition-colors cursor-pointer"
                onClick={() => setSelectedId(exp.experiment_id)}
              >
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <p className="text-sm text-[var(--ink-500)]">{exp.experiment_id}</p>
                    <p className="text-lg font-semibold text-[var(--ink-900)]">
                      {exp.players.a.model} vs {exp.players.b.model}
                    </p>
                  </div>
                  <span className="chip">{exp.status}</span>
                </div>
                <ProgressBar value={progress} />
                <div className="mt-3 flex flex-wrap gap-2 text-sm text-[var(--ink-700)]">
                  <span className="chip">
                    Completed <strong className="ml-1 text-[var(--ink-900)]">{exp.games.completed}</strong> /{" "}
                    {exp.games.total}
                  </span>
                  {exp.wins && (
                    <span className="chip">
                      Wins A/B/D: {exp.wins.player_a}/{exp.wins.player_b}/{exp.wins.draws}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {selectedExperiment && (
        <div className="card p-5 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3 flex-wrap">
              <h3 className="text-xl font-semibold text-[var(--ink-900)]">
                {selectedExperiment.players.a.model} vs {selectedExperiment.players.b.model} -{" "}
                {selectedExperiment.games.total} games
              </h3>
              <span className="chip">{selectedExperiment.status}</span>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <button className="btn secondary" onClick={() => setLiveMode((v) => !v)}>
                {liveMode ? "Back to dashboard" : "Watch chess"}
              </button>
              {liveMode && (
                <div className="flex items-center gap-2 text-sm text-[var(--ink-700)]">
                  <span className="chip">Boards</span>
                  {[1, 2, 4].map((n) => (
                    <button
                      key={n}
                      className={`chip ${liveBoardCount === n ? "bg-accent text-canvas-900" : ""}`}
                      onClick={() => setLiveBoardCount(n)}
                    >
                      {n}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
          {!liveMode && (
            <>
              <div className="grid gap-3 md:grid-cols-3 text-sm text-[var(--ink-700)]">
                <div className="glass rounded-xl p-3 border border-[var(--border-soft)]">
                  <p className="text-[var(--ink-900)] text-lg font-semibold">
                    {results?.wins.player_a ?? selectedExperiment.wins?.player_a ?? 0}
                  </p>
                  <p className="text-[var(--ink-500)]">
                    Player A wins{" "}
                    <span className="text-[var(--ink-500)] block text-xs">
                      {selectedExperiment.players.a.model}
                    </span>
                  </p>
                </div>
                <div className="glass rounded-xl p-3 border border-[var(--border-soft)]">
                  <p className="text-[var(--ink-900)] text-lg font-semibold">
                    {results?.wins.player_b ?? selectedExperiment.wins?.player_b ?? 0}
                  </p>
                  <p className="text-[var(--ink-500)]">
                    Player B wins{" "}
                    <span className="text-[var(--ink-500)] block text-xs">
                      {selectedExperiment.players.b.model}
                    </span>
                  </p>
                </div>
                <div className="glass rounded-xl p-3 border border-[var(--border-soft)]">
                  <p className="text-[var(--ink-900)] text-lg font-semibold">
                    {results?.wins.draws ?? selectedExperiment.wins?.draws ?? 0}
                  </p>
                  <p className="text-[var(--ink-500)]">Draws</p>
                </div>
              </div>
              {results?.games?.length ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm text-left text-[var(--ink-700)]">
                    <thead className="text-[var(--ink-500)] uppercase text-xs tracking-wide">
                      <tr>
                        <th className="py-2">Game ID</th>
                        <th className="py-2">White</th>
                        <th className="py-2">Black</th>
                        <th className="py-2">Result</th>
                        <th className="py-2">Illegal</th>
                      </tr>
                    </thead>
                    <tbody>
                      {results.games.map((g) => (
                        <tr key={g.game_id} className="border-t border-white/5">
                          <td className="py-2">{g.game_id}</td>
                          <td className="py-2">{g.white_model}</td>
                          <td className="py-2">{g.black_model}</td>
                          <td className="py-2 capitalize">{g.winner || "running"}</td>
                          <td className="py-2">{g.illegal_moves}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-[var(--ink-500)] text-sm">No per-game rows yet.</p>
              )}
            </>
          )}
          {liveMode && (
            <LiveBoardsPanel
              experimentId={selectedExperiment.experiment_id}
              games={results?.games || []}
              count={liveBoardCount}
            />
          )}
        </div>
      )}
    </div>
    <PromptDialog
      open={promptDialogOpen}
      mode={form.promptMode as any}
      onModeChange={(value) => setForm((f) => ({ ...f, promptMode: value }))}
      onClose={() => setPromptDialogOpen(false)}
    />
    </>
  );
}

function LiveBoardsPanel({
  experimentId,
  games,
  count
}: {
  experimentId: string;
  games: ExperimentResults["games"];
  count: number;
}) {
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  useEffect(() => {
    const defaults = (games || []).slice(0, count).map((g) => g.game_id);
    setSelectedIds((prev) => {
      const filtered = prev.filter((id) => defaults.includes(id));
      const fill = [...filtered, ...defaults.filter((id) => !filtered.includes(id))].slice(0, count);
      return fill;
    });
  }, [games, count]);

  if (!games?.length) {
    return <p className="text-[var(--ink-500)] text-sm">No games yet to display. Wait for games to start.</p>;
  }

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      if (prev.includes(id)) {
        return prev.filter((x) => x !== id);
      }
      const next = [...prev, id];
      if (next.length > count) {
        next.splice(0, next.length - count);
      }
      return next;
    });
  };

  const baseSize = 520; // larger baseline
  const boardSize = count === 1 ? baseSize * 2 : baseSize;
  const displayIds = selectedIds.length ? selectedIds.slice(0, count) : (games || []).slice(0, count).map((g) => g.game_id);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2 items-center">
        <p className="text-[var(--ink-700)] text-sm">
          Watching {Math.min(count, games.length)} board{count > 1 ? "s" : ""} from {experimentId}
        </p>
        <span className="text-[var(--ink-500)] text-xs">(select up to {count} game{count > 1 ? "s" : ""})</span>
      </div>
      <div className="flex flex-wrap gap-2">
        {games.map((g) => (
          <button
            key={g.game_id}
            className={`chip ${displayIds.includes(g.game_id) ? "bg-accent text-canvas-900" : ""}`}
            onClick={() => toggleSelect(g.game_id)}
          >
            {g.game_id} ┬╖ {g.white_model} vs {g.black_model}
          </button>
        ))}
      </div>
      <div className={`grid gap-4 ${count >= 2 ? "md:grid-cols-2" : "md:grid-cols-1"}`}>
        {displayIds.slice(0, count).map((gameId) => {
          const meta = games.find((g) => g.game_id === gameId);
          if (!meta) return null;
          return (
            <LiveBoard
              key={gameId}
              gameId={gameId}
              whiteModel={meta.white_model}
              blackModel={meta.black_model}
              size={boardSize}
            />
          );
        })}
      </div>
    </div>
  );
}

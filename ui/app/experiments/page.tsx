"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { ExperimentResults, ExperimentSummary } from "@/types";
import { createExperiment, fetchExperimentResults, fetchExperiments } from "@/lib/api";
import { ProgressBar } from "@/components/progress-bar";

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
  const pollExperimentsRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollResultsRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [form, setForm] = useState({
    name: "gpt4o_vs_claude",
    playerA: modelOptions[0],
    playerB: modelOptions[1],
    total: 20,
    aAsWhite: 10,
    promptMode: "fen+plaintext",
    illegalLimit: 3
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

  useEffect(() => {
    if (!selectedId) return;
    const load = () =>
      fetchExperimentResults(selectedId)
        .then(setResults)
        .catch((err) => {
          console.error(err);
          setError("Failed to fetch experiment results.");
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
      prompt: { mode: form.promptMode as any, instruction_template_id: "san_only_default" },
      illegal_move_limit: form.illegalLimit
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
    <div className="space-y-8 fade-in">
      <div className="flex flex-col gap-2">
        <p className="text-sm uppercase tracking-[0.3em] text-white/60">Experiment lab</p>
        <h1 className="text-3xl font-semibold text-white font-display">Model tournaments</h1>
        <p className="text-white/70 text-sm">
          Start a batch of games and monitor progress. POST `/api/experiments` on submit, poll
          `/api/experiments/:id/status` or subscribe to `/api/stream/experiments/:id`.
        </p>
        {error && <p className="text-sm text-red-300">{error}</p>}
      </div>

      <div className="card p-6">
        <h2 className="section-title mb-4">New experiment</h2>
        <form className="grid gap-4 md:grid-cols-4" onSubmit={handleSubmit}>
          <div className="md:col-span-2 space-y-2">
            <label className="text-sm text-white/70">Experiment name</label>
            <input
              className="w-full rounded-xl bg-white/5 border border-white/10 px-3 py-2 text-white/90"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              required
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm text-white/70">Player A model</label>
            <select
              className="w-full rounded-xl bg-white/5 border border-white/10 px-3 py-2 text-white/90"
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
            <label className="text-sm text-white/70">Player B model</label>
            <select
              className="w-full rounded-xl bg-white/5 border border-white/10 px-3 py-2 text-white/90"
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
            <label className="text-sm text-white/70">Prompt mode</label>
            <select
              className="w-full rounded-xl bg-white/5 border border-white/10 px-3 py-2 text-white/90"
              value={form.promptMode}
              onChange={(e) => setForm((f) => ({ ...f, promptMode: e.target.value }))}
            >
              <option value="plaintext">plaintext</option>
              <option value="fen">fen</option>
              <option value="fen+plaintext">fen+plaintext</option>
            </select>
          </div>
          <div className="space-y-2">
            <label className="text-sm text-white/70">Games total</label>
            <input
              type="number"
              min={2}
              className="w-full rounded-xl bg-white/5 border border-white/10 px-3 py-2 text-white/90"
              value={form.total}
              onChange={(e) => setForm((f) => ({ ...f, total: Number(e.target.value) }))}
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm text-white/70">Player A as white</label>
            <input
              type="number"
              min={0}
              className="w-full rounded-xl bg-white/5 border border-white/10 px-3 py-2 text-white/90"
              value={form.aAsWhite}
              onChange={(e) => setForm((f) => ({ ...f, aAsWhite: Number(e.target.value) }))}
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm text-white/70">Illegal move limit</label>
            <input
              type="number"
              min={1}
              className="w-full rounded-xl bg-white/5 border border-white/10 px-3 py-2 text-white/90"
              value={form.illegalLimit}
              onChange={(e) => setForm((f) => ({ ...f, illegalLimit: Number(e.target.value) }))}
            />
          </div>
          <div className="flex items-end">
            <button className="btn w-full" type="submit" disabled={submitting}>
              {submitting ? "Scheduling..." : "Start experiment"}
            </button>
          </div>
        </form>
      </div>

      <div className="space-y-3">
        <h2 className="section-title">Experiments</h2>
        <div className="grid gap-3 md:grid-cols-2">
          {experiments.map((exp) => {
            const progress = (exp.games.completed / exp.games.total) * 100;
            return (
              <div
                key={exp.experiment_id}
                className="card p-5 hover:border-accent/50 transition-colors cursor-pointer"
                onClick={() => setSelectedId(exp.experiment_id)}
              >
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <p className="text-sm text-white/60">{exp.experiment_id}</p>
                    <p className="text-lg font-semibold text-white">
                      {exp.players.a.model} vs {exp.players.b.model}
                    </p>
                  </div>
                  <span className="chip">{exp.status}</span>
                </div>
                <ProgressBar value={progress} />
                <div className="mt-3 flex flex-wrap gap-2 text-sm text-white/70">
                  <span className="chip">
                    Completed <strong className="ml-1 text-white">{exp.games.completed}</strong> /{" "}
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
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-white/60 uppercase tracking-[0.25em]">Experiment detail</p>
              <h3 className="text-xl font-semibold text-white">
                {selectedExperiment.players.a.model} vs {selectedExperiment.players.b.model} —{" "}
                {selectedExperiment.games.total} games
              </h3>
            </div>
            <span className="chip">{selectedExperiment.status}</span>
          </div>
          <div className="grid gap-3 md:grid-cols-3 text-sm text-white/80">
            <div className="glass rounded-xl p-3 border border-white/10">
              <p className="text-white text-lg font-semibold">
                {results?.wins.player_a ?? selectedExperiment.wins?.player_a ?? 0}
              </p>
              <p className="text-white/60">Player A wins</p>
            </div>
            <div className="glass rounded-xl p-3 border border-white/10">
              <p className="text-white text-lg font-semibold">
                {results?.wins.player_b ?? selectedExperiment.wins?.player_b ?? 0}
              </p>
              <p className="text-white/60">Player B wins</p>
            </div>
            <div className="glass rounded-xl p-3 border border-white/10">
              <p className="text-white text-lg font-semibold">
                {results?.wins.draws ?? selectedExperiment.wins?.draws ?? 0}
              </p>
              <p className="text-white/60">Draws</p>
            </div>
          </div>
          {results?.games?.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left text-white/80">
                <thead className="text-white/60 uppercase text-xs tracking-wide">
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
            <p className="text-white/60 text-sm">No per-game rows yet.</p>
          )}
        </div>
      )}
    </div>
  );
}

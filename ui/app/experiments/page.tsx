"use client";

import clsx from "clsx";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { ExperimentResults, ExperimentSummary } from "@/types";
import { cancelExperiment, createExperiment, deleteExperiment, fetchExperimentResults, fetchExperiments } from "@/lib/api";
import { ProgressBar } from "@/components/progress-bar";
import { LiveBoard } from "@/components/live-board";
import { PromptDialog } from "@/components/prompt-dialog";

const modelOptions = [
  "openai/gpt-5-chat",
  "openai/gpt-5-mini",
  "openai/gpt-5.1-thinking",
  "openai/gpt-5.1-instant",
  "openai/gpt-4o",
  "openai/gpt-4.1",
  "anthropic/claude-3.7-sonnet",
  "anthropic/claude-haiku-4.5",
  "anthropic/claude-opus-4.5",
  "google/gemini-2.5-pro",
  "google/gemini-2.5-flash",
  "mistral/mistral-large-3"
];

const DEFAULT_SYSTEM = "You are a strong chess player. When asked for a move, provide only the best legal move in SAN.";
const DEFAULT_TEMPLATE = `Position (FEN): {FEN}
Respond with only your best legal move in SAN.`;

export default function ExperimentsPage() {
  const [experiments, setExperiments] = useState<ExperimentSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [results, setResults] = useState<ExperimentResults | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showAllExperiments, setShowAllExperiments] = useState(false);
  const [liveMode, setLiveMode] = useState(false);
  const [liveBoardCount, setLiveBoardCount] = useState(4);
  const [promptDialogOpen, setPromptDialogOpen] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [cancellingId, setCancellingId] = useState<string | null>(null);
  const pollExperimentsRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollResultsRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const deriveName = (a: string, b: string, total: number) =>
    `${a.split("/").pop() || a}_vs_${b.split("/").pop() || b}_${total}`.replace(/\s+/g, "_");
  const [form, setForm] = useState({
    playerA: modelOptions[0],
    playerB: modelOptions[1],
    total: 4,
    aAsWhite: 2,
    name: deriveName(modelOptions[0], modelOptions[1], 4),
    prompt: { system_instructions: DEFAULT_SYSTEM, template: DEFAULT_TEMPLATE }
  });

  useEffect(() => {
    const load = () =>
      fetchExperiments()
        .then((exps) => exps ? exps.slice().reverse() : [])
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

  const displayedExperiments = useMemo(() => {
    const selected = selectedId ? experiments.find((e) => e.experiment_id === selectedId) : null;
    const rest = experiments.filter((e) => e.experiment_id !== selectedId);
    const ordered = selected ? [selected, ...rest] : rest;
    if (showAllExperiments) return ordered;
    return ordered.slice(0, 4);
  }, [experiments, showAllExperiments, selectedId]);

  const handleSubmit = async (evt: FormEvent) => {
    evt.preventDefault();
    setSubmitting(true);
    setError(null);
    const payload = {
      name: form.name,
      players: { a: { model: form.playerA }, b: { model: form.playerB } },
      games: { total: form.total, a_as_white: form.aAsWhite, b_as_white: Math.max(form.total - form.aAsWhite, 0) },
      prompt: { system_instructions: form.prompt.system_instructions, template: form.prompt.template }
    } as const;

    try {
      const { experiment_id, name, log_dir_name } = await createExperiment(payload);
      const displayName = name || form.name;
      const optimistic: ExperimentSummary = {
        experiment_id,
        name: displayName,
        log_dir_name: log_dir_name || experiment_id,
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
      setError(err instanceof Error ? err.message : "Failed to start experiment. Check backend logs and NEXT_PUBLIC_API_BASE.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (exp: ExperimentSummary) => {
    const label = exp.name || exp.experiment_id;
    if (!confirm(`Delete experiment "${label}" and its logs? This cannot be undone.`)) return;
    setError(null);
    setDeletingId(exp.experiment_id);
    try {
      await deleteExperiment(exp.experiment_id);
      setExperiments((prev) => {
        const filtered = prev.filter((p) => p.experiment_id !== exp.experiment_id);
        if (selectedId === exp.experiment_id) {
          const next = filtered[0]?.experiment_id ?? null;
          setSelectedId(next);
          setResults(null);
        }
        return filtered;
      });
    } catch (err) {
      console.error(err);
      setError(err instanceof Error ? err.message : "Failed to delete experiment. Check backend logs and NEXT_PUBLIC_API_BASE.");
    } finally {
      setDeletingId(null);
    }
  };

  const handleCancel = async (exp: ExperimentSummary) => {
    if (exp.status === "cancelled" || exp.status === "finished") return;
    setError(null);
    setCancellingId(exp.experiment_id);
    try {
      await cancelExperiment(exp.experiment_id);
      setExperiments((prev) =>
        prev.map((e) => (e.experiment_id === exp.experiment_id ? { ...e, status: "cancelled" } : e))
      );
      if (selectedId === exp.experiment_id) {
        setResults(null);
      }
    } catch (err) {
      console.error(err);
      setError(err instanceof Error ? err.message : "Failed to cancel experiment. Check backend logs and NEXT_PUBLIC_API_BASE.");
    } finally {
      setCancellingId(null);
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
        </div>
        <form className="grid gap-4 md:grid-cols-4" onSubmit={handleSubmit}>
          <div className="space-y-2">
            <label className="text-sm text-[var(--ink-700)]">Player A model</label>
            <select
              className="select-field w-full px-3 py-2 text-[var(--ink-900)] shadow-sm focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition"
              value={form.playerA}
              onChange={(e) =>
                setForm((f) => {
                  const playerA = e.target.value;
                  return { ...f, playerA, name: deriveName(playerA, f.playerB, f.total) };
                })
              }
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
              className="select-field w-full px-3 py-2 text-[var(--ink-900)] shadow-sm focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition"
              value={form.playerB}
              onChange={(e) =>
                setForm((f) => {
                  const playerB = e.target.value;
                  return { ...f, playerB, name: deriveName(f.playerA, playerB, f.total) };
                })
              }
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
              onChange={(e) =>
                setForm((f) => {
                  const total = Number(e.target.value);
                  const aAsWhite = Math.ceil(total / 2);
                  return { ...f, total, aAsWhite, name: deriveName(f.playerA, f.playerB, total) };
                })
              }
            />
          </div>
          <div className="flex items-end">
            <button className="btn w-full" type="submit" disabled={submitting}>
              {submitting ? "Scheduling..." : "Start games"}
            </button>
          </div>

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
            <button
              type="button"
              className="btn secondary w-full justify-center"
              onClick={() => setPromptDialogOpen(true)}
            >
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
        </form>
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="section-title">Experiments</h2>
          <button className="btn secondary" onClick={() => setShowAllExperiments((v) => !v)}>
            {showAllExperiments ? "Show fewer" : "Show all"}
          </button>
        </div>
        <div className="grid gap-3 md:grid-cols-4 items-stretch">
          {displayedExperiments.map((exp) => {
            const displayName = exp.name || exp.experiment_id;
            const folderName = exp.log_dir_name || exp.experiment_id;
            const isSelected = selectedId === exp.experiment_id;
            const total = exp.games?.total ?? 0;
            const completed = exp.games?.completed ?? 0;
            const winsA = exp.wins?.player_a ?? 0;
            const winsB = exp.wins?.player_b ?? 0;
            const draws = exp.wins?.draws ?? 0;
            const totalFinished = Math.max(1, completed || total || winsA + winsB + draws);
            const pctA = Math.round((winsA / totalFinished) * 100);
            const pctB = Math.round((winsB / totalFinished) * 100);
            const shortName = (m: string) => m.split("/").pop() || m;
            const decided = completed === total && total > 0;
            const winner =
              decided && winsA !== winsB ? (winsA > winsB ? "a" : "b") : null;
            const classFor = (side: "a" | "b") => {
              if (winner === side) return "border-emerald-500/50 bg-emerald-900/30 text-emerald-100";
              if (winner && winner !== side) return "border-red-500/40 bg-red-900/30 text-red-100";
              return "border-[var(--border-soft)] bg-[var(--surface-weak)] text-[var(--ink-900)]";
            };
            return (
              <div
                key={exp.experiment_id}
                className={clsx(
                  "card p-5 transition-all duration-300 ease-out cursor-pointer border h-full flex flex-col gap-3 min-h-[230px]",
                  isSelected ? "border-accent bg-accent/5" : "border-[var(--border-soft)] hover:border-accent/50"
                )}
                style={
                  isSelected
                    ? { boxShadow: "0 0 0 2px rgba(124,231,172,0.9), 0 14px 40px rgba(124,231,172,0.28)" }
                    : undefined
                }
                onClick={() => setSelectedId(exp.experiment_id)}
            >
              <div className="flex items-start justify-between mb-3">
                <div>
                  <p className="text-sm text-[var(--ink-500)] break-words leading-tight line-clamp-2 min-h-[32px]">
                    {displayName}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {(exp.status === "running" || exp.status === "queued") && (
                    <button
                      type="button"
                      className="p-2 rounded-lg hover:bg-[var(--field-bg)] text-[var(--ink-500)] disabled:opacity-50"
                      aria-label={`Cancel experiment ${displayName}`}
                      title="Cancel experiment"
                      disabled={cancellingId === exp.experiment_id}
                      onClick={(evt) => {
                        evt.stopPropagation();
                        handleCancel(exp);
                      }}
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.6">
                        <path strokeLinecap="round" strokeLinejoin="round" d="m6 6 12 12M18 6 6 18" />
                      </svg>
                    </button>
                  )}
                  <span className="chip text-xs">{completed}/{total || "?"}</span>
                  <button
                    type="button"
                    className="p-2 rounded-lg hover:bg-[var(--field-bg)] text-[var(--ink-500)] disabled:opacity-50"
                    aria-label={`Delete experiment ${displayName}`}
                      title="Delete experiment and logs"
                      disabled={deletingId === exp.experiment_id}
                      onClick={(evt) => {
                        evt.stopPropagation();
                        handleDelete(exp);
                      }}
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.6">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M9.5 4h5l.75 2H19M7 4h4m2 0h4m-9 4v9.5a1.5 1.5 0 0 0 1.5 1.5h4A1.5 1.5 0 0 0 15 17.5V8M5 6h14" />
                      </svg>
                    </button>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div
                    className={clsx(
                      "rounded-xl border p-3 h-full min-h-[104px] max-h-[104px] flex flex-col justify-between",
                      classFor("a")
                    )}
                  >
                    <p className="font-semibold leading-tight line-clamp-2 overflow-hidden text-ellipsis">
                      {shortName(exp.players?.a?.model || "A")}
                    </p>
                    <p className="text-lg font-bold text-right">{winsA}</p>
                  </div>
                  <div
                    className={clsx(
                      "rounded-xl border p-3 h-full min-h-[104px] max-h-[104px] flex flex-col justify-between",
                      classFor("b")
                    )}
                  >
                    <p className="font-semibold text-right leading-tight line-clamp-2 overflow-hidden text-ellipsis">
                      {shortName(exp.players?.b?.model || "B")}
                    </p>
                    <p className="text-lg font-bold text-right">{winsB}</p>
                  </div>
                </div>
                <div className="mt-3 flex items-center justify-between text-xs text-[var(--ink-600)] min-h-[28px]">
                  <span>{pctA}%</span>
                  {draws > 0 && <span className="chip text-xs">Draws {draws}</span>}
                  <span>{pctB}%</span>
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
              <div className="flex flex-col">
                <h3 className="text-xl font-semibold text-[var(--ink-900)]">
                  {selectedExperiment.name || selectedExperiment.experiment_id}
                </h3>
                <p className="text-sm text-[var(--ink-600)]">
                  {selectedExperiment.players.a.model} vs {selectedExperiment.players.b.model} ·{" "}
                  {selectedExperiment.games.total} games
                </p>
                <p className="text-xs text-[var(--ink-500)]">
                  Folder: {selectedExperiment.log_dir_name || selectedExperiment.experiment_id}
                </p>
              </div>
              <span className="chip">{selectedExperiment.status}</span>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <button className="btn secondary" onClick={() => setLiveMode((v) => !v)}>
                {liveMode ? "Back to dashboard" : "Watch chess"}
              </button>
              {liveMode && (
                <button
                  className="btn secondary flex items-center justify-center text-sm w-16 h-10"
                  onClick={() =>
                    setLiveBoardCount((prev) => {
                      if (prev === 1) return 4;
                      return 1;
                    })
                  }
                  aria-label="Toggle number of boards"
                  title="Toggle number of boards"
                >
                  {liveBoardCount === 1 && <span className="inline-block text-base leading-none">▢</span>}
                  {liveBoardCount === 4 && (
                    <span className="inline-block">
                      <div className="grid grid-cols-2 gap-0.5 leading-none text-base">
                        <span>▢</span>
                        <span>▢</span>
                        <span>▢</span>
                        <span>▢</span>
                      </div>
                    </span>
                  )}
                </button>
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
              experimentName={selectedExperiment.name || selectedExperiment.experiment_id}
              games={results?.games || []}
              count={liveBoardCount}
            />
          )}
        </div>
      )}
    </div>
    <PromptDialog
      open={promptDialogOpen}
      systemInstructions={form.prompt.system_instructions}
      template={form.prompt.template}
      onChange={(value) =>
        setForm((f) => ({
          ...f,
          prompt: {
            system_instructions: value.systemInstructions ?? f.prompt.system_instructions,
            template: value.template ?? f.prompt.template
          }
        }))
      }
      onClose={() => setPromptDialogOpen(false)}
    />
    </>
  );
}

function LiveBoardsPanel({
  experimentId,
  experimentName,
  games,
  count
}: {
  experimentId: string;
  experimentName?: string;
  games: ExperimentResults["games"];
  count: number;
}) {
  if (!games?.length) {
    return <p className="text-[var(--ink-500)] text-sm">No games yet to display. Wait for games to start.</p>;
  }

  const baseSize = 520; // larger baseline
  const boardSize = count === 1 ? baseSize * 2 : Math.floor(baseSize * 0.85);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2 items-center">
        <p className="text-[var(--ink-700)] text-sm">
          {experimentName || experimentId} - {games.length} game{games.length === 1 ? "" : "s"}
        </p>
        <span className="text-[var(--ink-500)] text-xs">Scroll to browse all boards ({count}-board view size)</span>
      </div>
      <div className="max-h-[80vh] overflow-y-auto pb-3 pr-1">
        <div className={`grid gap-4 ${count >= 2 ? "md:grid-cols-2" : "md:grid-cols-1"}`}>
          {games.map((g) => (
            <LiveBoard
              key={g.game_id}
              gameId={g.game_id}
              whiteModel={g.white_model}
              blackModel={g.black_model}
              size={boardSize}
              winner={g.winner}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

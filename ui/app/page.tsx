import Link from "next/link";

export default function HomePage() {
  return (
    <div className="fade-in">
      <div className="card p-8 md:p-12">
        <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
          <div className="max-w-xl space-y-4">
            <p className="text-sm uppercase tracking-[0.35em] text-[var(--ink-500)]">Observer mode</p>
            <h1 className="text-3xl md:text-4xl font-semibold text-[var(--ink-900)] font-display">
              Orchestrate live LLM chess games, experiments, and human challenges.
            </h1>
            <p className="text-[var(--ink-700)] leading-relaxed">
              This UI wraps the llmchess runners with a clean control room: watch live LLM vs LLM matches,
              monitor model tournaments, or play a human game while inspecting every prompt and reply.
            </p>
            <div className="flex flex-wrap gap-3">
              <Link href="/experiments" className="btn">
                Open Game Master
              </Link>
              <Link href="/play" className="btn secondary">
                Play vs AI
              </Link>
            </div>
        </div>
        <div className="w-full md:w-80">
            <div className="card p-5 border-[var(--border-soft)]">
              <p className="text-sm text-[var(--ink-700)] mb-3">API wiring</p>
              <ul className="space-y-2 text-sm text-[var(--ink-700)]">
                <li className="flex items-center gap-2">
                  <span className="chip">GET</span>
                  <span>/api/experiments</span>
                </li>
                <li className="flex items-center gap-2">
                  <span className="chip">POST</span>
                  <span>/api/experiments</span>
                </li>
                <li className="flex items-center gap-2">
                  <span className="chip">POST</span>
                  <span>/api/human-games</span>
                </li>
              </ul>
              <p className="text-xs text-[var(--ink-500)] mt-4">
                Configure the backend host via `NEXT_PUBLIC_API_BASE` in `.env.local`.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

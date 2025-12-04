"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";
import { useEffect, useState } from "react";

const links = [
  { href: "/experiments", label: "Game master" },
  { href: "/play", label: "Play vs AI" }
];

type Theme = "light" | "dark";

export function NavBar() {
  const pathname = usePathname();
  const [theme, setTheme] = useState<Theme>("light");

  const applyTheme = (next: Theme) => {
    setTheme(next);
    if (typeof document !== "undefined") {
      document.documentElement.setAttribute("data-theme", next);
    }
    if (typeof localStorage !== "undefined") {
      localStorage.setItem("theme", next);
    }
  };

  useEffect(() => {
    const stored = typeof window !== "undefined" ? (localStorage.getItem("theme") as Theme | null) : null;
    const prefersDark = typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches;
    const initial = stored === "dark" || stored === "light" ? stored : prefersDark ? "dark" : "light";
    applyTheme(initial);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggleTheme = () => {
    applyTheme(theme === "light" ? "dark" : "light");
  };

  return (
    <header className="sticky top-0 z-30 glass border-b border-[var(--border-soft)] backdrop-blur bg-[var(--nav-bg)]">
      <div className="page-shell flex items-center justify-between gap-6 py-4">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-[var(--logo-bg)] border border-[var(--border-strong)] grid place-items-center text-accent font-semibold shadow-sm">
            LC
          </div>
          <div>
            <p className="text-sm uppercase tracking-[0.22em] text-[var(--ink-500)]">llmchess</p>
            <p className="text-lg font-semibold text-[var(--ink-900)]">Control Room</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <nav className="flex items-center gap-2 bg-[var(--nav-pill-bg)] px-2 py-1 rounded-full border border-[var(--border-soft)] shadow-sm">
            {links.map((link) => {
              const active = pathname === link.href || pathname === `${link.href}/`;
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={clsx(
                    "px-4 py-2 rounded-full text-sm font-semibold transition-colors",
                    active
                      ? "bg-gradient-to-r from-accent to-accent2 text-canvas-900 shadow-sm"
                      : "text-[var(--ink-500)] hover:text-[var(--ink-900)] hover:bg-[var(--surface-weak)]"
                  )}
                >
                  {link.label}
                </Link>
              );
            })}
          </nav>
          <button
            className="btn secondary text-sm flex items-center gap-2"
            onClick={toggleTheme}
            aria-label={theme === "light" ? "Switch to dark mode" : "Switch to light mode"}
            title={theme === "light" ? "Switch to dark mode" : "Switch to light mode"}
          >
            {theme === "light" ? "◐" : "☼"}
          </button>
        </div>
      </div>
    </header>
  );
}

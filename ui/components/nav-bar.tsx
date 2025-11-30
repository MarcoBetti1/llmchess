"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";

const links = [
  { href: "/experiments", label: "Game master" },
  { href: "/play", label: "Play vs AI" }
];

export function NavBar() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-30 glass border-b border-white/5 backdrop-blur">
      <div className="page-shell flex items-center justify-between gap-6 py-4">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-white/10 border border-white/10 grid place-items-center text-accent font-semibold">
            LC
          </div>
          <div>
            <p className="text-sm uppercase tracking-[0.22em] text-white/60">llmchess</p>
            <p className="text-lg font-semibold text-white">Control Room</p>
          </div>
        </div>
        <nav className="flex items-center gap-2 bg-white/5 px-2 py-1 rounded-full border border-white/10">
          {links.map((link) => {
            const active = pathname === link.href || pathname === `${link.href}/`;
            return (
              <Link
                key={link.href}
                href={link.href}
                className={clsx(
                  "px-4 py-2 rounded-full text-sm font-semibold transition-colors",
                  active
                    ? "bg-white text-canvas-900"
                    : "text-white/70 hover:text-white hover:bg-white/10"
                )}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}

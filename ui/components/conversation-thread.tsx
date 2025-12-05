"use client";

import { ConversationMessage } from "@/types";
import clsx from "clsx";
import { CSSProperties } from "react";

type Props = {
  messages: ConversationMessage[];
  className?: string;
  title?: string;
  height?: string;
  styleOverride?: CSSProperties;
};

export function ConversationThread({ messages, className, title, height = "min-h-[520px]", styleOverride }: Props) {
  return (
    <div className={clsx("card h-full flex flex-col overflow-hidden", height, className)} style={styleOverride}>
      <div className="flex items-center justify-between gap-3 border-b border-[var(--border-soft)] px-5 py-4">
        <div className="space-y-1">
          <p className="text-sm font-semibold text-[var(--ink-900)]">{title || "Conversation"}</p>
          <p className="text-xs text-[var(--ink-500)]">Latest prompts and replies for this game.</p>
        </div>
        <span className="chip text-xs">{messages.length} {messages.length === 1 ? "msg" : "msgs"}</span>
      </div>
      <div className="flex-1 overflow-y-auto bg-[var(--surface-weak)]/60 px-5 py-5 space-y-4">
        {messages.length === 0 && (
          <div className="glass p-4 rounded-2xl border border-[var(--border-soft)] text-sm text-[var(--ink-500)]">
            Messages exchanged with the AI will appear here once the game begins.
          </div>
        )}
        {messages.map((msg, idx) => {
          const isHuman = msg.role === "human" || msg.role === "user";
          const isSystem = msg.role === "system";
          const isAI = msg.role === "assistant";
          const alignment = isHuman ? "flex-row-reverse" : "flex-row";
          const textAlign = isHuman ? "items-end text-right" : "items-start text-left";
          const bubbleTone = isSystem
            ? "bg-transparent border border-[var(--border-soft)] text-[var(--ink-700)]"
            : isHuman
              ? "bg-gradient-to-br from-[#7ce7ac] to-[#a3bffa] text-[#0b1024]"
              : "bg-[var(--surface-strong)] text-[var(--ink-900)] border border-[var(--border-soft)]";

          const initials = (msg.actor || msg.model || msg.role || "?")
            .split(" ")
            .map((part) => part[0])
            .join("")
            .slice(0, 2)
            .toUpperCase();

          const label = isHuman ? "You" : isAI ? msg.model || "AI" : "System";

          return (
            <div key={idx} className={clsx("flex gap-3 items-start", alignment)}>
              <div
                className={clsx(
                  "w-9 h-9 rounded-full flex items-center justify-center text-xs font-semibold shadow-sm border border-[var(--border-soft)]",
                  isHuman ? "bg-accent text-canvas-900" : isAI ? "bg-[var(--surface-weak)] text-[var(--ink-900)]" : "bg-[var(--surface-strong)] text-[var(--ink-900)]"
                )}
              >
                {initials}
              </div>
              <div className={clsx("flex flex-col gap-2 max-w-[min(720px,80vw)]", textAlign)}>
                <div className="flex flex-wrap items-center gap-2 text-[11px] text-[var(--ink-500)]">
                  <span className="font-semibold text-[var(--ink-700)]">{label}</span>
                  {msg.side && <span className="chip uppercase">{msg.side}</span>}
                  {msg.model && <span className="chip bg-accent text-canvas-900">{msg.model}</span>}
                  {!msg.model && !isSystem && <span className="chip">{msg.role}</span>}
                </div>
                <div className={clsx("rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm", bubbleTone)}>
                  <div className="whitespace-pre-wrap">{msg.content}</div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

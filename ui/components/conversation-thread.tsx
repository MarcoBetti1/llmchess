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
  const visibleMessages = (messages || [])
    .filter((msg) => (msg.content || "").trim().length > 0)
    // The backend adds a synthetic human note ("You played ..."); hide it so we only show what the LLM saw.
    .filter((msg) => msg.role !== "human");

  const formatModel = (model?: string) => {
    if (!model) return "LLM";
    const parts = model.split("/");
    return parts[parts.length - 1] || model;
  };

  return (
    <div className={clsx("card h-full flex flex-col overflow-hidden", height, className)} style={styleOverride}>
      <div className="flex items-center justify-between gap-3 border-b border-[var(--border-soft)] px-5 py-4">
        <div className="space-y-1">
          <p className="text-sm font-semibold text-[var(--ink-900)]">{title || "Conversation"}</p>
          <p className="text-xs text-[var(--ink-500)]">What the model saw and how it replied.</p>
        </div>
        <span className="chip text-xs">
          {visibleMessages.length} {visibleMessages.length === 1 ? "msg" : "msgs"}
        </span>
      </div>
      <div className="flex-1 overflow-y-auto bg-[var(--surface-weak)]/60 px-5 py-5 space-y-4">
        {visibleMessages.length === 0 && (
          <div className="glass p-4 rounded-2xl border border-[var(--border-soft)] text-sm text-[var(--ink-500)]">
            Messages exchanged with the AI will appear here once the game begins.
          </div>
        )}
        {visibleMessages.map((msg, idx) => {
          const isYou = msg.role === "user";
          const isSystem = msg.role === "system";
          const alignment = isYou ? "flex-row-reverse" : "flex-row";
          const textAlign = isYou ? "items-end text-right" : "items-start text-left";
          const bubbleTone = isSystem
            ? "bg-[var(--surface-weak)] border border-[var(--border-soft)] text-[var(--ink-800)]"
            : isYou
              ? "bg-gradient-to-br from-[#7ce7ac] to-[#a3bffa] text-[#0b1024]"
              : "bg-[var(--surface-strong)] text-[var(--ink-900)] border border-[var(--border-soft)]";

          const label = isSystem ? "System" : isYou ? "You" : formatModel(msg.model);
          const meta =
            isSystem ? `System prompt for ${formatModel(msg.model)}` : isYou ? `Prompt -> ${formatModel(msg.model)}` : "Reply";

          const icon = isSystem ? "⚙" : isYou ? "👤" : "🤖";

          return (
            <div key={idx} className={clsx("flex gap-3 items-start", alignment)}>
              <div className="h-9 w-9 flex items-center justify-center text-lg" aria-hidden>
                {icon}
              </div>
              <div className={clsx("flex flex-col gap-2 max-w-[min(720px,80vw)]", textAlign)}>
                <div className="flex flex-wrap items-center gap-2 text-[11px] text-[var(--ink-500)]">
                  <span className="font-semibold text-[var(--ink-800)]">{label}</span>
                  <span className="rounded-full bg-[var(--surface-weak)] px-2 py-0.5 text-[10px] uppercase tracking-wide text-[var(--ink-500)] border border-[var(--border-soft)]">
                    {meta}
                  </span>
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

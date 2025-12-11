"use client";

import { ConversationData, ConversationMessage } from "@/types";
import { Fragment, useMemo } from "react";

type Props = {
  open: boolean;
  onClose: () => void;
  log: ConversationData | null;
};

export function ConversationDialog({ open, onClose, log }: Props) {
  const messages: ConversationMessage[] = useMemo(() => {
    if (!log) return [];
    if (log.messages?.length) return log.messages;
    const flattened: ConversationMessage[] = [];
    (log.conversation || []).forEach((turn) => {
      (turn.messages || []).forEach((msg) =>
        flattened.push({ ...msg, side: turn.side, model: turn.model })
      );
    });
    return flattened;
  }, [log]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40 flex items-start justify-center bg-[var(--overlay-bg)] backdrop-blur-sm p-4 overflow-y-auto">
      <div className="card w-full max-w-4xl p-0 overflow-hidden">
        <div className="sticky top-0 flex items-center justify-between gap-3 border-b border-[var(--border-soft)] bg-[var(--surface-weak)]/90 px-6 py-4 backdrop-blur-sm">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-[var(--ink-500)]">Conversation</p>
            <p className="text-lg font-semibold text-[var(--ink-900)]">{log?.game_id || "game"}</p>
          </div>
          <button className="btn secondary" onClick={onClose}>
            Close
          </button>
        </div>
        <div className="space-y-3 px-6 py-4">
          {!log && <p className="text-[var(--ink-500)] text-sm">Loading conversation...</p>}
          {log &&
            (messages.length > 0 ? (
              messages.map((msg, idx) => {
                const isSystem = msg.role === "system";
                const isUser = msg.role === "user";
                const isAI = msg.role === "assistant";
                return (
                  <div
                    key={idx}
                    className="rounded-2xl border border-[var(--border-soft)] bg-[var(--surface-weak)]/70 p-4 shadow-sm"
                  >
                    <div className="flex flex-wrap items-center gap-2 text-[11px] text-[var(--ink-600)] mb-2">
                      <span className="font-semibold text-[var(--ink-800)]">
                        {isSystem ? "System" : isUser ? "You" : msg.model || "LLM"}
                      </span>
                      {msg.side && <span className="chip uppercase">{msg.side}</span>}
                      {msg.model && <span className="chip bg-accent text-canvas-900">{msg.model}</span>}
                      <span className="chip">{msg.role}</span>
                    </div>
                    <div
                      className={
                        isSystem
                          ? "text-[var(--ink-700)] text-sm whitespace-pre-wrap"
                          : "text-[var(--ink-900)] text-sm whitespace-pre-wrap leading-relaxed"
                      }
                    >
                      {msg.content}
                    </div>
                  </div>
                );
              })
            ) : (
              <p className="text-[var(--ink-500)] text-sm">No conversation available for this game.</p>
            ))}
        </div>
      </div>
    </div>
  );
}

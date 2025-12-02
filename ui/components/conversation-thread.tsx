"use client";

import { ConversationMessage } from "@/types";
import clsx from "clsx";

type Props = {
  messages: ConversationMessage[];
  className?: string;
  title?: string;
  height?: string;
};

export function ConversationThread({ messages, className, title, height = "min-h-[320px]" }: Props) {
  return (
    <div className={clsx("card p-4 space-y-3", height, className)}>
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-[var(--ink-900)]">{title || "Conversation"}</p>
        <span className="chip text-xs">{messages.length} msg</span>
      </div>
      <div className="space-y-3 max-h-[70vh] overflow-y-auto pr-1">
        {messages.length === 0 && <p className="text-[var(--ink-500)] text-sm">No conversation yet.</p>}
        {messages.map((msg, idx) => (
          <div key={idx} className="glass rounded-lg p-3 border border-[var(--border-soft)] text-sm text-[var(--ink-700)]">
            <div className="flex items-center gap-2 mb-1 text-xs text-[var(--ink-500)]">
              {msg.side && <span className="chip uppercase">{msg.side}</span>}
              {msg.model && <span className="chip bg-accent text-canvas-900">{msg.model}</span>}
              <span className="chip">{msg.role}</span>
            </div>
            <div className="whitespace-pre-wrap leading-relaxed">{msg.content}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

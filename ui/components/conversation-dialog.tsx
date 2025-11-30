"use client";

import { ConversationLog } from "@/types";
import { Fragment } from "react";

type Props = {
  open: boolean;
  onClose: () => void;
  log: ConversationLog | null;
};

export function ConversationDialog({ open, onClose, log }: Props) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40 flex items-start justify-center bg-black/60 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="card w-full max-w-4xl p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-white/60">Conversation</p>
            <p className="text-lg font-semibold text-white">{log?.game_id || "game"}</p>
          </div>
          <button className="btn secondary" onClick={onClose}>
            Close
          </button>
        </div>
        <div className="space-y-3 max-h-[70vh] overflow-y-auto pr-2">
          {log?.conversation.map((turn) => (
            <div key={turn.turn_ply} className="glass rounded-xl p-4 border border-white/10">
              <div className="flex items-center gap-2 text-sm text-white/70 mb-2">
                <span className="chip uppercase">{turn.side} {turn.turn_ply}</span>
                <span className="chip bg-accent text-canvas-900">{turn.model}</span>
                {turn.parsed_move && <span className="chip">Move {turn.parsed_move.san}</span>}
              </div>
              <div className="space-y-2 text-sm leading-relaxed">
                {turn.messages.map((msg, idx) => (
                  <Fragment key={idx}>
                    <p className="text-white/60 uppercase text-xs tracking-wide">{msg.role}</p>
                    <div className="glass rounded-lg p-3 border border-white/5 text-white/80 whitespace-pre-wrap">
                      {msg.content}
                    </div>
                  </Fragment>
                ))}
              </div>
            </div>
          ))}
          {!log && <p className="text-white/60 text-sm">Loading conversation...</p>}
        </div>
      </div>
    </div>
  );
}

"use client";

import clsx from "clsx";

type Props = {
  open: boolean;
  systemInstructions: string;
  template: string;
  onChange: (value: { systemInstructions?: string; template?: string }) => void;
  onClose: () => void;
  className?: string;
};

const helperText = "Use placeholders like {FEN}, {SAN_HISTORY}, {PLAINTEXT_HISTORY}, {SIDE_TO_MOVE}. Variables will be injected at runtime.";

export function PromptDialog({ open, systemInstructions, template, onChange, onClose, className }: Props) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40 flex items-start justify-center bg-[var(--overlay-bg)] backdrop-blur-sm p-4 overflow-y-auto">
      <div className={clsx("card w-full max-w-3xl p-6 space-y-5", className)}>
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-[var(--ink-500)]">Prompt</p>
            <p className="text-lg font-semibold text-[var(--ink-900)]">Edit prompt</p>
          </div>
          <button className="btn secondary" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="space-y-3">
          <label className="text-sm text-[var(--ink-700)]">System instructions</label>
          <textarea
            className="w-full min-h-[120px] rounded-xl bg-[var(--field-bg)] border border-[var(--border-soft)] px-3 py-2 text-[var(--ink-900)] shadow-sm"
            value={systemInstructions}
            onChange={(e) => onChange({ systemInstructions: e.target.value })}
          />
          <p className="text-xs text-[var(--ink-500)]">This is sent as the system message.</p>
        </div>

        <div className="space-y-3">
          <label className="text-sm text-[var(--ink-700)]">Prompt template</label>
          <textarea
            className="w-full min-h-[200px] rounded-xl bg-[var(--field-bg)] border border-[var(--border-soft)] px-3 py-2 text-[var(--ink-900)] shadow-sm font-mono text-sm"
            value={template}
            onChange={(e) => onChange({ template: e.target.value })}
          />
          <p className="text-xs text-[var(--ink-500)]">{helperText}</p>
        </div>

        <div className="flex justify-end gap-2">
          <button className="btn secondary" onClick={onClose}>
            Cancel
          </button>
          <button className="btn" onClick={onClose}>
            Save
          </button>
        </div>
      </div>
    </div>
  );
}

"use client";

import clsx from "clsx";

type PromptMode = "plaintext" | "fen" | "fen+plaintext";

type Props = {
  open: boolean;
  mode: PromptMode;
  onModeChange: (value: PromptMode) => void;
  onClose: () => void;
  className?: string;
};

const modes: PromptMode[] = ["plaintext", "fen", "fen+plaintext"];

export function PromptDialog({ open, mode, onModeChange, onClose, className }: Props) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40 flex items-start justify-center bg-[var(--overlay-bg)] backdrop-blur-sm p-4 overflow-y-auto">
      <div className={clsx("card w-full max-w-lg p-6 space-y-5", className)}>
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-[var(--ink-500)]">Prompt</p>
            <p className="text-lg font-semibold text-[var(--ink-900)]">Edit prompt settings</p>
          </div>
          <button className="btn secondary" onClick={onClose}>
            Close
          </button>
        </div>
        <div className="space-y-3">
          <label className="text-sm text-[var(--ink-700)]">Prompt mode</label>
          <select
            className="w-full rounded-xl bg-[var(--field-bg)] border border-[var(--border-soft)] px-3 py-2 text-[var(--ink-900)] shadow-sm"
            value={mode}
            onChange={(e) => onModeChange(e.target.value as PromptMode)}
          >
            {modes.map((opt) => (
              <option key={opt} value={opt}>
                {opt}
              </option>
            ))}
          </select>
          <p className="text-xs text-[var(--ink-500)]">
            Choose how board state is sent to the model. More prompt controls are coming soon.
          </p>
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

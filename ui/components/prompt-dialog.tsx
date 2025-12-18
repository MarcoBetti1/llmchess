"use client";

import clsx from "clsx";
import { MoveNotation } from "@/types";

type Props = {
  open: boolean;
  systemInstructions: string;
  template: string;
  expectedNotation: MoveNotation;
  onChange: (value: { systemInstructions?: string; template?: string; expectedNotation?: MoveNotation }) => void;
  onClose: () => void;
  className?: string;
};

const helperText =
  "Placeholders available: {FEN}, {SIDE_TO_MOVE}, {SAN_HISTORY}, {PLAINTEXT_HISTORY}. Pick a notation preset or customize both fields.";

const presets: Record<MoveNotation, { system: string; template: string; label: string; hint: string }> = {
  san: {
    label: "SAN",
    system: "You are a strong chess player. When asked for a move, provide only the best legal move in SAN.",
    template: `Board FEN: {FEN}
Move history (SAN): {SAN_HISTORY}
Side to move: {SIDE_TO_MOVE}
Return only the best legal move in SAN.`,
    hint: "Return algebraic notation like e4, Nf3, O-O",
  },
  uci: {
    label: "UCI",
    system: "You are a chess engine. Respond with exactly one legal move in long algebraic UCI (e.g., e2e4). Return only the move.",
    template: `Board FEN: {FEN}
Move history (SAN): {SAN_HISTORY}
Side to move: {SIDE_TO_MOVE}
Return only the best legal move in UCI (e.g., e2e4, g7g8q).`,
    hint: "Return long algebraic like e2e4 or e7e8q",
  },
  fen: {
    label: "FEN",
    system: "You generate the resulting board position as a FEN after making your move. Output only that FEN.",
    template: `{FEN}`,
    hint: "Return the FEN of the board after your move",
  },
};

export function PromptDialog({ open, systemInstructions, template, expectedNotation, onChange, onClose, className }: Props) {
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

        <div className="grid gap-3 md:grid-cols-[1.1fr_1fr]">
          <div className="space-y-3">
            <label className="text-sm text-[var(--ink-700)]">Output notation</label>
            <select
              className="select-field w-full px-3 py-2 text-[var(--ink-900)] shadow-sm focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition"
              value={expectedNotation}
              onChange={(e) => onChange({ expectedNotation: e.target.value as MoveNotation })}
            >
              <option value="san">SAN (e4, Nf3, O-O)</option>
              <option value="uci">UCI (e2e4, g7g8q)</option>
              <option value="fen">FEN (resulting board after your move)</option>
            </select>
            <p className="text-xs text-[var(--ink-500)]">
              Backend will validate strictly against this notation. Pick a preset below to auto-fill system and user prompts.
            </p>
          </div>

          <div className="space-y-2">
            <p className="text-sm text-[var(--ink-700)]">Presets</p>
            <div className="grid sm:grid-cols-3 gap-2">
              {(Object.keys(presets) as MoveNotation[]).map((key) => {
                const preset = presets[key];
                return (
                  <button
                    key={key}
                    type="button"
                    className={clsx(
                      "rounded-xl border px-3 py-3 text-left text-sm shadow-sm transition hover:border-accent hover:shadow",
                      expectedNotation === key ? "border-accent bg-accent/10" : "border-[var(--border-soft)] bg-[var(--field-bg)]"
                    )}
                    onClick={() =>
                      onChange({
                        systemInstructions: preset.system,
                        template: preset.template,
                        expectedNotation: key,
                      })
                    }
                  >
                    <p className="font-semibold text-[var(--ink-900)]">{preset.label}</p>
                    <p className="text-xs text-[var(--ink-500)] leading-snug">{preset.hint}</p>
                  </button>
                );
              })}
            </div>
          </div>
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

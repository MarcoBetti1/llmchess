type Props = {
  value: number;
};

export function ProgressBar({ value }: Props) {
  const clamped = Math.min(100, Math.max(0, value));
  return (
    <div className="w-full h-2 rounded-full bg-white/10 overflow-hidden">
      <div
        className="h-full rounded-full bg-gradient-to-r from-accent to-accent2 transition-[width]"
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}

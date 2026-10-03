/** Semantic strength cell — value drives color, not the reverse. */
export function strengthTone(value: number): { bg: string; fg: string; label: string } {
  if (value >= 2) return { bg: '#2f9e44', fg: '#fff', label: 'Strong positive' };
  if (value > 0.05) return { bg: '#b2f2bb', fg: '#1b4332', label: 'Positive' };
  if (value <= -2) return { bg: '#e03131', fg: '#fff', label: 'Strong negative' };
  if (value < -0.05) return { bg: '#ffc9c9', fg: '#862e2e', label: 'Negative' };
  return { bg: '#eef1f5', fg: '#475467', label: 'Near neutral' };
}

export function StrengthCell({ value, quality }: { value: number | undefined; quality?: string }) {
  if (value === undefined || quality === 'MISSING') {
    return (
      <span className="mi-cell mi-cell-missing" title="Missing closed-bar history">
        —
      </span>
    );
  }
  const tone = strengthTone(value);
  const display = `${value >= 0 ? '+' : ''}${value.toFixed(4)}`;
  return (
    <span
      className="mi-cell"
      style={{ background: tone.bg, color: tone.fg }}
      title={`${tone.label}: ${display}`}
      aria-label={`${tone.label}, ${display}`}
    >
      {display}
    </span>
  );
}

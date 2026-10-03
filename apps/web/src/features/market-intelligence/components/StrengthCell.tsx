/** EarnForex CSM cell — solid green/red, signed values to 4 decimals. */
export function strengthTone(value: number): { bg: string; fg: string; label: string } {
  if (value > 0) return { bg: '#228b22', fg: '#fff', label: 'Positive strength' };
  if (value < 0) return { bg: '#dc143c', fg: '#fff', label: 'Negative strength' };
  return { bg: '#fff', fg: '#111', label: 'Neutral' };
}

export function StrengthCell({
  value,
  quality,
  sampleCount,
}: {
  value: number | undefined;
  quality?: string;
  sampleCount?: number;
}) {
  const noData = value === undefined || (quality === 'MISSING' && (sampleCount ?? 0) === 0);
  if (noData) {
    return (
      <span className="mi-cell mi-cell-missing mi-cell-ef" title="Missing closed-bar history">
        —
      </span>
    );
  }
  const tone = strengthTone(value ?? 0);
  const display = `${(value ?? 0) >= 0 ? '+' : ''}${(value ?? 0).toFixed(4)}`;
  const partial = quality === 'PARTIAL';
  return (
    <span
      className={`mi-cell mi-cell-ef${partial ? ' mi-cell-partial' : ''}`}
      style={{ background: tone.bg, color: tone.fg }}
      title={`${tone.label}${partial ? ' (partial basket — run Ingest & calculate)' : ''}: ${display}`}
      aria-label={`${tone.label}, ${display}`}
    >
      {display}
    </span>
  );
}

export function ActionCell({ action }: { action: 'B' | 'S' | 'W' | string | undefined }) {
  const a = action ?? 'W';
  let bg = '#e0ffff';
  let fg = '#111';
  let tip = 'WAIT';
  if (a === 'B') {
    bg = '#228b22';
    fg = '#fff';
    tip = 'POSSIBLE BUY';
  } else if (a === 'S') {
    bg = '#dc143c';
    fg = '#fff';
    tip = 'POSSIBLE SELL';
  }
  return (
    <span className="mi-cell mi-cell-ef mi-cell-action" style={{ background: bg, color: fg }} title={tip}>
      {a}
    </span>
  );
}

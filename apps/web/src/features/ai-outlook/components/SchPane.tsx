/** Weekly SCH oscillator. It is a 0–100 series and must never share the price scale. */
export function SchPane({ series }: { series: { t: string; fast: number; signal: number }[] }) {
  if (!series.length) return null;
  const w = 720;
  const h = 96;
  const pad = 10;
  const t0 = Date.parse(series[0].t);
  const t1 = Date.parse(series[series.length - 1].t);
  const span = t1 - t0 || 1;
  const x = (t: string) => pad + ((Date.parse(t) - t0) / span) * (w - pad * 2);
  const y = (v: number) => pad + (1 - Math.min(100, Math.max(0, v)) / 100) * (h - pad * 2);
  const line = (key: 'fast' | 'signal') => series.map((p, i) => `${i ? 'L' : 'M'}${x(p.t).toFixed(1)},${y(p[key]).toFixed(1)}`).join(' ');
  const last = series[series.length - 1];
  return (
    <figure className="mao-sch">
      <figcaption>
        <b>SCH</b>
        <small>Weekly oscillator beneath price · fast {last.fast.toFixed(1)} · signal {last.signal.toFixed(1)}</small>
      </figcaption>
      <svg viewBox={`0 0 ${w} ${h}`} role="img" aria-label="Weekly SCH oscillator">
        <line className="mao-sch-grid" x1={pad} x2={w - pad} y1={y(75)} y2={y(75)} />
        <line className="mao-sch-grid" x1={pad} x2={w - pad} y1={y(25)} y2={y(25)} />
        <path d={line('signal')} className="mao-sch-signal" />
        <path d={line('fast')} className="mao-sch-fast" />
      </svg>
    </figure>
  );
}

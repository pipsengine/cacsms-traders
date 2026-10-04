import { useEffect, useMemo, useRef, useState, type MouseEvent, type ReactNode } from 'react';

export interface ChartSeries {
  key: string;
  label: string;
  color: string;
  values: (number | null)[];
  emphasis?: boolean;
  dimmed?: boolean;
  area?: boolean;
}

export interface ChartRefLine {
  y: number;
  label?: string;
  color?: string;
  dashed?: boolean;
}

export interface ChartBand {
  from: number;
  to: number;
  color: string;
}

const PAD = { top: 12, right: 16, bottom: 28, left: 40 };

function fmtTick(ms: number, spanMs: number) {
  const d = new Date(ms);
  const opts: Intl.DateTimeFormatOptions =
    spanMs <= 2 * 86_400_000
      ? { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'UTC' }
      : { day: '2-digit', month: 'short', timeZone: 'UTC' };
  return new Intl.DateTimeFormat('en-GB', opts).format(d);
}

export function fmtUtc(iso: string) {
  return `${new Intl.DateTimeFormat('en-GB', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'UTC',
  }).format(new Date(iso))} UTC`;
}

/** Wider gaps than this are drawn as breaks, never as interpolated lines. */
function gapLimit(ts: number[], minGapMs: number) {
  if (ts.length < 3) return Infinity;
  const d = ts.slice(1).map((t, i) => t - ts[i]).sort((a, b) => a - b);
  return Math.max(d[Math.floor(d.length / 2)] * 4, minGapMs, 60_000);
}

export function TimeSeriesChart({
  times,
  series,
  yDomain,
  refLines = [],
  bands = [],
  height = 300,
  formatValue = (v) => v.toFixed(1),
  ariaLabel,
  tooltipExtra,
  minGapMs = 0,
}: {
  times: string[];
  series: ChartSeries[];
  yDomain: [number, number];
  refLines?: ChartRefLine[];
  bands?: ChartBand[];
  height?: number;
  formatValue?: (v: number) => string;
  ariaLabel: string;
  tooltipExtra?: (index: number) => ReactNode;
  minGapMs?: number;
}) {
  const wrap = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(800);
  const [hover, setHover] = useState<number | null>(null);

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(320, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const ts = useMemo(() => times.map((t) => new Date(t).getTime()), [times]);
  const [lo, hi] = yDomain;
  const innerW = width - PAD.left - PAD.right;
  const innerH = height - PAD.top - PAD.bottom;
  const t0 = ts[0] ?? 0;
  const span = Math.max(1, (ts[ts.length - 1] ?? 1) - t0);
  const x = (t: number) => PAD.left + ((t - t0) / span) * innerW;
  const y = (v: number) => PAD.top + (1 - (Math.min(hi, Math.max(lo, v)) - lo) / (hi - lo || 1)) * innerH;
  const limit = useMemo(() => gapLimit(ts, minGapMs), [ts, minGapMs]);

  const paths = useMemo(
    () =>
      series.map((s) => {
        const segs: string[] = [];
        const dots: [number, number][] = [];
        let cur: [number, number][] = [];
        let prevT = -Infinity;
        const flush = () => {
          if (cur.length > 1) segs.push(cur.map(([px, py], k) => `${k ? 'L' : 'M'}${px.toFixed(1)},${py.toFixed(1)}`).join(' '));
          else if (cur.length === 1) dots.push(cur[0]);
          cur = [];
        };
        s.values.forEach((v, i) => {
          if (v === null || v === undefined || ts[i] - prevT > limit) flush();
          if (v !== null && v !== undefined) {
            cur.push([x(ts[i]), y(v)]);
            prevT = ts[i];
          }
        });
        flush();
        return { segs, dots };
      }),
    [series, ts, width, height, lo, hi, limit],
  );

  const yTicks = useMemo(() => {
    const step = (hi - lo) / 4;
    return Array.from({ length: 5 }, (_, i) => lo + step * i);
  }, [lo, hi]);
  const xTicks = useMemo(() => {
    if (ts.length < 2) return [];
    const n = Math.max(2, Math.min(7, Math.floor(innerW / 110)));
    return Array.from({ length: n }, (_, i) => t0 + (span * i) / (n - 1));
  }, [ts, innerW, t0, span]);

  const onMove = (e: MouseEvent<SVGRectElement>) => {
    if (!ts.length) return;
    const box = e.currentTarget.getBoundingClientRect();
    const t = t0 + ((e.clientX - box.left) / box.width) * span;
    let best = 0;
    for (let i = 1; i < ts.length; i++) if (Math.abs(ts[i] - t) < Math.abs(ts[best] - t)) best = i;
    setHover(best);
  };

  const hoverRows =
    hover === null
      ? []
      : series
          .map((s) => ({ s, v: s.values[hover] }))
          .filter((r): r is { s: ChartSeries; v: number } => r.v !== null && r.v !== undefined)
          .sort((a, b) => b.v - a.v);
  const hx = hover === null ? 0 : x(ts[hover]);

  return (
    <div className="si-chart" ref={wrap}>
      <svg width={width} height={height} role="img" aria-label={ariaLabel}>
        {bands.map((b, i) => (
          <rect
            key={i}
            x={PAD.left}
            width={innerW}
            y={y(Math.max(b.from, b.to))}
            height={Math.abs(y(b.from) - y(b.to))}
            fill={b.color}
          />
        ))}
        {yTicks.map((v) => (
          <g key={v}>
            <line x1={PAD.left} x2={width - PAD.right} y1={y(v)} y2={y(v)} className="si-chart-grid" />
            <text x={PAD.left - 8} y={y(v) + 3} textAnchor="end" className="si-chart-axis">
              {formatValue(v)}
            </text>
          </g>
        ))}
        {refLines.map((r) => (
          <g key={`${r.y}-${r.label}`}>
            <line
              x1={PAD.left}
              x2={width - PAD.right}
              y1={y(r.y)}
              y2={y(r.y)}
              stroke={r.color ?? '#94a3b8'}
              strokeDasharray={r.dashed ? '4 4' : undefined}
              strokeWidth={1}
            />
            {r.label ? (
              <text x={width - PAD.right - 4} y={y(r.y) - 4} textAnchor="end" className="si-chart-ref">
                {r.label}
              </text>
            ) : null}
          </g>
        ))}
        {xTicks.map((t, i) => (
          <text
            key={t}
            x={x(t)}
            y={height - 8}
            textAnchor={i === 0 ? 'start' : i === xTicks.length - 1 ? 'end' : 'middle'}
            className="si-chart-axis"
          >
            {fmtTick(t, span)}
          </text>
        ))}
        {series.map((s, si) => (
          <g key={s.key} opacity={s.dimmed ? 0.18 : 1}>
            {paths[si].segs.map((d, k) => (
              <g key={k}>
                {s.area ? <path d={`${d} V${y(0)} H${d.match(/^M([\d.]+)/)?.[1] ?? PAD.left} Z`} fill={s.color} opacity={0.12} /> : null}
                <path d={d} fill="none" stroke={s.color} strokeWidth={s.emphasis ? 2.6 : 1.7} strokeLinejoin="round" />
              </g>
            ))}
            {paths[si].dots.map(([cx, cy], k) => (
              <circle key={`d${k}`} cx={cx} cy={cy} r={s.emphasis ? 3.4 : 2.6} fill={s.color} />
            ))}
          </g>
        ))}
        {hover !== null ? (
          <g>
            <line x1={hx} x2={hx} y1={PAD.top} y2={PAD.top + innerH} className="si-chart-cursor" />
            {hoverRows.map(({ s, v }) => (
              <circle key={s.key} cx={hx} cy={y(v)} r={3.2} fill="#fff" stroke={s.color} strokeWidth={2} />
            ))}
          </g>
        ) : null}
        <rect
          x={PAD.left}
          y={PAD.top}
          width={innerW}
          height={innerH}
          fill="transparent"
          onMouseMove={onMove}
          onMouseLeave={() => setHover(null)}
        />
      </svg>
      {hover !== null && hoverRows.length ? (
        <div
          className="si-chart-tip"
          style={{ left: Math.min(hx + 12, width - 190), top: PAD.top + 4 }}
          role="status"
        >
          <strong>{fmtUtc(times[hover])}</strong>
          {hoverRows.map(({ s, v }) => (
            <span key={s.key}>
              <i style={{ background: s.color }} />
              {s.label}
              <b>{formatValue(v)}</b>
            </span>
          ))}
          {tooltipExtra?.(hover)}
        </div>
      ) : null}
    </div>
  );
}

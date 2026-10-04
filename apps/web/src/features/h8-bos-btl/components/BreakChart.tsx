import { useEffect, useId, useMemo, useRef, useState } from 'react';
import type { Candle, ChartTf, Point } from '../types';

export type ChartLine = { pts: Point[]; color: string; dash?: string; width?: number };
export type ChartHLine = { price: number; from?: string; color: string; dash?: string; label?: string };
export type ChartZone = { lo: number; hi: number; from: string; color: string; stroke: string; label?: string };
export type ChartMarker = { t: string; price: number; kind: 'HIGH' | 'LOW'; color: string };
export type ChartLabel = { t: string; price: number; text: string; above: boolean; color: string; boxed?: boolean };

export type ChartOverlays = {
  lines?: ChartLine[];
  hlines?: ChartHLine[];
  zones?: ChartZone[];
  markers?: ChartMarker[];
  labels?: ChartLabel[];
};

type Sch = { t: string; fast: number; signal: number }[];

const AXIS_W = 58;
const AXIS_H = 18;
const PAD_T = 8;
const PAD_L = 6;
const TICK_PX = 34;

function niceStep(span: number, target: number) {
  const raw = span / Math.max(1, target);
  const mag = 10 ** Math.floor(Math.log10(raw));
  const n = raw / mag;
  return (n < 1.5 ? 1 : n < 3 ? 2 : n < 7 ? 5 : 10) * mag;
}

function fmtTime(ms: number, tf: ChartTf) {
  const d = new Date(ms);
  const mon = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][d.getUTCMonth()];
  if (tf === 'W') return `${mon} '${String(d.getUTCFullYear()).slice(2)}`;
  if (tf === 'H8') return `${d.getUTCDate()} ${mon}`;
  return `${d.getUTCDate()} ${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}`;
}

function useSize() {
  const ref = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => {
      const { width, height } = e.contentRect;
      setSize({ w: Math.floor(width), h: Math.floor(height) });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return { ref, ...size };
}

export function BreakChart({
  tf,
  candles,
  digits,
  overlays = {},
  sch,
  price,
}: {
  tf: ChartTf;
  candles: Candle[];
  digits: number;
  overlays?: ChartOverlays;
  sch?: Sch;
  price?: number | null;
}) {
  const { ref, w, h } = useSize();
  const clip = useId().replace(/:/g, '');
  const times = useMemo(() => candles.map((c) => Date.parse(c.t)), [candles]);

  const geo = useMemo(() => {
    if (!w || !h || candles.length < 2) return null;
    const schH = sch ? Math.max(48, Math.round(h * 0.26)) : 0;
    const plotR = w - AXIS_W;
    const plotB = h - AXIS_H - schH - (sch ? 6 : 0);
    const n = candles.length;
    const step = (plotR - PAD_L) / n;
    const xi = (i: number) => PAD_L + step * (i + 0.5);
    const barMs = (times[n - 1] - times[0]) / (n - 1);
    const xt = (iso: string) => {
      const t = Date.parse(iso);
      if (t <= times[0]) return xi((t - times[0]) / barMs);
      if (t >= times[n - 1]) return xi(n - 1 + (t - times[n - 1]) / barMs);
      let lo = 0;
      let hi = n - 1;
      while (hi - lo > 1) {
        const mid = (lo + hi) >> 1;
        if (times[mid] <= t) lo = mid;
        else hi = mid;
      }
      return xi(lo + (t - times[lo]) / (times[hi] - times[lo]));
    };
    const vals: number[] = candles.flatMap((c) => [c.h, c.l]);
    const t0 = times[0];
    for (const z of overlays.zones ?? []) vals.push(z.lo, z.hi);
    for (const l of overlays.hlines ?? []) vals.push(l.price);
    for (const m of overlays.markers ?? []) if (Date.parse(m.t) >= t0) vals.push(m.price);
    if (price != null) vals.push(price);
    const finite = vals.filter(Number.isFinite);
    let lo = Math.min(...finite);
    let hi = Math.max(...finite);
    const pad = Math.max((hi - lo) * 0.08, Math.abs(hi) * 0.0004);
    lo -= pad;
    hi += pad;
    const y = (p: number) => PAD_T + ((hi - p) / (hi - lo)) * (plotB - PAD_T);
    const tickStep = niceStep(hi - lo, Math.max(2, Math.floor((plotB - PAD_T) / TICK_PX)));
    const ticks: number[] = [];
    for (let v = Math.ceil(lo / tickStep) * tickStep; v <= hi; v += tickStep) ticks.push(v);
    const every = Math.max(1, Math.ceil(n / Math.max(2, Math.floor((plotR - PAD_L) / 90))));
    const xticks = candles.map((_, i) => i).filter((i) => i % every === Math.floor(every / 2));
    return { schH, plotR, plotB, step, xi, xt, y, ticks, xticks };
  }, [w, h, candles, times, overlays, sch, price]);

  if (candles.length < 2) {
    return (
      <div ref={ref} className="h8b-chart h8b-chart--empty">
        <span>No closed {tf} candles stored yet</span>
      </div>
    );
  }

  return (
    <div ref={ref} className="h8b-chart">
      {geo && (
        <svg width={w} height={h} role="img" aria-label={`${tf} chart`}>
          <defs>
            <clipPath id={clip}>
              <rect x={0} y={0} width={geo.plotR} height={geo.plotB} />
            </clipPath>
          </defs>
          {geo.ticks.map((t) => (
            <g key={t}>
              <line x1={0} x2={geo.plotR} y1={geo.y(t)} y2={geo.y(t)} className="h8b-grid" />
              <text x={geo.plotR + 6} y={geo.y(t) + 3.5} className="h8b-axis">
                {t.toFixed(digits)}
              </text>
            </g>
          ))}
          {geo.xticks.map((i) => (
            <g key={i}>
              <line x1={geo.xi(i)} x2={geo.xi(i)} y1={PAD_T} y2={geo.plotB} className="h8b-grid" />
              <text x={geo.xi(i)} y={h - 5} textAnchor="middle" className="h8b-axis">
                {fmtTime(times[i], tf)}
              </text>
            </g>
          ))}
          <g clipPath={`url(#${clip})`}>
            {(overlays.zones ?? []).map((z, i) => {
              const x0 = Math.max(0, geo.xt(z.from));
              return (
                <g key={i}>
                  <rect
                    x={x0}
                    y={geo.y(z.hi)}
                    width={Math.max(4, geo.plotR - x0)}
                    height={Math.max(4, geo.y(z.lo) - geo.y(z.hi))}
                    fill={z.color}
                    stroke={z.stroke}
                    strokeDasharray="4 3"
                  />
                  {z.label && (
                    <text x={Math.min(x0 + 6, geo.plotR - 70)} y={geo.y(z.hi) - 4} className="h8b-tag" fill={z.stroke}>
                      {z.label}
                    </text>
                  )}
                </g>
              );
            })}
            {candles.map((c, i) => {
              const up = c.c >= c.o;
              const x = geo.xi(i);
              const bw = Math.max(1, Math.min(9, geo.step * 0.62));
              const top = geo.y(Math.max(c.o, c.c));
              return (
                <g key={c.t} className={up ? 'h8b-up' : 'h8b-down'}>
                  <line x1={x} x2={x} y1={geo.y(c.h)} y2={geo.y(c.l)} />
                  <rect x={x - bw / 2} y={top} width={bw} height={Math.max(1, geo.y(Math.min(c.o, c.c)) - top)} />
                </g>
              );
            })}
            {(overlays.lines ?? []).map((l, i) => (
              <polyline
                key={i}
                points={l.pts.map(([t, p]) => `${geo.xt(t)},${geo.y(p)}`).join(' ')}
                fill="none"
                stroke={l.color}
                strokeWidth={l.width ?? 1.6}
                strokeDasharray={l.dash}
              />
            ))}
            {(overlays.hlines ?? []).map((l, i) => {
              const x0 = l.from ? Math.max(0, geo.xt(l.from)) : 0;
              return (
                <g key={i}>
                  <line x1={x0} x2={geo.plotR} y1={geo.y(l.price)} y2={geo.y(l.price)} stroke={l.color} strokeDasharray={l.dash ?? '5 4'} strokeWidth={1.3} />
                  {l.label && (
                    <text x={geo.plotR - 4} y={geo.y(l.price) - 4} textAnchor="end" className="h8b-tag" fill={l.color}>
                      {l.label}
                    </text>
                  )}
                </g>
              );
            })}
            {(overlays.markers ?? []).map((m, i) => {
              const x = geo.xt(m.t);
              const yy = geo.y(m.price) + (m.kind === 'HIGH' ? -9 : 9);
              return <path key={i} d={m.kind === 'HIGH' ? `M${x - 4},${yy - 3} L${x + 4},${yy - 3} L${x},${yy + 3} Z` : `M${x - 4},${yy + 3} L${x + 4},${yy + 3} L${x},${yy - 3} Z`} fill={m.color} />;
            })}
            {(overlays.labels ?? []).map((l, i) => {
              const x = Math.min(Math.max(geo.xt(l.t), 18), geo.plotR - 18);
              const yy = geo.y(l.price) + (l.above ? -10 : 16);
              if (!l.boxed) {
                return (
                  <text key={i} x={x} y={yy} textAnchor="middle" className="h8b-swing" fill={l.color}>
                    {l.text}
                  </text>
                );
              }
              const wBox = l.text.length * 6.2 + 12;
              const bx = Math.min(Math.max(x - wBox / 2, 2), geo.plotR - wBox - 2);
              return (
                <g key={i}>
                  <rect x={bx} y={yy - 12} width={wBox} height={17} rx={3} fill="#fff" stroke={l.color} />
                  <text x={bx + wBox / 2} y={yy} textAnchor="middle" className="h8b-tag" fill={l.color}>
                    {l.text}
                  </text>
                </g>
              );
            })}
          </g>
          {price != null && Number.isFinite(price) && (
            <g>
              <line x1={0} x2={geo.plotR} y1={geo.y(price)} y2={geo.y(price)} className="h8b-price-line" />
              <rect x={geo.plotR + 1} y={geo.y(price) - 8} width={AXIS_W - 2} height={16} rx={2} className="h8b-price-tag" />
              <text x={geo.plotR + 5} y={geo.y(price) + 3.5} className="h8b-price-text">
                {price.toFixed(digits)}
              </text>
            </g>
          )}
          {sch && geo.schH > 0 && <SchPane sch={sch} geo={geo} top={geo.plotB + 6} />}
        </svg>
      )}
    </div>
  );
}

function SchPane({ sch, geo, top }: { sch: Sch; geo: { schH: number; plotR: number; xt: (iso: string) => number }; top: number }) {
  const hgt = geo.schH;
  const yv = (v: number) => top + 4 + ((100 - v) / 100) * (hgt - 8);
  const pts = (k: 'fast' | 'signal') =>
    sch
      .filter((p) => Number.isFinite(p[k]))
      .map((p) => `${geo.xt(p.t)},${yv(p[k])}`)
      .join(' ');
  return (
    <g>
      <rect x={0} y={top} width={geo.plotR} height={hgt} className="h8b-sch-bg" />
      {[0, 50, 100].map((v) => (
        <g key={v}>
          <line x1={0} x2={geo.plotR} y1={yv(v)} y2={yv(v)} className="h8b-sch-grid" />
          <text x={geo.plotR + 6} y={yv(v) + 3.5} className="h8b-axis">
            {v}
          </text>
        </g>
      ))}
      <text x={6} y={top + 12} className="h8b-sch-title">
        SCH
      </text>
      <svg x={0} y={top} width={geo.plotR} height={hgt} overflow="hidden">
        <g transform={`translate(0,${-top})`}>
          <polyline points={pts('fast')} fill="none" stroke="#14b8c4" strokeWidth={1.6} />
          <polyline points={pts('signal')} fill="none" stroke="#ef4444" strokeWidth={1.3} strokeDasharray="4 3" />
        </g>
      </svg>
    </g>
  );
}

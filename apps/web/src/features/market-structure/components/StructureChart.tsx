import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from 'react';
import { InstrumentIcon } from '../../market-scanner/components/InstrumentIcon';
import { fmtPrice } from '../../market-scanner/format';
import type { ChannelOverlay, FractalMark, RangeCore, VCandle } from '../types';

const PAD = { top: 12, right: 58, bottom: 22, left: 8 };
const VOL_H = 30;
const RANGE_LEAD_BARS = 26;
const RANGE_MIN_BARS = 60;
const RANGE_MIN_FILL = 0.35;
const RANGE_LEAD_BAND = 1.5;
const TICK_SPACING_PX = 26;

type RangeOverlay = Pick<RangeCore, 'start' | 'high_zone' | 'low_zone' | 'range_high' | 'range_low' | 'midpoint'> & {
  fractals?: FractalMark[];
};

export type OverlayTone = 'res' | 'sup' | 'mid' | 'blue' | 'red' | 'green' | 'amber' | 'purple' | 'gray';
export type TimePoint = [string, number];
/** Time-anchored chart annotations; times outside the loaded candles are extrapolated by bar spacing. */
export type ChartOverlay = {
  bands?: { upper: [TimePoint, TimePoint]; lower: [TimePoint, TimePoint]; tone: OverlayTone }[];
  lines?: { from: TimePoint; to: TimePoint; tone: OverlayTone; dashed?: boolean; width?: number }[];
  levels?: { price: number; tone: OverlayTone; label?: string; dashed?: boolean; from?: string; id?: string }[];
  zones?: { lo: number; hi: number; tone: OverlayTone; from?: string; label?: string; id?: string }[];
  markers?: {
    at: string;
    price: number;
    shape: 'up' | 'down' | 'dot' | 'diamond' | 'text';
    tone: OverlayTone;
    label?: string;
    muted?: boolean;
    below?: boolean;
    id?: string;
  }[];
  tags?: { at?: string; price: number; title: string; value?: string; tone: OverlayTone; place: 'above' | 'below' | 'center'; id?: string }[];
  /** Projected paths (may extend into the reserved future area); the last segment gets an arrowhead. */
  paths?: { points: TimePoint[]; tone: OverlayTone; dashed?: boolean; arrow?: boolean; id?: string }[];
};
export type LegendItem = { label: string; swatch: string };

function ticks(lo: number, hi: number, count: number) {
  const raw = (hi - lo || 1) / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  const out: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) out.push(v);
  return out;
}

function axisLabels(candles: VCandle[], tf: string) {
  const out: { i: number; text: string; strong: boolean }[] = [];
  const fmt = (d: Date, o: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat('en-GB', { ...o, timeZone: 'UTC' }).format(d);
  let prev: Date | null = null;
  candles.forEach((c, i) => {
    const d = new Date(c.t);
    if (prev) {
      if (tf === 'Y' || tf === 'HY' || tf === 'Q' || tf === 'MN') {
        if (d.getUTCFullYear() !== prev.getUTCFullYear()) out.push({ i, text: String(d.getUTCFullYear()), strong: d.getUTCFullYear() % 5 === 0 });
      } else if (tf === 'W') {
        if (d.getUTCMonth() !== prev.getUTCMonth() && d.getUTCMonth() % 3 === 0) {
          const jan = d.getUTCMonth() === 0;
          out.push({ i, text: jan ? String(d.getUTCFullYear()) : fmt(d, { month: 'short' }), strong: jan });
        }
      } else if (tf === 'D1' || tf === 'YTD') {
        if (d.getUTCMonth() !== prev.getUTCMonth()) out.push({ i, text: fmt(d, { month: 'short' }), strong: false });
      } else if (d.getUTCDate() !== prev.getUTCDate()) {
        const monthStart = d.getUTCMonth() !== prev.getUTCMonth();
        out.push({ i, text: monthStart ? fmt(d, { month: 'short' }) : String(d.getUTCDate()), strong: monthStart });
      }
    }
    prev = d;
  });
  const minGap = tf === 'W' || tf === 'D1' ? 1 : 4;
  return out.filter((l, k) => k === 0 || l.i - out[k - 1].i >= minGap || l.strong);
}

function thin<T extends { i: number }>(labels: T[], x: (i: number) => number, minPx: number) {
  const out: T[] = [];
  for (const l of labels) if (!out.length || x(l.i) - x(out[out.length - 1].i) >= minPx) out.push(l);
  return out;
}

function timeIndex(candles: VCandle[]) {
  const ms = candles.map((c) => Date.parse(c.t));
  const n = ms.length;
  const span = n > 1 ? (ms[n - 1] - ms[0]) / (n - 1) : 1;
  return (t: string) => {
    const v = Date.parse(t);
    if (!n || Number.isNaN(v)) return NaN;
    if (v <= ms[0]) return (v - ms[0]) / span;
    if (v >= ms[n - 1]) return n - 1 + (v - ms[n - 1]) / span;
    let lo = 0;
    let hi = n - 1;
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1;
      if (ms[mid] <= v) lo = mid;
      else hi = mid;
    }
    return lo + (v - ms[lo]) / (ms[hi] - ms[lo] || 1);
  };
}

const TAG_W = 120;

export function StructureChart({
  symbol,
  title,
  tf,
  candles: source,
  digits,
  lastPrice,
  range,
  channel,
  height,
  loading,
  error,
  heading,
  actions,
  overlay,
  legend,
  showVolume = true,
  compact = false,
  className = '',
  futureBars = 0,
  onPick,
  selected,
}: {
  symbol: string;
  title: string;
  tf: string;
  candles: VCandle[];
  digits: number;
  lastPrice: number | null | undefined;
  range?: RangeOverlay | null;
  channel?: ChannelOverlay | null;
  height: number;
  loading?: boolean;
  error?: string;
  heading?: ReactNode;
  actions?: ReactNode;
  overlay?: ChartOverlay | null;
  legend?: LegendItem[];
  showVolume?: boolean;
  compact?: boolean;
  className?: string;
  futureBars?: number;
  onPick?: (id: string) => void;
  selected?: string | null;
}) {
  const clipId = `mst-clip-${useId().replace(/:/g, '')}`;
  const wrap = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(600);
  const [hover, setHover] = useState<number | null>(null);
  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(260, Math.floor(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const candles = useMemo(() => {
    if (!range || source.length <= RANGE_MIN_BARS) return source;
    const si = source.findIndex((c) => c.t >= range.start);
    if (si < 0) return source;
    const w = range.range_high - range.range_low;
    const bandLo = range.range_low - RANGE_LEAD_BAND * w;
    const bandHi = range.range_high + RANGE_LEAD_BAND * w;
    let from = si;
    while (
      from > 0 &&
      (si - from < RANGE_LEAD_BARS || source.length - from < RANGE_MIN_BARS) &&
      source[from - 1].l >= bandLo &&
      source[from - 1].h <= bandHi
    )
      from--;
    return source.slice(from);
  }, [source, range]);

  const ch = useMemo(() => {
    if (!channel || channel.key === 'INSUFFICIENT' || channel.mid == null || channel.upper == null || !channel.period) return null;
    const n = candles.length;
    if (n < channel.period) return null;
    const slope = ((channel.slope_pct_per_bar ?? 0) * channel.mid) / 100;
    return {
      i0: n - channel.period,
      i1: n - 1,
      m0: channel.mid - slope * (channel.period - 1),
      m1: channel.mid,
      half: channel.upper - channel.mid,
    };
  }, [channel, candles.length]);

  const idxAt = useMemo(() => timeIndex(candles), [candles]);

  const g = useMemo(() => {
    if (!candles.length) return null;
    const si = range ? Math.max(0, candles.findIndex((c) => c.t >= range.start)) : 0;
    const framed = candles.slice(si);
    let lo = Math.min(...framed.map((c) => c.l));
    let hi = Math.max(...framed.map((c) => c.h));
    const extra: number[] = [];
    if (lastPrice != null) extra.push(lastPrice);
    if (range) extra.push(range.range_high, range.range_low);
    if (ch) extra.push(ch.m0 + ch.half, ch.m0 - ch.half, ch.m1 + ch.half, ch.m1 - ch.half);
    if (overlay) {
      const n = candles.length;
      const end = n - 0.5 + futureBars;
      const visible = (a: TimePoint, b: TimePoint) => {
        const ia = idxAt(a[0]);
        const ib = idxAt(b[0]);
        if (!Number.isFinite(ia) || !Number.isFinite(ib) || ib === ia) return [];
        const at = (i: number) => a[1] + ((b[1] - a[1]) * (i - ia)) / (ib - ia);
        const i0 = Math.max(-0.5, Math.min(ia, ib));
        const i1 = Math.min(end, Math.max(ia, ib));
        return i1 > i0 ? [at(i0), at(i1)] : [];
      };
      for (const b of overlay.bands ?? []) extra.push(...visible(...b.upper), ...visible(...b.lower));
      for (const l of overlay.lines ?? []) extra.push(...visible(l.from, l.to));
      for (const l of overlay.levels ?? []) extra.push(l.price);
      for (const z of overlay.zones ?? []) extra.push(z.lo, z.hi);
      for (const m of overlay.markers ?? []) if (idxAt(m.at) >= -0.5) extra.push(m.price);
      for (const t of overlay.tags ?? []) extra.push(t.price);
      for (const p of overlay.paths ?? [])
        for (const [t, v] of p.points) {
          const i = idxAt(t);
          if (i >= -0.5 && i <= end) extra.push(v);
        }
    }
    for (const v of extra) {
      lo = Math.min(lo, v);
      hi = Math.max(hi, v);
    }
    const pad = range ? Math.max((hi - lo) * 0.45, (range.range_high - range.range_low) * 0.6) : (hi - lo) * 0.07 || hi * 0.001;
    lo -= pad;
    hi += pad;
    if (range && si > 0) {
      const allLo = Math.min(lo, ...candles.map((c) => c.l));
      const allHi = Math.max(hi, ...candles.map((c) => c.h));
      const fill = (range.range_high - range.range_low) / (allHi - allLo);
      if (fill >= RANGE_MIN_FILL) {
        const edge = (allHi - allLo) * 0.04;
        lo = allLo - edge;
        hi = allHi + edge;
      }
    }
    const plotBottom = height - PAD.bottom;
    const priceBottom = showVolume ? plotBottom - VOL_H - 4 : plotBottom - 2;
    const step = (width - PAD.left - PAD.right) / (candles.length + futureBars);
    const x = (i: number) => PAD.left + step * (i + 0.5);
    const y = (v: number) => PAD.top + ((hi - v) / (hi - lo)) * (priceBottom - PAD.top);
    const vmax = Math.max(1, ...candles.map((c) => c.v || 0));
    const tickCount = Math.max(compact ? 3 : 4, Math.round((priceBottom - PAD.top) / TICK_SPACING_PX));
    return { lo, hi, step, x, y, plotBottom, priceBottom, vmax, tickCount };
  }, [candles, width, height, lastPrice, range, ch, overlay, idxAt, showVolume, compact, futureBars]);
  const pick = (id?: string) =>
    id && onPick
      ? { onClick: () => onPick(id), style: { cursor: 'pointer' }, 'data-picked': selected === id ? '' : undefined }
      : {};

  const last = candles[candles.length - 1];
  const prev = candles[candles.length - 2];
  const chg = last && prev ? last.c - prev.c : null;
  const chgPct = chg != null && prev ? (chg / prev.c) * 100 : null;
  const cls = chg == null ? '' : chg >= 0 ? 'up' : 'down';
  const tfLabel = tf === 'W' ? 'W' : tf;

  return (
    <section className={`mst-card mst-chart-card ${className}`}>
      <header className="mst-chart-head">
        {heading ?? (
          <strong>
            <InstrumentIcon base={symbol.slice(0, 3)} quote={symbol.slice(3, 6)} size="sm" /> {symbol} · {title}
          </strong>
        )}
        {actions ?? <span className="mst-tf-badge">{tfLabel}</span>}
      </header>
      <div className="mst-ohlc" hidden={compact}>
        {last ? (
          <>
            O <b className={cls}>{fmtPrice(last.o, digits)}</b> H <b className={cls}>{fmtPrice(last.h, digits)}</b> L{' '}
            <b className={cls}>{fmtPrice(last.l, digits)}</b> C <b className={cls}>{fmtPrice(last.c, digits)}</b>{' '}
            {chg != null ? (
              <span className={cls}>
                {chg > 0 ? '+' : ''}
                {fmtPrice(chg, digits)} ({chgPct! > 0 ? '+' : ''}
                {chgPct!.toFixed(2)}%)
              </span>
            ) : null}
            <small> last closed bar</small>
          </>
        ) : (
          <span className="mst-muted">—</span>
        )}
      </div>
      <div ref={wrap} className="mst-chart" style={{ height }}>
        {!g ? (
          <div className="mst-chart-empty" style={{ height }}>
            {loading ? `Loading ${tfLabel} candles…` : error ? 'Candle history unavailable' : `No closed ${tfLabel} candles stored`}
          </div>
        ) : (
          <svg
            width={width}
            height={height}
            role="img"
            aria-label={`${symbol} ${title} chart`}
            onMouseLeave={() => setHover(null)}
            onMouseMove={(e) => {
              const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
              const i = Math.floor((e.clientX - r.left - PAD.left) / g.step);
              setHover(i >= 0 && i < candles.length ? i : null);
            }}
          >
            {ticks(g.lo, g.hi, g.tickCount).map((t) => (
              <g key={t}>
                <line className="mst-grid" x1={PAD.left} x2={width - PAD.right} y1={g.y(t)} y2={g.y(t)} />
                <text className="mst-axis" x={width - PAD.right + 6} y={g.y(t) + 3.5}>
                  {fmtPrice(t, digits > 3 ? digits - 1 : digits === 3 ? 2 : 0)}
                </text>
              </g>
            ))}
            {thin(axisLabels(candles, tf), g.x, compact ? 30 : 34).map((l) => (
              <g key={l.i}>
                <line className="mst-grid" x1={g.x(l.i)} x2={g.x(l.i)} y1={PAD.top} y2={g.plotBottom} />
                <text className={`mst-axis ${l.strong ? 'is-strong' : ''}`} x={g.x(l.i)} y={height - 6} textAnchor="middle">
                  {l.text}
                </text>
              </g>
            ))}

            {range
              ? (() => {
                  const si = Math.max(0, candles.findIndex((c) => c.t >= range.start));
                  const x0 = si <= 0 ? PAD.left : g.x(si) - g.step / 2;
                  const x1 = width - PAD.right;
                  const zone = (z: [number, number] | null, fallback: number, cls: string) => {
                    const [a, b] = z ?? [fallback, fallback];
                    const top = g.y(Math.max(a, b));
                    const h = Math.max(6, g.y(Math.min(a, b)) - top);
                    return <rect className={cls} x={x0} y={h === 6 ? top - 3 : top} width={x1 - x0} height={h} />;
                  };
                  return (
                    <g>
                      <rect
                        className="mst-range-box"
                        x={x0}
                        y={g.y(range.range_high)}
                        width={x1 - x0}
                        height={Math.max(0, g.y(range.range_low) - g.y(range.range_high))}
                      />
                      {zone(range.high_zone, range.range_high, 'mst-zone-high')}
                      {zone(range.low_zone, range.range_low, 'mst-zone-low')}
                      <line className="mst-mid" x1={x0} x2={x1} y1={g.y(range.midpoint)} y2={g.y(range.midpoint)} />
                    </g>
                  );
                })()
              : null}

            {ch ? (
              <g>
                <polygon
                  className="mst-channel"
                  points={`${g.x(ch.i0)},${g.y(ch.m0 + ch.half)} ${g.x(ch.i1)},${g.y(ch.m1 + ch.half)} ${g.x(ch.i1)},${g.y(ch.m1 - ch.half)} ${g.x(ch.i0)},${g.y(ch.m0 - ch.half)}`}
                />
                <line className="mst-channel-edge" x1={g.x(ch.i0)} y1={g.y(ch.m0 + ch.half)} x2={g.x(ch.i1)} y2={g.y(ch.m1 + ch.half)} />
                <line className="mst-channel-edge" x1={g.x(ch.i0)} y1={g.y(ch.m0 - ch.half)} x2={g.x(ch.i1)} y2={g.y(ch.m1 - ch.half)} />
                <line className="mst-channel-mid" x1={g.x(ch.i0)} y1={g.y(ch.m0)} x2={g.x(ch.i1)} y2={g.y(ch.m1)} />
              </g>
            ) : null}

            <defs>
              <clipPath id={clipId}>
                <rect x={PAD.left} y={PAD.top} width={width - PAD.left - PAD.right} height={g.priceBottom - PAD.top} />
              </clipPath>
            </defs>
            {overlay ? (
              <g clipPath={`url(#${clipId})`}>
                {overlay.zones?.map((z, k) => {
                  const x0 = z.from ? Math.max(PAD.left, g.x(idxAt(z.from)) - g.step / 2) : PAD.left;
                  const top = g.y(Math.max(z.lo, z.hi));
                  return (
                    <rect
                      key={`z${k}`}
                      {...pick(z.id)}
                      className={`mcx-zone is-${z.tone}`}
                      x={x0}
                      y={top}
                      width={Math.max(0, width - PAD.right - x0)}
                      height={Math.max(2, g.y(Math.min(z.lo, z.hi)) - top)}
                    />
                  );
                })}
                {overlay.bands?.map((b, k) => {
                  const pt = ([t, p]: TimePoint) => `${g.x(idxAt(t))},${g.y(p)}`;
                  return <polygon key={`b${k}`} className={`mcx-band is-${b.tone}`} points={[pt(b.upper[0]), pt(b.upper[1]), pt(b.lower[1]), pt(b.lower[0])].join(' ')} />;
                })}
                {overlay.lines?.map((l, k) => (
                  <line
                    key={`l${k}`}
                    className={`mcx-line is-${l.tone} ${l.dashed ? 'is-dashed' : ''}`}
                    style={l.width ? { strokeWidth: l.width } : undefined}
                    x1={g.x(idxAt(l.from[0]))}
                    y1={g.y(l.from[1])}
                    x2={g.x(idxAt(l.to[0]))}
                    y2={g.y(l.to[1])}
                  />
                ))}
                {overlay.levels?.map((l, k) => {
                  const x0 = l.from ? Math.max(PAD.left, g.x(idxAt(l.from))) : PAD.left;
                  return (
                    <line
                      key={`v${k}`}
                      {...pick(l.id)}
                      className={`mcx-line is-${l.tone} ${l.dashed === false ? '' : 'is-dashed'}`}
                      x1={x0}
                      x2={width - PAD.right}
                      y1={g.y(l.price)}
                      y2={g.y(l.price)}
                    />
                  );
                })}
              </g>
            ) : null}
            {showVolume && candles.map((c, i) => {
              const bw = Math.max(1, Math.min(9, g.step * 0.62));
              const vh = ((c.v || 0) / g.vmax) * VOL_H;
              return (
                <rect
                  key={`v${c.t}`}
                  className={`mst-vol ${c.c >= c.o ? 'is-up' : 'is-down'}`}
                  x={g.x(i) - bw / 2}
                  y={g.plotBottom - vh}
                  width={bw}
                  height={vh}
                />
              );
            })}
            <g clipPath={`url(#${clipId})`}>
              {candles.map((c, i) => {
                const bw = Math.max(1, Math.min(9, g.step * 0.62));
                return (
                  <g key={c.t} className={c.c >= c.o ? 'mst-up' : 'mst-down'}>
                    <line x1={g.x(i)} x2={g.x(i)} y1={g.y(c.h)} y2={g.y(c.l)} />
                    <rect x={g.x(i) - bw / 2} y={g.y(Math.max(c.o, c.c))} width={bw} height={Math.max(1, Math.abs(g.y(c.o) - g.y(c.c)))} />
                  </g>
                );
              })}
            </g>

            {range
              ? (() => {
                  const bx = Math.max(PAD.left + 4, width - PAD.right - 176);
                  const hz = range.high_zone ?? [range.range_high, range.range_high];
                  const lz = range.low_zone ?? [range.range_low, range.range_low];
                  const hy = Math.max(PAD.top, g.y(Math.max(...hz)) - 36);
                  const ly = Math.min(g.priceBottom - 32, g.y(Math.min(...lz)) + 6);
                  return (
                    <g>
                      <rect className="mst-callout is-res" x={bx} y={hy} width={164} height={30} rx={5} />
                      <text className="mst-callout-t is-res" x={bx + 82} y={hy + 12} textAnchor="middle">
                        Weekly Resistance Cluster
                      </text>
                      <text className="mst-callout-v is-res" x={bx + 82} y={hy + 25} textAnchor="middle">
                        {fmtPrice(Math.min(...hz), digits)} – {fmtPrice(Math.max(...hz), digits)}
                      </text>
                      <rect className="mst-callout is-sup" x={bx} y={ly} width={164} height={30} rx={5} />
                      <text className="mst-callout-t is-sup" x={bx + 82} y={ly + 12} textAnchor="middle">
                        Weekly Support Cluster
                      </text>
                      <text className="mst-callout-v is-sup" x={bx + 82} y={ly + 25} textAnchor="middle">
                        {fmtPrice(Math.min(...lz), digits)} – {fmtPrice(Math.max(...lz), digits)}
                      </text>
                    </g>
                  );
                })()
              : null}

            {ch
              ? (() => {
                  const bx = Math.max(PAD.left + 4, g.x(ch.i1) - 128);
                  const ry = Math.max(PAD.top, g.y(ch.m1 + ch.half) - 40);
                  const sy = Math.min(g.priceBottom - 30, g.y(ch.m1 - ch.half) + 10);
                  return (
                    <g>
                      <rect className="mst-label" x={bx} y={ry} width={112} height={30} rx={5} />
                      <text className="mst-label-t" x={bx + 56} y={ry + 12} textAnchor="middle">
                        Channel Resistance
                      </text>
                      <text className="mst-label-v" x={bx + 56} y={ry + 25} textAnchor="middle">
                        {fmtPrice(ch.m1 + ch.half, digits)}
                      </text>
                      <rect className="mst-label" x={bx} y={sy} width={112} height={30} rx={5} />
                      <text className="mst-label-t" x={bx + 56} y={sy + 12} textAnchor="middle">
                        Channel Support
                      </text>
                      <text className="mst-label-v" x={bx + 56} y={sy + 25} textAnchor="middle">
                        {fmtPrice(ch.m1 - ch.half, digits)}
                      </text>
                    </g>
                  );
                })()
              : null}

            {range?.fractals?.map((f) => {
              if (!f.in_cluster && !f.major) return null;
              const i = candles.findIndex((c) => c.t === f.at);
              if (i < 0) return null;
              const py = g.y(f.price);
              if (py < PAD.top || py > g.priceBottom) return null;
              return f.kind === 'WFH' ? (
                <path key={f.kind + f.at} className="mst-fh" d={`M${g.x(i) - 5},${py - 12} h10 l-5,8 z`} />
              ) : (
                <path key={f.kind + f.at} className="mst-fl" d={`M${g.x(i) - 5},${py + 12} h10 l-5,-8 z`} />
              );
            })}

            {overlay ? (
              <g>
                {overlay.zones?.map((z, k) =>
                  z.label ? (
                    <text
                      key={`zt${k}`}
                      className={`mcx-level-t is-${z.tone}`}
                      x={(z.from ? Math.max(PAD.left, g.x(idxAt(z.from)) - g.step / 2) : PAD.left) + 4}
                      y={g.y(Math.max(z.lo, z.hi)) - 3}
                    >
                      {z.label}
                    </text>
                  ) : null,
                )}
                {overlay.levels?.map((l, k) =>
                  l.label ? (
                    <text
                      key={`vt${k}`}
                      className={`mcx-level-t is-${l.tone}`}
                      x={(l.from ? Math.max(PAD.left, g.x(idxAt(l.from))) : PAD.left) + 4}
                      y={g.y(l.price) - 3}
                    >
                      {l.label}
                    </text>
                  ) : null,
                )}
                {overlay.markers?.map((m, k) => {
                  const i = idxAt(m.at);
                  if (!(i >= -0.5 && i <= candles.length - 0.5)) return null;
                  const mx = g.x(i);
                  const my = g.y(m.price);
                  if (my < PAD.top - 2 || my > g.priceBottom + 2) return null;
                  const cls = `mcx-mark is-${m.tone} ${m.muted ? 'is-muted' : ''}`;
                  if (m.shape === 'text') {
                    return (
                      <text key={`m${k}`} className={`${cls} is-text`} x={mx} y={m.below ? my + 13 : my - 5} textAnchor="middle">
                        {m.label}
                      </text>
                    );
                  }
                  const below = m.shape === 'up';
                  const ty = below ? my + 22 : my - 15;
                  return (
                    <g key={`m${k}`} {...pick(m.id)} className={cls}>
                      {m.shape === 'up' ? (
                        <path d={`M${mx},${my + 5} l5,8 h-10 z`} />
                      ) : m.shape === 'down' ? (
                        <path d={`M${mx},${my - 5} l5,-8 h-10 z`} />
                      ) : m.shape === 'diamond' ? (
                        <path d={`M${mx},${my - 5} l5,5 l-5,5 l-5,-5 z`} />
                      ) : (
                        <circle cx={mx} cy={my} r={4} />
                      )}
                      {m.label ? (
                        <text x={mx} y={m.shape === 'dot' || m.shape === 'diamond' ? my - 8 : ty} textAnchor="middle">
                          {m.label}
                        </text>
                      ) : null}
                    </g>
                  );
                })}
                {overlay.paths?.map((p, k) => {
                  const pts = p.points.map(([t, v]) => [g.x(idxAt(t)), g.y(v)] as const).filter(([px, py]) => Number.isFinite(px) && Number.isFinite(py));
                  if (pts.length < 2) return null;
                  const [ax, ay] = pts[pts.length - 2];
                  const [bx, by] = pts[pts.length - 1];
                  const ang = Math.atan2(by - ay, bx - ax);
                  const head = (s: number) => `${bx - 9 * Math.cos(ang + s)},${by - 9 * Math.sin(ang + s)}`;
                  return (
                    <g key={`p${k}`} {...pick(p.id)} className={`mcx-path is-${p.tone} ${p.dashed ? 'is-dashed' : ''}`}>
                      <polyline points={pts.map(([px, py]) => `${px},${py}`).join(' ')} />
                      {pts.slice(1, -1).map(([px, py], j) => (
                        <circle key={j} cx={px} cy={py} r={2.5} />
                      ))}
                      {p.arrow !== false ? <path className="mcx-path-head" d={`M${bx},${by} L${head(0.45)} L${head(-0.45)} Z`} /> : null}
                    </g>
                  );
                })}
                {overlay.tags?.map((t, k) => {
                  const w = TAG_W;
                  const h = t.value ? 30 : 18;
                  const ax = t.at != null ? g.x(idxAt(t.at)) - w / 2 : width - PAD.right - w - 6;
                  const bx = Math.max(PAD.left + 2, Math.min(width - PAD.right - w - 2, ax));
                  const py = g.y(t.price);
                  const raw = t.place === 'above' ? py - h - 8 : t.place === 'below' ? py + 8 : py - h / 2;
                  const by = Math.max(PAD.top, Math.min(g.priceBottom - h, raw));
                  return (
                    <g key={`t${k}`} {...pick(t.id)} className={`mcx-tag is-${t.tone}`}>
                      <rect x={bx} y={by} width={w} height={h} rx={5} />
                      <text className="mcx-tag-t" x={bx + w / 2} y={by + 12} textAnchor="middle">
                        {t.title}
                      </text>
                      {t.value ? (
                        <text className="mcx-tag-v" x={bx + w / 2} y={by + 25} textAnchor="middle">
                          {t.value}
                        </text>
                      ) : null}
                    </g>
                  );
                })}
              </g>
            ) : null}

            {hover !== null ? <line className="mst-cross" x1={g.x(hover)} x2={g.x(hover)} y1={PAD.top} y2={g.plotBottom} /> : null}

            {lastPrice != null ? (
              <g className="mst-last">
                <line x1={PAD.left} x2={width - PAD.right} y1={g.y(lastPrice)} y2={g.y(lastPrice)} />
                <rect x={width - PAD.right + 1} y={g.y(lastPrice) - 9} width={PAD.right - 2} height={18} rx={3} />
                <text x={width - PAD.right + 5} y={g.y(lastPrice) + 4}>
                  {fmtPrice(lastPrice, digits)}
                </text>
              </g>
            ) : null}
          </svg>
        )}
        {g && hover !== null ? (
          <div className="mst-tip" style={{ left: Math.min(width - 180, Math.max(4, g.x(hover) + 10)) }}>
            <strong>{new Date(candles[hover].t).toISOString().slice(0, 16).replace('T', ' ')} UTC</strong>
            <span>
              O {fmtPrice(candles[hover].o, digits)} H {fmtPrice(candles[hover].h, digits)}
            </span>
            <span>
              L {fmtPrice(candles[hover].l, digits)} C {fmtPrice(candles[hover].c, digits)}
            </span>
          </div>
        ) : null}
      </div>
      {legend?.length ? (
        <footer className="mst-legend">
          {legend.map((l) => (
            <span key={l.label}>
              <i className={`mcx-sw ${l.swatch}`} /> {l.label}
            </span>
          ))}
        </footer>
      ) : range ? (
        <footer className="mst-legend">
          <span>
            <i className="mst-lg-fh" /> Fractal High
          </span>
          <span>
            <i className="mst-lg-fl" /> Fractal Low
          </span>
          <span>
            <i className="mst-lg-zh" /> Range High Zone
          </span>
          <span>
            <i className="mst-lg-zl" /> Range Low Zone
          </span>
          <span>
            <i className="mst-lg-mid" /> Midpoint
          </span>
        </footer>
      ) : null}
    </section>
  );
}

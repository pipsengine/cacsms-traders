import { useEffect, useId, useMemo, useRef, useState } from 'react';
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
      if (tf === 'W') {
        if (d.getUTCMonth() !== prev.getUTCMonth() && d.getUTCMonth() % 3 === 0) {
          const jan = d.getUTCMonth() === 0;
          out.push({ i, text: jan ? String(d.getUTCFullYear()) : fmt(d, { month: 'short' }), strong: jan });
        }
      } else if (tf === 'D1') {
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
    const priceBottom = plotBottom - VOL_H - 4;
    const step = (width - PAD.left - PAD.right) / candles.length;
    const x = (i: number) => PAD.left + step * (i + 0.5);
    const y = (v: number) => PAD.top + ((hi - v) / (hi - lo)) * (priceBottom - PAD.top);
    const vmax = Math.max(1, ...candles.map((c) => c.v || 0));
    const tickCount = Math.max(4, Math.round((priceBottom - PAD.top) / TICK_SPACING_PX));
    return { lo, hi, step, x, y, plotBottom, priceBottom, vmax, tickCount };
  }, [candles, width, height, lastPrice, range, ch]);

  const last = candles[candles.length - 1];
  const prev = candles[candles.length - 2];
  const chg = last && prev ? last.c - prev.c : null;
  const chgPct = chg != null && prev ? (chg / prev.c) * 100 : null;
  const cls = chg == null ? '' : chg >= 0 ? 'up' : 'down';
  const tfLabel = tf === 'W' ? 'W' : tf;

  return (
    <section className="mst-card mst-chart-card">
      <header className="mst-chart-head">
        <strong>
          <InstrumentIcon base={symbol.slice(0, 3)} quote={symbol.slice(3, 6)} size="sm" /> {symbol} · {title}
        </strong>
        <span className="mst-tf-badge">{tfLabel}</span>
      </header>
      <div className="mst-ohlc">
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
            {axisLabels(candles, tf).map((l) => (
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
            {candles.map((c, i) => {
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
      {range ? (
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

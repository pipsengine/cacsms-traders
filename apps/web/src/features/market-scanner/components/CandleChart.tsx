import { useEffect, useMemo, useRef, useState } from 'react';
import { fmtPrice } from '../format';
import type { Candle, Channel } from '../types';

const PAD = { top: 10, right: 62, bottom: 22, left: 6 };

function niceTicks(lo: number, hi: number, count: number) {
  const span = hi - lo || Math.abs(hi) || 1;
  const raw = span / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  const out: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) out.push(v);
  return out;
}

function timeLabel(iso: string, timeframe: string) {
  const d = new Date(iso);
  const opts: Intl.DateTimeFormatOptions =
    timeframe === 'MN'
      ? { month: 'short', year: '2-digit', timeZone: 'UTC' }
      : timeframe === 'D1' || timeframe === 'W'
        ? { day: '2-digit', month: 'short', timeZone: 'UTC' }
        : { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'UTC' };
  return new Intl.DateTimeFormat('en-GB', opts).format(d);
}

/** Closed-candle SVG chart with the latest quote marked on the price axis. */
export function CandleChart({
  candles,
  timeframe,
  digits,
  lastPrice,
  channel,
  height = 220,
}: {
  candles: Candle[];
  timeframe: string;
  digits: number;
  lastPrice?: number | null;
  channel?: Channel | null;
  height?: number;
}) {
  const wrap = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(360);
  const [hover, setHover] = useState<number | null>(null);

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(240, Math.floor(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const overlay = useMemo(() => {
    if (!channel || channel.mid === undefined || channel.upper === undefined || !channel.period || timeframe !== 'D1') return null;
    const n = candles.length;
    if (n < channel.period) return null;
    const slope = ((channel.slope_pct_per_bar ?? 0) * channel.mid) / 100;
    const half = channel.upper - channel.mid;
    const i0 = n - channel.period;
    const m0 = channel.mid - slope * (channel.period - 1);
    return { i0, i1: n - 1, m0, m1: channel.mid, half };
  }, [channel, candles.length, timeframe]);

  const geo = useMemo(() => {
    if (!candles.length) return null;
    let lo = Math.min(...candles.map((c) => c.l));
    let hi = Math.max(...candles.map((c) => c.h));
    if (lastPrice != null) {
      lo = Math.min(lo, lastPrice);
      hi = Math.max(hi, lastPrice);
    }
    if (overlay) {
      lo = Math.min(lo, overlay.m0 - overlay.half, overlay.m1 - overlay.half);
      hi = Math.max(hi, overlay.m0 + overlay.half, overlay.m1 + overlay.half);
    }
    const padY = (hi - lo) * 0.06 || hi * 0.001;
    lo -= padY;
    hi += padY;
    const plotW = width - PAD.left - PAD.right;
    const plotH = height - PAD.top - PAD.bottom;
    const step = plotW / candles.length;
    const x = (i: number) => PAD.left + step * (i + 0.5);
    const y = (v: number) => PAD.top + ((hi - v) / (hi - lo)) * plotH;
    return { lo, hi, step, x, y, plotW, plotH };
  }, [candles, width, height, lastPrice, overlay]);

  if (!geo) return <div ref={wrap} className="ms-chart-empty" style={{ height }} />;

  const { step, x, y, lo, hi } = geo;
  const body = Math.max(1, Math.min(10, step * 0.62));
  const ticks = niceTicks(lo, hi, 5);
  const labelEvery = Math.max(1, Math.ceil(candles.length / Math.max(2, Math.floor(width / 80))));
  const hc = hover !== null ? candles[hover] : null;

  return (
    <div ref={wrap} className="ms-chart" style={{ height }}>
      <svg
        width={width}
        height={height}
        role="img"
        aria-label={`${timeframe} candlestick chart`}
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const rect = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
          const i = Math.floor((e.clientX - rect.left - PAD.left) / step);
          setHover(i >= 0 && i < candles.length ? i : null);
        }}
      >
        {ticks.map((t) => (
          <g key={t}>
            <line x1={PAD.left} x2={width - PAD.right} y1={y(t)} y2={y(t)} className="ms-chart-grid" />
            <text x={width - PAD.right + 6} y={y(t) + 3.5} className="ms-chart-axis">
              {fmtPrice(t, digits)}
            </text>
          </g>
        ))}
        {candles.map((c, i) =>
          i % labelEvery === 0 ? (
            <text key={c.t} x={x(i)} y={height - 6} textAnchor="middle" className="ms-chart-axis">
              {timeLabel(c.t, timeframe)}
            </text>
          ) : null,
        )}
        {overlay ? (
          <g className="ms-chart-channel">
            {[-1, 0, 1].map((k) => (
              <line
                key={k}
                x1={x(overlay.i0)}
                x2={x(overlay.i1)}
                y1={y(overlay.m0 + k * overlay.half)}
                y2={y(overlay.m1 + k * overlay.half)}
                className={k === 0 ? 'is-mid' : 'is-edge'}
              />
            ))}
          </g>
        ) : null}
        {candles.map((c, i) => {
          const upC = c.c >= c.o;
          const top = y(Math.max(c.o, c.c));
          const h = Math.max(1, Math.abs(y(c.o) - y(c.c)));
          return (
            <g key={c.t} className={upC ? 'ms-candle-up' : 'ms-candle-down'}>
              <line x1={x(i)} x2={x(i)} y1={y(c.h)} y2={y(c.l)} />
              <rect x={x(i) - body / 2} y={top} width={body} height={h} rx={0.6} />
            </g>
          );
        })}
        {hover !== null ? <line x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={height - PAD.bottom} className="ms-chart-cross" /> : null}
        {lastPrice != null ? (
          <g className="ms-chart-last">
            <line x1={PAD.left} x2={width - PAD.right} y1={y(lastPrice)} y2={y(lastPrice)} />
            <rect x={width - PAD.right + 1} y={y(lastPrice) - 9} width={PAD.right - 2} height={18} rx={4} />
            <text x={width - PAD.right + 6} y={y(lastPrice) + 4}>
              {fmtPrice(lastPrice, digits)}
            </text>
          </g>
        ) : null}
      </svg>
      {hc ? (
        <div className="ms-chart-tip" style={{ left: Math.min(width - 170, Math.max(4, x(hover!) + 10)) }}>
          <strong>{new Date(hc.t).toISOString().slice(0, 16).replace('T', ' ')} UTC</strong>
          <span>
            O {fmtPrice(hc.o, digits)} H {fmtPrice(hc.h, digits)}
          </span>
          <span>
            L {fmtPrice(hc.l, digits)} C {fmtPrice(hc.c, digits)}
          </span>
        </div>
      ) : null}
    </div>
  );
}

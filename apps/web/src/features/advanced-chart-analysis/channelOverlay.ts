import type { ChannelLines, ChannelTf } from '../channel-intelligence/types';
import type { Candle, Drawing } from './types';

const CHANNEL_TFS = new Set<string>(['Y', 'YTD', 'HY', 'Q', 'MN', 'W', 'D1', 'H8', 'H1']);

/** Prefer parent TFs in fullscreen for context (mock-style stack). */
export const FULLSCREEN_CHANNEL_TFS: ChannelTf[] = ['W', 'D1', 'H8', 'MN'];

export function mapChartTfToChannelTf(tf: string): ChannelTf {
  const t = tf.toUpperCase();
  if (t === 'W1') return 'W';
  if (CHANNEL_TFS.has(t)) return t as ChannelTf;
  return 'H1';
}

function isoToUnix(iso: string): number {
  return Math.floor(new Date(iso.replace('Z', '+00:00')).getTime() / 1000);
}

/** Extrapolate regression line across the visible candle window (TradingView-style). */
export function extendLineToCandleRange(
  line: ChannelLines['upper'],
  candles: Candle[],
): [{ time: number; price: number }, { time: number; price: number }] {
  const t0 = isoToUnix(line[0][0]);
  const p0 = line[0][1];
  const t1 = isoToUnix(line[1][0]);
  const p1 = line[1][1];
  if (!candles.length) {
    return [
      { time: t0, price: p0 },
      { time: t1, price: p1 },
    ];
  }
  const tLeft = candles[0].time;
  const tRight = candles[candles.length - 1].time;
  if (t1 === t0) {
    return [
      { time: tLeft, price: p0 },
      { time: tRight, price: p0 },
    ];
  }
  const slope = (p1 - p0) / (t1 - t0);
  const priceAt = (t: number) => p0 + slope * (t - t0);
  return [
    { time: tLeft, price: priceAt(tLeft) },
    { time: tRight, price: priceAt(tRight) },
  ];
}

function lineToDrawing(
  id: string,
  symbol: string,
  timeframe: string,
  line: ChannelLines['upper'],
  candles: Candle[],
  color: string,
  label: string,
): Drawing {
  const [a, b] = extendLineToCandleRange(line, candles);
  return {
    id,
    symbol,
    timeframe,
    kind: 'trendline',
    points: [a, b],
    color,
    label,
  };
}

export function channelLinesToDrawings(
  symbol: string,
  timeframe: string,
  lines: ChannelLines,
  candles: Candle[],
  channelTf: string,
  variant: 'primary' | 'parent' = 'primary',
): Drawing[] {
  const prefix = variant === 'primary' ? 'fs-ch' : `fs-ch-${channelTf.toLowerCase()}`;
  const upperColor = variant === 'primary' ? '#1d4ed8' : '#94a3b8';
  const midColor = variant === 'primary' ? '#38bdf8' : '#cbd5e1';
  const lowerColor = variant === 'primary' ? '#1d4ed8' : '#94a3b8';
  const tag = variant === 'primary' ? '' : ` ${channelTf}`;
  return [
    lineToDrawing(`${prefix}-upper`, symbol, timeframe, lines.upper, candles, upperColor, `Upper${tag}`),
    lineToDrawing(`${prefix}-mid`, symbol, timeframe, lines.mid, candles, midColor, `Mid${tag}`),
    lineToDrawing(`${prefix}-lower`, symbol, timeframe, lines.lower, candles, lowerColor, `Lower${tag}`),
    {
      id: `${prefix}-band`,
      symbol,
      timeframe,
      kind: 'trendline',
      points: [
        ...extendLineToCandleRange(lines.upper, candles),
        ...extendLineToCandleRange(lines.lower, candles).slice().reverse(),
      ],
      color: variant === 'primary' ? '#3b82f6' : '#94a3b8',
      label: `${channelTf} channel`,
    },
  ];
}

import type { Candle } from './types';

export function snapToOhlc(candles: Candle[], time: number, price: number): { time: number; price: number } {
  if (!candles.length) return { time, price };
  let bar = candles[0];
  let best = Math.abs(bar.time - time);
  for (const c of candles) {
    const d = Math.abs(c.time - time);
    if (d < best) {
      best = d;
      bar = c;
    }
  }
  const candidates = [bar.open, bar.high, bar.low, bar.close];
  const snapped = candidates.reduce((a, b) => (Math.abs(b - price) < Math.abs(a - price) ? b : a));
  return { time: bar.time, price: snapped };
}

export function emaSeries(candles: Candle[], period: number): { time: number; value: number }[] {
  let ema = 0;
  const k = 2 / (period + 1);
  return candles.map((c, i) => {
    ema = i === 0 ? c.close : ema + (c.close - ema) * k;
    return { time: c.time, value: ema };
  });
}

/** Supertrend (10, 3) — display overlay only. */
export function supertrend(candles: Candle[], period = 10, mult = 3): { time: number; value: number; up: boolean }[] {
  if (candles.length < period + 2) return [];
  const out: { time: number; value: number; up: boolean }[] = [];
  let prevUpper = 0;
  let prevLower = 0;
  let prevSt = 0;
  let up = true;
  for (let i = 0; i < candles.length; i++) {
    const c = candles[i];
    if (i < period) {
      out.push({ time: c.time, value: c.close, up: true });
      continue;
    }
    const slice = candles.slice(i - period + 1, i + 1);
    const trs = slice.map((x, j) => {
      if (j === 0) return x.high - x.low;
      const prev = slice[j - 1];
      return Math.max(x.high - x.low, Math.abs(x.high - prev.close), Math.abs(x.low - prev.close));
    });
    const atr = trs.reduce((a, b) => a + b, 0) / period;
    const hl2 = (c.high + c.low) / 2;
    const upper = hl2 + mult * atr;
    const lower = hl2 - mult * atr;
    const finUpper = upper < prevUpper || candles[i - 1].close > prevUpper ? upper : prevUpper;
    const finLower = lower > prevLower || candles[i - 1].close < prevLower ? lower : prevLower;
    if (prevSt === prevUpper) {
      up = c.close <= finUpper;
    } else {
      up = c.close >= finLower;
    }
    const st = up ? finLower : finUpper;
    out.push({ time: c.time, value: st, up });
    prevUpper = finUpper;
    prevLower = finLower;
    prevSt = st;
  }
  return out;
}

export const FIB_LEVELS = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1] as const;

export function fibPrices(low: number, high: number): { level: number; price: number }[] {
  const a = Math.min(low, high);
  const b = Math.max(low, high);
  return FIB_LEVELS.map((level) => ({ level, price: a + (b - a) * level }));
}

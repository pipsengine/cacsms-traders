import { useCallback, useMemo, useRef } from 'react';
import { usePollingAsync } from '../market-intelligence/hooks/useMarketIntelligence';
import { marketStructureApi } from './api';
import type { VCandle } from './types';

export type LiveQuote = { bid: number; ask: number; price: number; spread: number; time: string; age_seconds: number; stale: boolean };
export type LivePayload = {
  symbol: string;
  provider: string | null;
  server_time: string;
  quote: LiveQuote | null;
  forming: Record<string, VCandle | null>;
  error: string | null;
};

export const LIVE_INTERVAL_MS = 1000;

/** Latest tick plus the forming bar for each timeframe, refreshed every second while the page is visible. */
export function useLive(symbol: string | null, timeframes: readonly string[], enabled: boolean) {
  const key = [...new Set(timeframes)].join(',');
  const loader = useCallback(() => (symbol ? marketStructureApi.live(symbol, key) : Promise.resolve(null)), [symbol, key]);
  const res = usePollingAsync(loader, [loader], { enabled: enabled && !!symbol && !!key, intervalMs: LIVE_INTERVAL_MS });
  const data = res.data && res.data.symbol === symbol ? res.data : null;
  return { data, error: res.error };
}

const HELD_BARS = 3;

/**
 * Closed candles plus the live forming bar. A bar that has just closed keeps its final live values until the
 * closed series catches up, so a bar boundary never leaves a gap. A forming bar with the same time as the last
 * closed bar (calendar aggregates such as Y / Q) replaces it.
 */
export function useLiveCandles(scope: string, closed: VCandle[], forming: VCandle | null | undefined): VCandle[] {
  const held = useRef<{ scope: string; bars: Map<number, VCandle> }>({ scope, bars: new Map() });
  return useMemo(() => {
    if (held.current.scope !== scope) held.current = { scope, bars: new Map() };
    const bars = held.current.bars;
    if (!closed.length) return closed;
    const lastClosed = Date.parse(closed[closed.length - 1].t);
    const ft = forming ? Date.parse(forming.t) : null;
    if (forming && ft != null) bars.set(ft, forming);
    for (const t of [...bars.keys()]) if (t < lastClosed || (t === lastClosed && t !== ft)) bars.delete(t);
    const kept = [...bars.entries()].sort((a, b) => a[0] - b[0]);
    for (const [t] of kept.slice(0, Math.max(0, kept.length - HELD_BARS))) bars.delete(t);
    if (!bars.size) return closed;
    const out = closed.slice();
    for (const [t, bar] of kept.slice(-HELD_BARS)) {
      if (t === lastClosed) out[out.length - 1] = bar;
      else out.push(bar);
    }
    return out;
  }, [scope, closed, forming]);
}

export type LiveState = { tone: 'live' | 'delayed' | 'off'; label: string; title: string };

const TIME = new Intl.DateTimeFormat('en-GB', { timeZone: 'Africa/Lagos', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });

export function liveState(data: LivePayload | null, error: string): LiveState {
  const q = data?.quote;
  if (!q) {
    const why = data?.error || error || 'No live quote from the market-data provider';
    return { tone: 'off', label: 'No live feed', title: why };
  }
  const at = `${TIME.format(new Date(q.time))} WAT`;
  const provider = data?.provider === 'ctrader' ? 'cTrader' : data?.provider === 'mt5' ? 'MT5' : data?.provider ?? 'provider';
  if (q.age_seconds <= 15) return { tone: 'live', label: `Live ${at}`, title: `Last ${provider} tick ${at} · updates every second` };
  return { tone: 'delayed', label: `Last tick ${at}`, title: `No ${provider} tick for ${Math.round(q.age_seconds)}s (market quiet or feed delayed)` };
}

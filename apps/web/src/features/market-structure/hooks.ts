import { useCallback, useEffect, useState } from 'react';
import { usePollingAsync } from '../market-intelligence/hooks/useMarketIntelligence';
import type { ScannerMeta } from '../market-scanner/types';
import { marketStructureApi } from './api';

export function useVisible() {
  const [visible, setVisible] = useState(() => typeof document === 'undefined' || document.visibilityState === 'visible');
  useEffect(() => {
    const onVis = () => setVisible(document.visibilityState === 'visible');
    document.addEventListener('visibilitychange', onVis);
    return () => document.removeEventListener('visibilitychange', onVis);
  }, []);
  return visible;
}

const SHORT_SCREEN = '(max-height: 900px)';

export function useShortScreen() {
  const [short, setShort] = useState(() => typeof window !== 'undefined' && window.matchMedia(SHORT_SCREEN).matches);
  useEffect(() => {
    const mq = window.matchMedia(SHORT_SCREEN);
    const onChange = () => setShort(mq.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);
  return short;
}

export function useCandles(symbol: string, tf: string, enabled: boolean, tick: number, limit: number) {
  const loader = useCallback(() => marketStructureApi.candles(symbol, tf, limit), [symbol, tf, tick, limit]);
  const res = usePollingAsync(loader, [loader], { enabled, intervalMs: 60000 });
  const ok = res.data?.symbol === symbol && res.data.timeframe === tf;
  return { candles: ok ? res.data!.candles : [], loading: res.loading || !ok, error: res.error };
}

export function liveStatus(meta: Pick<ScannerMeta, 'mt5_connected' | 'stale'> | null, error: boolean) {
  if (!meta) return { tone: error ? 'off' : 'warn', label: error ? 'Analysis Unavailable' : 'Connecting' };
  if (!meta.mt5_connected) return { tone: 'off', label: 'MT5 Disconnected' };
  if (meta.stale) return { tone: 'warn', label: 'Stale Analysis' };
  return { tone: 'live', label: 'Live Analysis' };
}

export function localStamp(iso: string | null | undefined) {
  if (!iso) return '—';
  return new Intl.DateTimeFormat('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZoneName: 'short',
  }).format(new Date(iso));
}

import type { OverviewPayload, RangeDetail, RangePayload, TrendDetail, TrendPayload, VCandle } from './types';
import { apiFetch } from '../../lib/api';

const root = '/market-intelligence';

async function get<T>(path: string): Promise<T> {
  const r = await apiFetch(`${root}${path}`);
  if (!r.ok) {
    const text = await r.text();
    throw new Error(text || r.statusText || 'Request failed');
  }
  return r.json();
}

export const marketStructureApi = {
  overview: () => get<OverviewPayload>('/structure/overview'),
  ranges: () => get<RangePayload>('/structure/range'),
  range: (symbol: string) => get<RangeDetail>(`/structure/range/${encodeURIComponent(symbol)}`),
  trends: () => get<TrendPayload>('/structure/trend'),
  trend: (symbol: string) => get<TrendDetail>(`/structure/trend/${encodeURIComponent(symbol)}`),
  candles: (symbol: string, timeframe: string, limit: number) =>
    get<{ symbol: string; timeframe: string; candles: VCandle[] }>(
      `/scanner/${encodeURIComponent(symbol)}/candles?${new URLSearchParams({ timeframe, limit: String(limit) })}`,
    ),
};

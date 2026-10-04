import type { OverviewPayload, RangeDetail, RangePayload, VCandle } from './types';

const BASE = import.meta.env.VITE_API_BASE ?? '';
const root = `${BASE}/api/market-intelligence`;

async function get<T>(path: string): Promise<T> {
  const token = localStorage.getItem('ct_token');
  const headers = new Headers();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const r = await fetch(`${root}${path}`, { credentials: 'include', headers });
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
  candles: (symbol: string, timeframe: string, limit: number) =>
    get<{ symbol: string; timeframe: string; candles: VCandle[] }>(
      `/scanner/${encodeURIComponent(symbol)}/candles?${new URLSearchParams({ timeframe, limit: String(limit) })}`,
    ),
};

import type {
  BosDetail,
  BosPayload,
  FractalDetail,
  FractalPayload,
  OverviewPayload,
  RangeDetail,
  RangePayload,
  TrendDetail,
  TrendPayload,
  VCandle,
} from './types';
import type { LivePayload } from './live';
import { apiFetch } from '../../lib/api';

const root = '/market-intelligence';

export async function get<T>(path: string): Promise<T> {
  const r = await apiFetch(`${root}${path}`);
  if (!r.ok) {
    const text = await r.text();
    throw new Error(text || r.statusText || 'Request failed');
  }
  return r.json();
}

const q = (params: Record<string, string>) => new URLSearchParams(params).toString();

export const marketStructureApi = {
  overview: () => get<OverviewPayload>('/structure/overview'),
  ranges: () => get<RangePayload>('/structure/range'),
  range: (symbol: string) => get<RangeDetail>(`/structure/range/${encodeURIComponent(symbol)}`),
  trends: () => get<TrendPayload>('/structure/trend'),
  trend: (symbol: string) => get<TrendDetail>(`/structure/trend/${encodeURIComponent(symbol)}`),
  fractals: () => get<FractalPayload>('/structure/fractals'),
  fractal: (symbol: string, timeframe: string) =>
    get<FractalDetail>(`/structure/fractals/${encodeURIComponent(symbol)}?${q({ timeframe })}`),
  bos: () => get<BosPayload>('/structure/bos'),
  bosDetail: (symbol: string, timeframe: string) => get<BosDetail>(`/structure/bos/${encodeURIComponent(symbol)}?${q({ timeframe })}`),
  live: (symbol: string, timeframes: string) => get<LivePayload>(`/scanner/${encodeURIComponent(symbol)}/live?${q({ timeframes })}`),
  candles: (symbol: string, timeframe: string, limit: number) =>
    get<{ symbol: string; timeframe: string; candles: VCandle[] }>(
      `/scanner/${encodeURIComponent(symbol)}/candles?${q({ timeframe, limit: String(limit) })}`,
    ),
};

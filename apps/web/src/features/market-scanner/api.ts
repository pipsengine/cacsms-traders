import type { CandlesPayload, ChartTimeframe, ScannerDetailPayload, ScannerPayload } from './types';
import { apiFetch } from '../../lib/api';

const root = '/market-intelligence/scanner';

async function get<T>(path: string): Promise<T> {
  const r = await apiFetch(`${root}${path}`);
  if (!r.ok) {
    const text = await r.text();
    throw new Error(text || r.statusText || 'Request failed');
  }
  return r.json();
}

export const marketScannerApi = {
  scanner: () => get<ScannerPayload>(''),
  instrument: (symbol: string) => get<ScannerDetailPayload>(`/${encodeURIComponent(symbol)}`),
  candles: (symbol: string, timeframe: ChartTimeframe, limit = 120) =>
    get<CandlesPayload>(`/${encodeURIComponent(symbol)}/candles?${new URLSearchParams({ timeframe, limit: String(limit) })}`),
};

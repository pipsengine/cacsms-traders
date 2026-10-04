import type { CandlesPayload, ChartTimeframe, ScannerDetailPayload, ScannerPayload } from './types';

const BASE = import.meta.env.VITE_API_BASE ?? '';
const root = `${BASE}/api/market-intelligence/scanner`;

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

export const marketScannerApi = {
  scanner: () => get<ScannerPayload>(''),
  instrument: (symbol: string) => get<ScannerDetailPayload>(`/${encodeURIComponent(symbol)}`),
  candles: (symbol: string, timeframe: ChartTimeframe, limit = 120) =>
    get<CandlesPayload>(`/${encodeURIComponent(symbol)}/candles?${new URLSearchParams({ timeframe, limit: String(limit) })}`),
};

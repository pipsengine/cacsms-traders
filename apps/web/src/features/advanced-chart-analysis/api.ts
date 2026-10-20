import { apiFetch } from '../../lib/api';
import type { Analysis, Candle, Drawing, Overlay, Quote, Workspace } from './types';

async function req<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const headers = new Headers(opts.headers);
  if (opts.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  const r = await apiFetch(`/chart${path}`, { ...opts, headers });
  if (!r.ok) {
    const text = await r.text();
    let message = text.slice(0, 240) || r.statusText;
    try {
      const detail = JSON.parse(text).detail;
      if (typeof detail === 'string' && detail.trim()) message = detail;
    } catch {
      /* body is already plain text */
    }
    throw new Error(message);
  }
  return r.json() as Promise<T>;
}

const json = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body) });

export const chartApi = {
  symbols: () => req<string[]>('/symbols'),
  candles: (symbol: string, tf: string, limit = 700) =>
    req<Candle[]>(`/candles?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(tf)}&limit=${limit}`),
  quote: (symbol: string) => req<Quote>(`/quote?symbol=${encodeURIComponent(symbol)}`),
  quotes: (symbols: string[]) =>
    req<Record<string, Quote>>(`/quotes?symbols=${encodeURIComponent(symbols.join(','))}`),
  overlays: (symbol: string, tf: string) =>
    req<Overlay[]>(`/overlays?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(tf)}`),
  workspace: (symbol: string, tf: string) =>
    req<Workspace & { updated_at?: string | null }>(
      `/workspace?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(tf)}`,
    ),
  saveWorkspace: (v: Workspace & { expected_updated_at?: string | null }) => req<Workspace & { updated_at?: string }>('/workspace', json(v)),
  analyses: (symbol: string) => req<Analysis[]>(`/analyses?symbol=${encodeURIComponent(symbol)}`),
  saveAnalysis: (a: { symbol: string; timeframe: string; title: string; notes: string }) =>
    req<Analysis>('/analyses', json(a)),
  createOpportunity: (v: {
    symbol: string;
    timeframe: string;
    direction: string;
    strategy: string;
    notes: string;
    analysis_id?: string;
  }) => req<{ id: string; status: string }>('/opportunities', json(v)),
};

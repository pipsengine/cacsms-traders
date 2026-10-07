import { api, post } from '../../lib/api';
import type { HistoryPayload, LatestPayload, MtfPayload, RunSummary, SymbolPayload } from './types';

const root = '/ai-outlook';
const q = (params: Record<string, string | null | undefined>) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v) p.set(k, v);
  const s = p.toString();
  return s ? `?${s}` : '';
};

export const outlookApi = {
  latest: (date?: string | null) => api<LatestPayload>(`${root}/latest${q({ analysis_date: date })}`),
  symbol: (symbol: string, date?: string | null) =>
    api<SymbolPayload>(`${root}/symbol/${encodeURIComponent(symbol)}${q({ analysis_date: date })}`),
  mtf: (symbol: string, date?: string | null, limit = 60) =>
    api<MtfPayload>(`${root}/symbol/${encodeURIComponent(symbol)}/mtf${q({ analysis_date: date, limit: String(limit) })}`),
  history: (symbol: string, days: number) => api<HistoryPayload>(`${root}/history${q({ symbol, days: String(days) })}`),
  runNow: () => post<{ run: RunSummary | null; skipped: string | null }>(`${root}/jobs/run`, {}),
};

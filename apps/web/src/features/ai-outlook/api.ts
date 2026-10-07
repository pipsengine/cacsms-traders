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
  catchUp: () => post<{ ran: boolean; reason: string | null }>(`${root}/jobs/catch-up`, {}),
};

const CACHE = { latest: 'cacsms.mao.latest', detail: 'cacsms.mao.detail' } as const;

/** Last good response, kept for this browser tab so a revisit renders instantly while the fresh read is in flight. */
export const outlookCache = {
  read<K extends keyof typeof CACHE>(key: K): (K extends 'latest' ? LatestPayload : SymbolPayload) | null {
    try {
      const raw = sessionStorage.getItem(CACHE[key]);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  },
  write(key: keyof typeof CACHE, value: LatestPayload | SymbolPayload | null) {
    if (!value) return;
    try {
      sessionStorage.setItem(CACHE[key], JSON.stringify(value));
    } catch {
      /* storage full or unavailable: caching is best-effort */
    }
  },
};

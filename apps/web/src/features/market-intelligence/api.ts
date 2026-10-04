import type {
  StrengthMatrixPayload,
  StrengthRow,
  RelationshipRow,
  QualityRow,
  CalculationMode,
  HistoricalStrengthPayload,
  HistoryPeriod,
  PairRelationshipsPayload,
  RelationshipAnalysisPayload,
} from './types';

const BASE = import.meta.env.VITE_API_BASE ?? '';
const root = `${BASE}/api/market-intelligence`;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = localStorage.getItem('ct_token');
  const headers = new Headers(init?.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (init?.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  const r = await fetch(`${root}${path}`, { credentials: 'include', headers, ...init });
  if (!r.ok) {
    const text = await r.text();
    throw new Error(text || r.statusText || 'Request failed');
  }
  return r.json();
}

function get<T>(path: string) {
  return request<T>(path);
}

export const marketIntelligenceApi = {
  matrix: (sortBy = 'AVG', calculationMode: CalculationMode = 'CLOSE_CLOSE') =>
    get<StrengthMatrixPayload>(
      `/matrix?${new URLSearchParams({ sort_by: sortBy, calculation_mode: calculationMode })}`,
    ),
  runCycle: (ingest = true) =>
    request<Record<string, unknown>>(`/cycle?ingest=${ingest ? 'true' : 'false'}`, { method: 'POST' }),
  ingest: () => request<Record<string, unknown>>('/ingest', { method: 'POST' }),
  status: () => get<{ market_data: Record<string, unknown> }>('/status'),
  relationships: (tf?: string, state?: string) =>
    get<RelationshipRow[]>(
      `/relationships?${new URLSearchParams({ ...(tf && { timeframe: tf }), ...(state && { state }) })}`,
    ),
  strengthHistory: (c: string, tf: string) =>
    get<StrengthRow[]>(`/strength/${c}/history?timeframe=${tf}`),
  strengthSparklines: (timeframe = 'AVG', limit = 32) =>
    get<Record<string, { as_of: string; score: number }[]>>(
      `/strength/sparklines?timeframe=${timeframe}&limit=${limit}`,
    ),
  relationshipHistory: (p: string, tf: string) =>
    get<RelationshipRow[]>(`/relationships/${p}/history?timeframe=${tf}`),
  historicalStrength: (period: HistoryPeriod, timeframe = 'AVG') =>
    get<HistoricalStrengthPayload>(`/strength/historical?${new URLSearchParams({ period, timeframe })}`),
  pairRelationships: () => get<PairRelationshipsPayload>('/relationships/pairs'),
  relationshipAnalysis: (pair: string, period: HistoryPeriod) =>
    get<RelationshipAnalysisPayload>(
      `/relationships/pairs/${encodeURIComponent(pair)}/analysis?${new URLSearchParams({ period })}`,
    ),
  quality: () => get<QualityRow[]>('/data-quality'),
  health: () => get<{ status: string }>('/health'),
};

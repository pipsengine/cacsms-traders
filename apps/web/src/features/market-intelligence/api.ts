import type { StrengthRow, RelationshipRow, QualityRow } from './types';

const BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000';
const root = `${BASE}/api/market-intelligence`;

async function get<T>(path: string): Promise<T> {
  const token = localStorage.getItem('ct_token');
  const headers = new Headers();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const r = await fetch(`${root}${path}`, { credentials: 'include', headers });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export const marketIntelligenceApi = {
  matrix: () => get<StrengthRow[]>('/matrix'),
  relationships: (tf?: string, state?: string) =>
    get<RelationshipRow[]>(
      `/relationships?${new URLSearchParams({ ...(tf && { timeframe: tf }), ...(state && { state }) })}`,
    ),
  strengthHistory: (c: string, tf: string) => get<StrengthRow[]>(`/strength/${c}/history?timeframe=${tf}`),
  relationshipHistory: (p: string, tf: string) =>
    get<RelationshipRow[]>(`/relationships/${p}/history?timeframe=${tf}`),
  quality: () => get<QualityRow[]>('/data-quality'),
  health: () => get<{ status: string }>('/health'),
};

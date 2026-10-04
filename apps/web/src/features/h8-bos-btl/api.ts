import type { H8BosBtlDetail, H8BosBtlPayload } from './types';

const BASE = import.meta.env.VITE_API_BASE ?? '';
const root = `${BASE}/api/market-intelligence/h8-bos-btl`;

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

export const h8BosBtlApi = {
  summary: () => get<H8BosBtlPayload>(''),
  latest: (symbol: string) => get<H8BosBtlDetail>(`/latest?${new URLSearchParams({ symbol })}`),
};

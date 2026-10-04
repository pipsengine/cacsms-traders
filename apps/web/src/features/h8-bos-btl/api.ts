import type { H8BosBtlDetail, H8BosBtlPayload } from './types';
import { apiFetch } from '../../lib/api';

const root = '/market-intelligence/h8-bos-btl';

async function get<T>(path: string): Promise<T> {
  const r = await apiFetch(`${root}${path}`);
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

import { get, post } from '../../lib/api';
import type {
  ChannelChart,
  SymbolChart,
  HistoryResponse,
  OpportunitiesResponse,
  Overview,
  StageDetail,
  StageFilters,
  StageKey,
  Transition,
} from './types';

function qs(params: Record<string, string | number | null | undefined>) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== null && v !== undefined && v !== '') q.set(k, String(v));
  const s = q.toString();
  return s ? `?${s}` : '';
}

export const autonomousApi = {
  overview: () => get<Overview>('/autonomous/overview'),
  stage: (key: StageKey, f: StageFilters) =>
    get<StageDetail>(`/autonomous/stages/${key}${qs({ symbol: f.symbol, timeframe: f.timeframe, provider: f.provider })}`),
  opportunities: (status: 'ACTIVE' | 'CLOSED' | 'ALL' = 'ALL', limit = 300) =>
    get<OpportunitiesResponse>(`/autonomous/opportunities${qs({ status, limit })}`),
  history: (id: string) => get<HistoryResponse>(`/autonomous/opportunities/${encodeURIComponent(id)}/history`),
  transitions: (entityType: string, limit = 150) =>
    get<{ rows: Transition[] }>(`/autonomous/transitions${qs({ entity_type: entityType, limit })}`),
  channelChart: (id: string, limit = 160) => get<ChannelChart>(`/autonomous/channels/${encodeURIComponent(id)}/chart${qs({ limit })}`),
  /** Candles and display geometry for one timeframe, including M1–W1. */
  symbolChart: (symbol: string, timeframe: string, limit = 140) =>
    get<SymbolChart>(`/autonomous/chart${qs({ symbol, timeframe, limit })}`),
  /** Lets a serverless deployment advance the engine while the page is open; the backend throttles and decides. */
  catchUp: () => post<{ ran: boolean; reason?: string; error?: string }>('/autonomous/jobs/catch-up', {}),
};

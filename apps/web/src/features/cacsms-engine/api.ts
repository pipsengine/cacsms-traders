import { api } from '../../lib/api';
import type { CampaignDetail, EngineResponse } from './types';

export const engineApi = {
  overview: (signal?: AbortSignal) => api<EngineResponse>('/cacsms-engine/overview', { signal }),
  detail: (id: string, signal?: AbortSignal) =>
    api<CampaignDetail>(`/cacsms-engine/campaigns/${encodeURIComponent(id)}`, { signal }),
  retryExecution: () =>
    api<{ cleared: Record<string, number>; advance: Record<string, number> }>('/cacsms-engine/retry-execution', {
      method: 'POST',
    }),
};

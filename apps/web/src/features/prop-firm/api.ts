import { get, post } from '../../lib/api';
import type { PropOverview, PropRules } from './types';

export const propApi = {
  overview: () => get<PropOverview>('/prop-firm/overview'),
  createFirm: (name: string, rules: PropRules) => post<{ id: string; rule_version_id: string }>('/prop-firm/firms', { name, rules }),
  versionRules: (firmId: string, rules: PropRules) => post(`/prop-firm/firms/${firmId}/rules`, { rules }),
  createAccount: (body: Record<string, unknown>) => post('/prop-firm/accounts', body),
  transition: (id: string, lifecycle: string, firmConfirmed = false) =>
    post(`/prop-firm/accounts/${id}/transition`, { lifecycle, firm_confirmed: firmConfirmed }),
  snapshot: (id: string, body: Record<string, number>) => post(`/prop-firm/accounts/${id}/snapshots`, body),
  performance: (id: string) => get<{
    snapshots: Array<{ recorded_at: string; balance: number; equity: number; floating_pnl: number }>;
    deals: Array<{ symbol: string; direction: string; volume: number; profit: number; commission: number; strategy: string | null; closed_at: string }>;
    win_rate: number | null;
    profit_factor: number | null;
    realized_pnl: number | null;
  }>(`/prop-firm/accounts/${id}/performance`),
  violations: () => get<{
    violations: Array<{ decision: string; protection: string; reasons: string[]; created_at: string; display_name: string; external_id: string }>;
    events: Array<{ action: string; actor: string; detail: Record<string, unknown>; created_at: string; account_id: string | null }>;
  }>('/prop-firm/violations'),
};

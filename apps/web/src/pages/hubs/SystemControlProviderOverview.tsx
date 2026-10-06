import { useEffect, useState } from 'react';
import { Card, Status } from '../../components/Ui';
import { get, put } from '../../lib/api';

type Mode = 'AUTO' | 'MT5_PREFERRED' | 'CTRADER_PREFERRED';
type ProviderHealth = {
  configured: boolean; authorized: boolean; connected: boolean; healthy: boolean;
  market_data_available: boolean; execution_available: boolean;
  last_heartbeat: string | null; last_market_data: string | null; last_error: string | null;
  environment: string; account_id: string | null;
};
type Overview = {
  active_provider: string | null; execution_provider: string | null; execution_account: string | null;
  selection_mode: Mode; providers?: Record<string, ProviderHealth>;
};
const name = (provider: string | null) => provider === 'mt5' ? 'MT5' : provider === 'ctrader' ? 'cTrader Direct' : 'Unavailable';

export function SystemControlProviderOverview({ tenantId, isPlatformAdmin, onChanged }: { tenantId: string; isPlatformAdmin: boolean; onChanged: () => void }) {
  const [state, setState] = useState<Overview | null>(null);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [accounts, setAccounts] = useState<{ account_id: string; broker: string | null; environment: string }[]>([]);
  useEffect(() => {
    if (!isPlatformAdmin) return;
    let active = true;
    const refresh = async () => {
      try {
        const [value, available] = await Promise.all([get<Overview>('/providers'), get<typeof accounts>(`/providers/accounts?tenant_id=${encodeURIComponent(tenantId)}`)]);
        if (active) { setState(value); setAccounts(available); setError(''); }
      } catch (err) { if (active) setError(err instanceof Error ? err.message : 'Provider health request failed'); }
    };
    void refresh();
    const timer = window.setInterval(refresh, 15000);
    return () => { active = false; window.clearInterval(timer); };
  }, [isPlatformAdmin, tenantId]);
  async function select(selection_mode: Mode, account_id?: string) {
    setSaving(true);
    try { setState(await put<Overview>('/providers/selection', { selection_mode, ...(account_id !== undefined ? { tenant_id: tenantId, account_id } : {}) })); setError(''); onChanged(); }
    catch (err) { setError(err instanceof Error ? err.message : 'Provider policy update failed'); }
    finally { setSaving(false); }
  }
  if (!isPlatformAdmin) return <Card><p>Platform administrator access is required to view global provider policy. Tenant connections are available in the MT5 and cTrader Direct tabs.</p></Card>;
  return <Card>
    <h2>Market &amp; Trading Connections</h2>
    <p>Operating Mode: <strong>ANALYSIS ONLY</strong></p>
    {error && <p role="alert">{error}</p>}
    {!state && !error && <p role="status">Loading provider health…</p>}
    {state && <>
      <div className="health-row"><span>Active Market Data Provider</span><strong>{name(state.active_provider)}</strong></div>
      <div className="health-row"><span>Execution Provider</span><strong>{state.execution_provider ? `${name(state.execution_provider)} / ${state.execution_account || 'No account selected'}` : 'No execution account selected'}</strong></div>
      <label>Selection Mode <select value={state.selection_mode || 'AUTO'} disabled={saving} onChange={event => void select(event.target.value as Mode)}>
        <option value="AUTO">AUTO</option><option value="MT5_PREFERRED">MT5 Preferred</option><option value="CTRADER_PREFERRED">cTrader Preferred</option>
      </select></label>
      <div style={{ marginTop: 12 }}><label>cTrader market-data account <select disabled={saving || !accounts.length} value={state.providers?.ctrader?.account_id || ''} onChange={event => void select(state.selection_mode, event.target.value)}>
        <option value="">No account selected</option>
        {accounts.map(account => <option key={account.account_id} value={account.account_id}>{account.broker || 'cTrader'} · …{account.account_id.slice(-4)} · {account.environment}</option>)}
      </select></label></div>
      <p>Market-data selection follows the configured policy. Execution remains bound to its explicitly selected account.</p>
      {Object.entries(state.providers || {}).map(([provider, health]) => <section key={provider} style={{ marginTop: 20 }}>
        <h3>{name(provider)}</h3>
        {(['configured', 'authorized', 'connected', 'healthy', 'market_data_available', 'execution_available'] as const).map(field => <div className="health-row" key={field}>
          <span>{field.replaceAll('_', ' ')}</span><Status value={health[field] ? 'AVAILABLE' : 'UNAVAILABLE'} />
        </div>)}
        <div className="health-row"><span>Connected account</span><span>{health.account_id || 'None'}</span></div>
        <div className="health-row"><span>Environment</span><span>{health.environment}</span></div>
        <div className="health-row"><span>Last heartbeat</span><span>{health.last_heartbeat ? new Date(health.last_heartbeat).toLocaleString() : 'Not observed'}</span></div>
        <div className="health-row"><span>Last market data</span><span>{health.last_market_data ? new Date(health.last_market_data).toLocaleString() : 'Not observed'}</span></div>
        {health.last_error && <p role="status">{health.last_error}</p>}
      </section>)}
    </>}
  </Card>;
}

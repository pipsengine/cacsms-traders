import React from 'react';
import { Cable, RefreshCcw, Unplug } from 'lucide-react';
import { Card, Notice, Status } from '../../components/Ui';
import { get, post } from '../../lib/api';

type CTraderAccount = {
  account: string | null;
  broker: string | null;
  account_type: string | null;
  environment: 'demo';
  currency: string | null;
  authorization: string;
  last_sync_at: string | null;
};

type CTraderStatus = {
  configured: boolean;
  can_manage: boolean;
  configuration_error: string | null;
  provider: string;
  environment: string;
  connected: boolean;
  authorization_status: string;
  connection_status: string;
  provider_status: string;
  application_status: string;
  message: string | null;
  last_successful_connection_at: string | null;
  last_sync_at: string | null;
  last_error_code: string | null;
  accounts: CTraderAccount[];
};

function fmt(value?: string | null) {
  if (!value) return 'Not yet';
  const timestamp = new Date(value);
  return Number.isNaN(timestamp.getTime()) ? 'Not available' : timestamp.toLocaleString();
}

const CALLBACK_MESSAGES: Record<string, { success?: string; error?: string }> = {
  app_inactive: { error: 'cTrader provider authorization unavailable: pending provider activation.' },
  connected: { success: 'cTrader authorization and demo account discovery completed.' },
  denied: { error: 'cTrader authorization was declined.' },
  invalid_state: { error: 'The authorization state expired or was already used. Start a new connection.' },
  invalid_request: { error: 'The cTrader callback was incomplete. Start a new connection.' },
  not_configured: { error: 'cTrader server configuration is incomplete.' },
  exchange_failed: { error: 'cTrader authorization could not be exchanged. Try connecting again.' },
  discovery_failed: { error: 'Authorization was saved, but cTrader account discovery failed. Retry account sync.' },
  persistence_failed: { error: 'cTrader authorization could not be safely stored. Try connecting again.' },
};

export function SystemControlCTraderPanel({
  tenantId,
  onRefreshGlobal,
}: {
  tenantId: string;
  onRefreshGlobal: () => void;
}) {
  const [data, setData] = React.useState<CTraderStatus | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [acting, setActing] = React.useState(false);
  const [error, setError] = React.useState('');
  const [success, setSuccess] = React.useState('');
  const authorizationAvailable = data?.authorization_status === 'AUTHORIZED';
  const canManage = data?.can_manage ?? false;

  const load = React.useCallback(async () => {
    if (!tenantId) return;
    setLoading(true);
    try {
      const status = await get<CTraderStatus>(`/connections/ctrader/status?tenant_id=${encodeURIComponent(tenantId)}`);
      setData(status);
      setError('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load cTrader connection status.');
    } finally {
      setLoading(false);
    }
  }, [tenantId]);

  React.useEffect(() => {
    void load();
  }, [load]);

  React.useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const result = params.get('ctrader');
    if (!result) return;
    const message = CALLBACK_MESSAGES[result];
    if (message?.success) setSuccess(message.success);
    if (message?.error) setError(message.error);
    params.delete('ctrader');
    const query = params.toString();
    window.history.replaceState(null, '', `${window.location.pathname}${query ? `?${query}` : ''}${window.location.hash}`);
    void load();
  }, [load]);

  async function connect() {
    if (!tenantId) return;
    setActing(true);
    setError('');
    setSuccess('');
    try {
      const result = await post<{ authorize_url: string }>('/connections/ctrader/authorize', { tenant_id: tenantId });
      window.location.assign(result.authorize_url);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not start cTrader authorization.');
      setActing(false);
    }
  }

  async function syncAccounts() {
    if (!tenantId) return;
    setActing(true);
    setError('');
    setSuccess('');
    try {
      await post('/connections/ctrader/accounts/sync', { tenant_id: tenantId });
      setSuccess('Demo account details synchronized.');
      await load();
      onRefreshGlobal();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'cTrader account discovery failed.');
    } finally {
      setActing(false);
    }
  }

  async function disconnect() {
    if (!tenantId || !window.confirm('Disconnect and revoke the locally stored cTrader authorization?')) return;
    setActing(true);
    setError('');
    setSuccess('');
    try {
      await post('/connections/ctrader/disconnect', { tenant_id: tenantId });
      setSuccess('cTrader authorization disconnected.');
      await load();
      onRefreshGlobal();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not disconnect cTrader.');
    } finally {
      setActing(false);
    }
  }

  return (
    <Card>
      <div className="card-title">
        <div>
          <h2>cTrader Direct</h2>
          <p>Read-only cTrader Open API connection.</p>
        </div>
        <Status value={data?.connection_status ?? 'DISCONNECTED'} />
      </div>
      {error && <Notice title="cTrader connection" text={error} tone="warning" />}
      {success && <Notice title="cTrader connection" text={success} />}
      {data?.provider_status === 'APP_INACTIVE' && (
        <Notice title="Pending provider activation" text={data.message || 'cTrader provider authorization unavailable.'} tone="warning" />
      )}
      <div className="detail-list">
        <div><span>Provider</span><b>cTrader</b></div>
        <div><span>Environment</span><b>Demo</b></div>
        <div><span>Provider status</span><b>{data?.provider_status?.replaceAll('_', ' ') ?? 'Unknown'}</b></div>
        <div><span>Connection health</span><b>{loading ? 'Checking…' : data?.connection_status?.replaceAll('_', ' ') ?? 'Unknown'}</b></div>
        <div><span>Authorization</span><b>{data?.authorization_status?.replaceAll('_', ' ') ?? 'Unknown'}</b></div>
        <div><span>Last successful connection</span><b>{fmt(data?.last_successful_connection_at)}</b></div>
        <div><span>Last synchronization</span><b>{fmt(data?.last_sync_at)}</b></div>
      </div>
      {data?.configuration_error && (
        <p className="muted">Server configuration issue: {data.configuration_error.replaceAll('_', ' ')}.</p>
      )}
      {data?.provider_status === 'APP_INACTIVE' && <p className="muted">After cTrader activates the application, select Connect cTrader to start a new authorization. No automatic authorization retries are performed.</p>}
      {data?.accounts.map((account) => (
        <div className="gateway-item" key={`${account.account}-${account.broker}`}>
          <Cable />
          <div>
            <b>{account.broker || 'Broker'} · {account.environment.toUpperCase()}</b>
            <p>Account {account.account || 'Hidden'} · {account.account_type || 'Account type unavailable'} · {account.currency || 'Currency unavailable'}</p>
            <p>Authorization: {account.authorization.replaceAll('_', ' ')} · Last sync: {fmt(account.last_sync_at)}</p>
          </div>
        </div>
      ))}
      {data?.last_error_code && <p className="muted">Last provider result: {data.last_error_code.replaceAll('_', ' ')}.</p>}
      {authorizationAvailable ? (
        <div className="sc-subtabs">
          <button type="button" className="sc-btnSecondary sc-btnSmall" disabled={!canManage || acting} onClick={() => void syncAccounts()}>
            <RefreshCcw /> Sync accounts
          </button>
          <button type="button" className="sc-btnSecondary sc-btnSmall" disabled={!canManage || acting} onClick={() => void disconnect()}>
            <Unplug /> Disconnect
          </button>
        </div>
      ) : (
        <button type="button" className="sc-btnPrimary" disabled={!canManage || acting || loading || !data?.configured} onClick={() => void connect()}>
          <Cable /> {acting ? 'Starting…' : 'Connect cTrader'}
        </button>
      )}
      <p className="muted">Account discovery only. Trading execution and autonomous trading are disabled.</p>
    </Card>
  );
}

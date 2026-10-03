import React from 'react';
import {
  Database,
  Monitor,
  Pencil,
  Play,
  RefreshCcw,
  RotateCcw,
  Settings,
  Square,
  X,
  Zap,
  Info,
} from 'lucide-react';
import { get, patch, post } from '../../lib/api';
import type { ConnectionsPayload, TradingAccount } from '../../types';

function fmtTs(v?: string | null) {
  if (!v) return '—';
  try {
    return new Date(v).toLocaleString();
  } catch {
    return v;
  }
}

type GatewayActionResult = {
  ok: boolean;
  error?: string;
  code?: string;
  settings?: ConnectionsPayload['settings'];
  gateway?: ConnectionsPayload['gateway'];
};

export function SystemControlMT5Panel({
  tenantId,
  onRefreshGlobal,
}: {
  tenantId: string;
  onRefreshGlobal: () => void;
}) {
  const [data, setData] = React.useState<ConnectionsPayload | null>(null);
  const [accounts, setAccounts] = React.useState<TradingAccount[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [noticeOpen, setNoticeOpen] = React.useState(true);
  const [configureOpen, setConfigureOpen] = React.useState(false);
  const [editOpen, setEditOpen] = React.useState(false);
  const [addOpen, setAddOpen] = React.useState(false);
  const [terminalPath, setTerminalPath] = React.useState('');
  const [loginType, setLoginType] = React.useState('');
  const [autoReconnect, setAutoReconnect] = React.useState(true);
  const [heartbeatSec, setHeartbeatSec] = React.useState(30);
  const [linkAccountId, setLinkAccountId] = React.useState('');
  const [error, setError] = React.useState('');
  const [success, setSuccess] = React.useState('');

  const load = React.useCallback(() => {
    if (!tenantId) return;
    setLoading(true);
    Promise.all([
      get<ConnectionsPayload>(`/tenants/${tenantId}/connections`),
      get<TradingAccount[]>(`/tenants/${tenantId}/accounts`),
    ])
      .then(([conn, acc]) => {
        setData(conn);
        setAccounts(acc);
        const s = conn.settings;
        if (s) {
          setTerminalPath(s.terminal_path ?? '');
          setLoginType(s.login_type ?? '');
          setAutoReconnect(s.auto_reconnect ?? true);
          setHeartbeatSec(s.heartbeat_interval_seconds ?? 30);
        }
      })
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [tenantId]);

  React.useEffect(load, [load]);

  const gw = data?.gateway;
  const connected = gw?.status === 'CONNECTED';
  const rows = data?.connections ?? [];

  async function action(path: string) {
    setError('');
    setLoading(true);
    try {
      const res = await post<GatewayActionResult>(`/tenants/${tenantId}${path}`, {});
      applyGatewayResult(res);
      if (res.ok === false && res.error) setError(res.error);
      await load();
      onRefreshGlobal();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      await load();
    } finally {
      setLoading(false);
    }
  }

  function applyGatewayResult(res: GatewayActionResult) {
    if (res.settings || res.gateway) {
      setData((prev) =>
        prev
          ? {
              ...prev,
              settings: res.settings ?? prev.settings,
              gateway: res.gateway ?? prev.gateway,
            }
          : prev,
      );
      if (res.settings?.terminal_path) setTerminalPath(res.settings.terminal_path);
    }
  }

  async function saveSettings(): Promise<boolean> {
    setError('');
    setLoading(true);
    try {
      const res = await patch<{ settings: ConnectionsPayload['settings']; gateway: ConnectionsPayload['gateway'] }>(
        `/tenants/${tenantId}/connections/settings`,
        {
          terminal_path: terminalPath,
          login_type: loginType,
          auto_reconnect: autoReconnect,
          heartbeat_interval_seconds: heartbeatSec,
        },
      );
      setData((prev) =>
        prev ? { ...prev, settings: res.settings, gateway: res.gateway, diagnostics: prev.diagnostics } : prev,
      );
      setEditOpen(false);
      setConfigureOpen(false);
      setError('');
      setSuccess('Connection settings saved to the database.');
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return false;
    } finally {
      setLoading(false);
    }
  }

  async function connect() {
    setError('');
    setSuccess('');
    setLoading(true);
    try {
      const res = await post<GatewayActionResult>(`/tenants/${tenantId}/connections/gateway/connect`, {
        terminal_path: terminalPath || undefined,
      });
      applyGatewayResult(res);
      if (res.ok) {
        setConfigureOpen(false);
        onRefreshGlobal();
      } else {
        setError(res.error ?? 'Connect failed');
      }
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      await load();
    } finally {
      setLoading(false);
    }
  }

  async function saveAndConnect() {
    const saved = await saveSettings();
    if (saved) await connect();
  }

  async function addConnection() {
    if (!linkAccountId) return;
    setError('');
    setLoading(true);
    try {
      await post(`/tenants/${tenantId}/connections`, {
        trading_account_id: linkAccountId,
        adapter_type: 'LOCAL_MT5',
        terminal_path: terminalPath || null,
        server_name: null,
      });
      setAddOpen(false);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      {noticeOpen && (
        <div className="sc-notice" role="status">
          <Info size={22} />
          <div className="sc-noticeBody">
            <b>Safe foundation state</b>
            <span>
              The local MT5 gateway contract is installed, but terminal binding and order submission are not enabled
              while operating mode is analysis-only.
            </span>
          </div>
          <button type="button" className="sc-noticeClose" aria-label="Dismiss" onClick={() => setNoticeOpen(false)}>
            <X size={18} />
          </button>
        </div>
      )}

      {success ? (
        <p className="sc-notice" style={{ borderColor: '#b7e6cf', background: '#f5fff9', color: '#067647' }}>
          {success}
        </p>
      ) : null}
      {data?.diagnostics?.python_package === 'missing' ? (
        <p className="sc-notice" style={{ borderColor: '#ffc9c9', background: '#fff5f5', color: '#c92a2a' }}>
          <b>API cannot load MetaTrader5.</b> {data.diagnostics.hint ?? 'Install MetaTrader5 and restart the API.'}
        </p>
      ) : null}
      {error ? <p className="muted" style={{ color: '#e03131' }}>{error}</p> : null}

      <div className="sc-grid">
        <section className="sc-card gateway">
          <div className="sc-cardTitle">
            <div className="sc-titleIcon">
              <Monitor />
            </div>
            <div>
              <h3>Local MT5 Gateway</h3>
              <p>Phase 1 adapter (Local Terminal)</p>
            </div>
            <span className={`sc-pill ${connected ? 'ok' : 'danger'}`}>
              <i className={`sc-dot ${connected ? 'green' : 'red'}`} />
              {connected ? 'Connected' : 'Disconnected'}
            </span>
          </div>
          <div className="sc-kv">
            <div>
              <span>Adapter</span>
              <b>{gw?.adapter ?? 'LOCAL_MT5'}</b>
            </div>
            <div>
              <span>Terminal</span>
              <b className={gw?.terminal_configured ? '' : 'sc-bad'}>
                {gw?.terminal_configured ? gw.terminal : 'Not configured'} {!gw?.terminal_configured ? 'ⓘ' : ''}
              </b>
            </div>
            <div>
              <span>Heartbeat</span>
              <b>{fmtTs(gw?.heartbeat_at)}</b>
            </div>
            <div>
              <span>Execution</span>
              <b className={gw?.execution_enabled ? 'sc-ok' : 'sc-bad'}>{gw?.execution ?? 'Disabled'}</b>
            </div>
            <div>
              <span>Last Connected</span>
              <b>{fmtTs(gw?.last_connected_at)}</b>
            </div>
            <div>
              <span>Last Error</span>
              <b>{gw?.last_error ?? '—'}</b>
            </div>
          </div>
          <button type="button" className="sc-btnPrimary sc-full" onClick={() => setConfigureOpen(true)} disabled={loading}>
            <Settings size={17} />
            Configure Connection
          </button>
        </section>

        <section className="sc-card registry">
          <div className="sc-cardTitle">
            <div className="sc-titleIcon">
              <Database />
            </div>
            <div>
              <h3>Connection Registry</h3>
              <p>{rows.length} record(s) for this tenant.</p>
            </div>
            <button type="button" className="sc-btnSecondary" onClick={load} disabled={loading}>
              <RefreshCcw size={17} />
              Refresh
            </button>
          </div>
          <p className="sc-muted">Link accounts via the registry; terminal handshake uses the local MT5 adapter.</p>
          <div className="sc-tableHead">
            <b>#</b>
            <b>Account Name</b>
            <b>Account No.</b>
            <b>Type</b>
            <b>Server</b>
            <b>Status</b>
            <b>Actions</b>
          </div>
          {rows.length ? (
            rows.map((c, i) => (
              <div className="sc-tableRow" key={c.id}>
                <span>{i + 1}</span>
                <span>{c.account_name}</span>
                <span>{c.account_number ?? '—'}</span>
                <span>{c.adapter_type}</span>
                <span>{c.server_name || c.account_server || '—'}</span>
                <span>{c.status}</span>
                <span>—</span>
              </div>
            ))
          ) : (
            <div className="sc-empty">
              <Database size={36} />
              <h4>No MT5 accounts linked yet</h4>
              <p>Configure a connection to get started.</p>
              <button type="button" className="sc-btnPrimary" onClick={() => setAddOpen(true)}>
                + Add MT5 Account
              </button>
            </div>
          )}
          {rows.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <button type="button" className="sc-btnPrimary sc-btnSmall" onClick={() => setAddOpen(true)}>
                + Add MT5 Account
              </button>
            </div>
          )}
        </section>

        <section className="sc-card sc-lower">
          <div className="sc-cardTitle">
            <div className="sc-titleIcon">
              <Settings />
            </div>
            <div>
              <h3>Connection Settings</h3>
              <p>Local MT5 terminal configuration and options.</p>
            </div>
            <button type="button" className="sc-btnSecondary" onClick={() => setEditOpen(true)}>
              <Pencil size={16} />
              Edit Settings
            </button>
          </div>
          <div className="sc-settingsGrid">
            <div>
              <span>Terminal Path</span>
              <b>{data?.settings?.terminal_path?.trim() ? data.settings.terminal_path : 'Not configured'}</b>
            </div>
            <div>
              <span>Auto Reconnect</span>
              <b className={data?.settings?.auto_reconnect ? 'sc-ok' : ''}>
                {data?.settings?.auto_reconnect ? 'Enabled' : 'Disabled'}
              </b>
            </div>
            <div>
              <span>Login Type</span>
              <b>{data?.settings?.login_type?.trim() ? data.settings.login_type : 'Not configured'}</b>
            </div>
            <div>
              <span>Heartbeat Interval</span>
              <b>{data?.settings?.heartbeat_interval_seconds ?? 30} seconds</b>
            </div>
          </div>
        </section>

        <section className="sc-card sc-lower">
          <div className="sc-cardTitle">
            <div className="sc-titleIcon">
              <Zap />
            </div>
            <div>
              <h3>Connection Actions</h3>
              <p>Manage the MT5 connection and terminal state.</p>
            </div>
          </div>
          <div className="sc-actionGrid">
            <button type="button" className="sc-action connect" disabled={loading} onClick={() => void connect()}>
              <Play />
              <span>
                <b>Connect</b>
                <small>Start MT5 connection</small>
              </span>
            </button>
            <button
              type="button"
              className="sc-action disconnect"
              disabled={loading}
              onClick={() => void action('/connections/gateway/disconnect')}
            >
              <Square />
              <span>
                <b>Disconnect</b>
                <small>Stop MT5 connection</small>
              </span>
            </button>
            <button
              type="button"
              className="sc-action"
              disabled={loading}
              onClick={() => void action('/connections/gateway/restart')}
            >
              <RotateCcw />
              <span>
                <b>Restart</b>
                <small>Restart terminal</small>
              </span>
            </button>
          </div>
        </section>
      </div>

      {configureOpen && (
        <div className="sc-modalBackdrop" role="dialog" aria-modal="true">
          <div className="sc-modal">
            <h3>Configure local MT5</h3>
            <label>
              Terminal path (terminal64.exe)
              <input value={terminalPath} onChange={(e) => setTerminalPath(e.target.value)} placeholder="C:\Program Files\MetaTrader 5\terminal64.exe" />
            </label>
            <div className="sc-modalActions">
              <button type="button" className="sc-btnSecondary" onClick={() => setConfigureOpen(false)}>
                Cancel
              </button>
              <button type="button" className="sc-btnSecondary" onClick={() => void saveSettings()} disabled={loading}>
                Save only
              </button>
              <button type="button" className="sc-btnPrimary" onClick={() => void saveAndConnect()} disabled={loading}>
                Save & Connect
              </button>
            </div>
          </div>
        </div>
      )}

      {editOpen && (
        <div className="sc-modalBackdrop" role="dialog" aria-modal="true">
          <div className="sc-modal">
            <h3>Edit connection settings</h3>
            <label>
              Terminal path
              <input value={terminalPath} onChange={(e) => setTerminalPath(e.target.value)} />
            </label>
            <label>
              Login type
              <input value={loginType} onChange={(e) => setLoginType(e.target.value)} placeholder="e.g. INVESTOR" />
            </label>
            <label>
              Heartbeat interval (seconds)
              <input type="number" min={5} max={300} value={heartbeatSec} onChange={(e) => setHeartbeatSec(Number(e.target.value))} />
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <input type="checkbox" checked={autoReconnect} onChange={(e) => setAutoReconnect(e.target.checked)} />
              Auto reconnect
            </label>
            <div className="sc-modalActions">
              <button type="button" className="sc-btnSecondary" onClick={() => setEditOpen(false)}>
                Cancel
              </button>
              <button type="button" className="sc-btnPrimary" onClick={() => void saveSettings()} disabled={loading}>
                Save
              </button>
            </div>
          </div>
        </div>
      )}

      {addOpen && (
        <div className="sc-modalBackdrop" role="dialog" aria-modal="true">
          <div className="sc-modal">
            <h3>Link MT5 account</h3>
            <label>
              Trading account
              <select value={linkAccountId} onChange={(e) => setLinkAccountId(e.target.value)}>
                <option value="">Select account…</option>
                {accounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.account_name} ({a.environment})
                  </option>
                ))}
              </select>
            </label>
            <div className="sc-modalActions">
              <button type="button" className="sc-btnSecondary" onClick={() => setAddOpen(false)}>
                Cancel
              </button>
              <button type="button" className="sc-btnPrimary" onClick={() => void addConnection()} disabled={loading || !linkAccountId}>
                Link account
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

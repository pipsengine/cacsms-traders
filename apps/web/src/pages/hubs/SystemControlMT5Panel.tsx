import React from 'react';
import { createPortal } from 'react-dom';
import {
  Database,
  Monitor,
  Pencil,
  Play,
  RefreshCcw,
  RotateCcw,
  Settings,
  Square,
  Zap,
  Info,
} from 'lucide-react';
import { del, get, patch, post } from '../../lib/api';
import { openLocalMT5 } from '../../lib/mt5Local';
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
  terminal_launch?: { launched: boolean; code: string };
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
  const [pageLoading, setPageLoading] = React.useState(false);
  const [acting, setActing] = React.useState(false);
  const [editOpen, setEditOpen] = React.useState(false);
  const [addOpen, setAddOpen] = React.useState(false);
  const [terminalPath, setTerminalPath] = React.useState('');
  const [loginType, setLoginType] = React.useState('');
  const [autoReconnect, setAutoReconnect] = React.useState(true);
  const [heartbeatSec, setHeartbeatSec] = React.useState(30);
  const [linkAccountId, setLinkAccountId] = React.useState('');
  const [error, setError] = React.useState('');
  const [success, setSuccess] = React.useState('');
  const hostedGateway = data?.diagnostics?.terminal_launch_mode === 'WINDOWS_GATEWAY_REQUIRED';

  const closeModals = () => {
    setEditOpen(false);
    setAddOpen(false);
  };

  function openTerminalSettings() {
    const running = data?.diagnostics?.terminal_running_processes?.[0]?.trim();
    const saved = data?.settings?.terminal_path?.trim();
    if (!terminalPath.trim()) {
      setTerminalPath(running || saved || data?.diagnostics?.terminal_auto_detect_path || '');
    }
    setEditOpen(true);
  }

  const load = React.useCallback(() => {
    if (!tenantId) return Promise.resolve();
    setPageLoading(true);
    return get<ConnectionsPayload>(`/tenants/${tenantId}/connections`)
      .then((conn) => {
        setData(conn);
        const s = conn.settings;
        if (s) {
          setTerminalPath(s.terminal_path ?? conn.diagnostics?.terminal_auto_detect_path ?? '');
          setLoginType(s.login_type ?? '');
          setAutoReconnect(s.auto_reconnect ?? true);
          setHeartbeatSec(s.heartbeat_interval_seconds ?? 30);
        }
        return get<TradingAccount[]>(`/tenants/${tenantId}/accounts`);
      })
      .then((acc) => {
        setAccounts(acc);
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : 'Failed to load MT5 connections.');
      })
      .finally(() => setPageLoading(false));
  }, [tenantId]);

  React.useEffect(() => {
    void load();
  }, [load]);

  const gw = data?.gateway;
  const sessionSaved = data?.settings?.session_status === 'CONNECTED';
  const connected = gw?.status === 'CONNECTED' || sessionSaved;
  const terminalSaved = Boolean(data?.settings?.terminal_path?.trim());
  const terminalDisplay =
    data?.settings?.terminal_path?.trim() ||
    (gw as { terminal_path_detected?: string } | undefined)?.terminal_path_detected?.trim() ||
    (connected && gw?.terminal && gw.terminal !== 'Not configured' ? gw.terminal : '') ||
    data?.diagnostics?.terminal_auto_detect_path?.trim() ||
    '';
  const rows = data?.connections ?? [];
  const hasPlaceholderRows = rows.some((r) => /verify demo|demo account|test account/i.test(r.account_name || ''));
  const terminalAccount = data?.diagnostics?.terminal_account;
  const terminalAccountLive = terminalAccount?.available ? terminalAccount : null;
  const loginTypeDisplay =
    terminalAccountLive?.trade_mode ||
    data?.settings?.login_type?.trim() ||
    (connected ? '—' : 'Not configured');

  React.useEffect(() => {
    const login = terminalAccountLive?.login?.trim();
    if (!addOpen || !login) return;
    const match = accounts.find((a) => (a.account_number || '').trim() === login);
    if (match) setLinkAccountId(match.id);
  }, [addOpen, terminalAccountLive?.login, accounts]);

  async function action(path: string, label: string) {
    if (!tenantId) {
      setError('Select a tenant in the header before managing MT5.');
      return;
    }
    closeModals();
    setError('');
    setSuccess(`${label}…`);
    setActing(true);
    try {
      const res = await post<GatewayActionResult>(`/tenants/${tenantId}${path}`, {});
      applyGatewayResult(res);
      if (res.ok === false && res.error) {
        setError(res.error);
        setSuccess('');
      } else {
        setSuccess(`${label} completed.`);
        setError('');
      }
      await load();
      onRefreshGlobal();
    } catch (e) {
      setSuccess('');
      setError(e instanceof Error ? e.message : String(e));
      await load();
    } finally {
      setActing(false);
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

  async function saveSettings(opts?: { keepModalOpen?: boolean }): Promise<boolean> {
    setError('');
    setActing(true);
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
      if (!opts?.keepModalOpen) setEditOpen(false);
      setError('');
      setSuccess('Connection settings saved to the database.');
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return false;
    } finally {
      setActing(false);
    }
  }

  async function connect() {
    if (!tenantId) {
      setError('Select a tenant in the header before managing MT5.');
      return;
    }
    closeModals();
    setError('');
    setSuccess('Connecting…');
    setActing(true);
    try {
      const diagnostic = data?.diagnostics;
      if (diagnostic?.terminal_launch_mode === 'WINDOWS_GATEWAY_REQUIRED') {
        setSuccess(await openLocalMT5());
        return;
      }
      const res = await post<GatewayActionResult>(`/tenants/${tenantId}/connections/gateway/connect`, {
        terminal_path: terminalPath?.trim() || undefined,
      });
      applyGatewayResult(res);
      if (res.ok) {
        setSuccess('MT5 gateway connected for this tenant.');
        onRefreshGlobal();
      } else {
        setSuccess(res.terminal_launch?.launched ? 'MT5 was opened. The gateway still needs the connection requirements shown below.' : '');
        setError(res.error ?? 'Connect failed');
      }
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      await load();
    } finally {
      setActing(false);
    }
  }

  async function saveAndConnect() {
    setSuccess('Saving settings…');
    const saved = await saveSettings({ keepModalOpen: true });
    if (!saved) return;
    setEditOpen(false);
    await connect();
  }

  async function addConnection() {
    if (!tenantId || !linkAccountId) return;
    setError('');
    setSuccess('Linking account…');
    setActing(true);
    try {
      await post(`/tenants/${tenantId}/connections`, {
        trading_account_id: linkAccountId,
        adapter_type: 'LOCAL_MT5',
        terminal_path: terminalPath || null,
        server_name: terminalAccountLive?.server || null,
      });
      setAddOpen(false);
      setSuccess('Trading account linked in the registry.');
      await load();
      onRefreshGlobal();
    } catch (e) {
      setSuccess('');
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setActing(false);
    }
  }

  async function syncRegistry() {
    if (!tenantId) return;
    setError('');
    setSuccess('Syncing registry from MT5…');
    setActing(true);
    try {
      const res = await post<{ connections: ConnectionsPayload['connections'] }>(
        `/tenants/${tenantId}/connections/sync-registry`,
        {},
      );
      setData((prev) => (prev ? { ...prev, connections: res.connections } : prev));
      setSuccess('Registry updated from the MT5 terminal.');
      await load();
    } catch (e) {
      setSuccess('');
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setActing(false);
    }
  }

  async function cleanupPlaceholders() {
    if (!tenantId) return;
    setError('');
    setSuccess('Removing placeholder accounts…');
    setActing(true);
    try {
      const res = await post<{ removed: number; connections: ConnectionsPayload['connections'] }>(
        `/tenants/${tenantId}/connections/cleanup-placeholders`,
        {},
      );
      setData((prev) => (prev ? { ...prev, connections: res.connections } : prev));
      setSuccess(
        res.removed > 0
          ? `Removed ${res.removed} placeholder account(s). Use Import from MT5 terminal for IC Markets.`
          : 'No placeholder accounts found.',
      );
      await load();
      onRefreshGlobal();
    } catch (e) {
      setSuccess('');
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setActing(false);
    }
  }

  async function removeRegistryRow(connectionId: string, accountName: string) {
    if (!tenantId) return;
    if (!window.confirm(`Remove "${accountName}" from the registry and delete the trading account record?`)) return;
    setActing(true);
    setError('');
    try {
      await del(`/tenants/${tenantId}/connections/${connectionId}?delete_account=true`);
      setSuccess('Registry entry removed.');
      await load();
      onRefreshGlobal();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setActing(false);
    }
  }

  async function autoLinkFromTerminal() {
    if (!tenantId) {
      setError('Select a tenant in the header before managing MT5.');
      return;
    }
    setError('');
    setSuccess('Reading MT5 terminal account…');
    setActing(true);
    try {
      await post(`/tenants/${tenantId}/connections/auto-link-terminal`, {});
      setAddOpen(false);
      setSuccess('Terminal account detected and linked.');
      await load();
      onRefreshGlobal();
    } catch (e) {
      setSuccess('');
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setActing(false);
    }
  }

  const statusBanner = acting ? (
    <div className="sc-actionStatus busy" role="status">
      Working…
    </div>
  ) : error ? (
    <div className="sc-actionStatus err" role="alert">
      {error}
    </div>
  ) : success ? (
    <div className="sc-actionStatus ok" role="status">
      {success}
    </div>
  ) : null;

  if (!tenantId) {
    return (
      <p className="sc-notice sc-notice-warn" role="status">
        Select a tenant in the header to manage MT5 connections.
      </p>
    );
  }

  return (
    <>
      {hostedGateway ? (
        <p className="sc-notice" role="status">
          <b>MT5 market data is not connected to the hosted platform.</b> The local launcher opens MT5 on this PC. An authenticated Windows market-data bridge is still required to send prices and account status to the platform.
        </p>
      ) : data?.diagnostics?.python_package === 'missing' ? (
        <p className="sc-notice" style={{ borderColor: '#ffc9c9', background: '#fff5f5', color: '#c92a2a' }}>
          <b>API cannot load MetaTrader5.</b> {data.diagnostics.hint ?? 'Install MetaTrader5 and restart the API.'}
        </p>
      ) : null}
      {statusBanner}


      {(data?.diagnostics?.terminal_running_processes?.length ?? 0) > 0 ? (
        <p className="sc-notice sc-notice-ok" role="status">
          <Info size={18} />
          <span>
            Running MT5 (taskbar): <code>{data?.diagnostics?.terminal_running_processes?.[0]}</code>
            {data?.diagnostics?.terminal_running_processes?.[0]?.toLowerCase().includes('ic markets')
              ? ' — IC Markets terminal will be used for account detection.'
              : ''}
          </span>
        </p>
      ) : null}
      {data?.diagnostics?.terminal_auto_detect_path || terminalSaved ? (
        <p className="sc-notice sc-notice-ok" role="status">
          <Info size={18} />
          <span>
            Tenant terminal path
            {data?.diagnostics?.terminal_auto_detect_source
              ? ` (auto-detected: ${data.diagnostics.terminal_auto_detect_source})`
              : ''}
            : <code>{data?.settings?.terminal_path || data?.diagnostics?.terminal_auto_detect_path}</code>
          </span>
        </p>
      ) : null}

      <section className="sc-steps" aria-label="MT5 setup steps">
        <ol>
          <li>
            <b>Select tenant</b> — use the tenant switcher in the header (each tenant has its own MT5 settings).
          </li>
          <li>
            <b>Select MT5 Preferred or click Connect</b> to open or restore your configured broker terminal on this PC. Log in when MT5 opens.
          </li>
          {!hostedGateway && <li>
            <b>Connect in this UI</b> — IC Markets is detected from the running terminal; click <em>Connect</em>, then{' '}
            <em>Import from MT5 terminal</em>. Use <em>Edit Settings</em> only if auto-detect picks the wrong install.
          </li>}
          {!hostedGateway && <li>
            <b>Link trading account</b> — after <em>Connect</em>, use <em>Import from MT5 terminal</em> or link an existing
            Administration account.
          </li>}
        </ol>
      </section>

      <div className={`sc-grid sc-grid-compact${acting ? ' sc-actionBusy' : ''}`}>
        <section className="sc-card gateway">
          <div className="sc-cardTitle">
            <div className="sc-titleIcon">
              <Monitor />
            </div>
            <div>
              <h3>{hostedGateway ? 'MT5 Market-data Connection' : 'Local MT5 Gateway'}</h3>
              <p>{hostedGateway ? 'Connection status reported by the hosted API' : 'Phase 1 adapter (Local Terminal)'}</p>
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
              <b className={!terminalDisplay ? 'sc-bad' : terminalSaved ? 'sc-ok' : 'sc-warn'}>
                {terminalDisplay || 'Not configured'}
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
              <b>{hostedGateway ? 'Windows market-data bridge is not connected.' : gw?.last_error ?? '—'}</b>
            </div>
          </div>
          {!hostedGateway && <p className="sc-muted" style={{ margin: '8px 0 0', textAlign: 'center' }}>
            Terminal path is auto-detected from your taskbar MT5. Wrong install?{' '}
            <button type="button" className="sc-linkBtn" onClick={openTerminalSettings}>
              Edit terminal path
            </button>
          </p>}
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
            <button
              type="button"
              className="sc-btnSecondary"
              onClick={() => void syncRegistry()}
              disabled={acting || !tenantId}
              title="Read login and server from MetaTrader 5 into the registry"
            >
              <RefreshCcw size={17} />
              Sync from MT5
            </button>
            <button type="button" className="sc-btnSecondary" onClick={() => void load()} disabled={pageLoading}>
              Refresh
            </button>
          </div>
          <p className="sc-muted">
            Link accounts via the registry; data is stored in SQLite
            {data?.diagnostics?.database_path ? (
              <>
                {' '}
                (<code style={{ fontSize: 10 }}>{data.diagnostics.database_path}</code>)
              </>
            ) : null}
            .
          </p>
          <div className="sc-tableHead sc-tableHeadWide">
            <b>#</b>
            <b>Account Name</b>
            <b>Account No.</b>
            <b>Env</b>
            <b>Type</b>
            <b>Server</b>
            <b>Status</b>
            <b>Actions</b>
          </div>
          {hasPlaceholderRows ? (
            <div style={{ marginBottom: 10 }}>
              <button type="button" className="sc-btnSecondary sc-btnSmall" disabled={acting} onClick={() => void cleanupPlaceholders()}>
                Remove all placeholder accounts
              </button>
            </div>
          ) : null}
          {rows.length ? (
            rows.map((c, i) => (
              <div className="sc-tableRow sc-tableRowWide" key={c.id}>
                <span>{i + 1}</span>
                <span>{c.account_name}</span>
                <span>{(c.account_number || '').trim() || '—'}</span>
                <span>{c.environment || '—'}</span>
                <span>{c.adapter_type}</span>
                <span>{(c.server_name || c.account_server || '').trim() || '—'}</span>
                <span className={c.status === 'CONNECTED' ? 'sc-ok' : ''}>{c.status}</span>
                <span>
                  <button
                    type="button"
                    className="sc-btnSecondary sc-btnSmall"
                    disabled={acting}
                    onClick={() => void removeRegistryRow(c.id, c.account_name)}
                  >
                    Remove
                  </button>
                </span>
              </div>
            ))
          ) : (
            <div className="sc-empty">
              <Database size={36} />
              <h4>No MT5 accounts linked yet</h4>
              <p>
                {connected
                  ? 'Import the account logged into MetaTrader 5, or link a record you created under Administration.'
                  : 'Connect the gateway first, then import the account logged into MetaTrader 5.'}
              </p>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, justifyContent: 'center' }}>
                <button
                  type="button"
                  className="sc-btnPrimary"
                  disabled={acting || !connected || !tenantId}
                  onClick={() => void autoLinkFromTerminal()}
                >
                  Import from MT5 terminal
                </button>
                <button type="button" className="sc-btnSecondary" onClick={() => setAddOpen(true)}>
                  Link existing account
                </button>
              </div>
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
            <button type="button" className="sc-btnSecondary" onClick={openTerminalSettings}>
              <Pencil size={16} />
              Edit Settings
            </button>
          </div>
          <div className="sc-settingsGrid">
            <div>
              <span>Terminal Path</span>
              <b>{terminalDisplay || 'Not configured'}</b>
            </div>
            <div>
              <span>Auto Reconnect</span>
              <b className={data?.settings?.auto_reconnect ? 'sc-ok' : ''}>
                {data?.settings?.auto_reconnect ? 'Enabled' : 'Disabled'}
              </b>
            </div>
            <div>
              <span>Terminal account</span>
              <b className={terminalAccountLive ? 'sc-ok' : connected ? 'sc-warn' : ''}>
                {terminalAccountLive
                  ? `${terminalAccountLive.login} @ ${terminalAccountLive.server || '—'}`
                  : connected
                    ? 'Connected — open MT5 and log in, then Refresh'
                    : 'Connect gateway to detect'}
              </b>
            </div>
            <div>
              <span>Account mode</span>
              <b>{loginTypeDisplay}</b>
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
            <button
              type="button"
              className="sc-action connect"
              disabled={acting || !tenantId}
              onClick={() => void connect()}
            >
              <Play />
              <span>
                <b>Connect</b>
                <small>Open terminal and connect</small>
              </span>
            </button>
            <button
              type="button"
              className="sc-action disconnect"
              disabled={acting || !tenantId}
              onClick={() => void action('/connections/gateway/disconnect', 'Disconnect')}
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
              disabled={acting || !tenantId}
              onClick={() => void action('/connections/gateway/restart', 'Restart')}
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

      {editOpen &&
        createPortal(
          <div className="sc-modalBackdrop" role="dialog" aria-modal="true">
            <div className="sc-modal">
              <h3>Connection settings</h3>
              {data?.diagnostics?.terminal_running_processes?.[0] ? (
                <p className="sc-modalDetect">
                  Running terminal: <code>{data.diagnostics.terminal_running_processes[0]}</code>
                </p>
              ) : null}
              <label>
                Terminal path (terminal64.exe)
                <input
                  value={terminalPath}
                  onChange={(e) => setTerminalPath(e.target.value)}
                  placeholder="C:\Program Files\MetaTrader 5 IC Markets Global\terminal64.exe"
                />
              </label>
              <label>
                Login type (optional label)
                <input value={loginType} onChange={(e) => setLoginType(e.target.value)} placeholder="Main or Investor" />
              </label>
              <p className="muted section-hint" style={{ margin: '-4px 0 8px' }}>
                This is stored for your records only. Log into the IC Markets terminal itself (Main password for trading;
                Investor is read-only). The API attaches to that running terminal.
              </p>
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
                <button type="button" className="sc-btnSecondary" onClick={() => void saveSettings()} disabled={acting}>
                  Save
                </button>
                <button type="button" className="sc-btnPrimary" onClick={() => void saveAndConnect()} disabled={acting}>
                  Save & Connect
                </button>
              </div>
            </div>
          </div>,
          document.body,
        )}

      {addOpen &&
        createPortal(
          <div className="sc-modalBackdrop" role="dialog" aria-modal="true">
            <div className="sc-modal">
              <h3>Link MT5 account</h3>
            {terminalAccountLive ? (
              <p className="sc-modalDetect">
                MT5 terminal: <b>{terminalAccountLive.login}</b> — {terminalAccountLive.name || '—'} (
                {terminalAccountLive.server}, {terminalAccountLive.trade_mode})
              </p>
            ) : (
              <p className="sc-modalDetect muted">
                {data?.diagnostics?.terminal_account_hint ??
                  'Connect the gateway while MetaTrader 5 is logged in to detect the terminal account.'}
              </p>
            )}
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
              {connected ? (
                <button
                  type="button"
                  className="sc-btnSecondary"
                  onClick={() => void autoLinkFromTerminal()}
                  disabled={acting}
                >
                  Import from terminal
                </button>
              ) : null}
              <button type="button" className="sc-btnPrimary" onClick={() => void addConnection()} disabled={acting || !linkAccountId}>
                Link account
              </button>
            </div>
          </div>
        </div>,
          document.body,
        )}
    </>
  );
}



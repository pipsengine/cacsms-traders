import React from 'react';
import { Plus, WalletCards } from 'lucide-react';
import { Card, Empty, PageHeader, Status } from '../components/Ui';
import { get, post } from '../lib/api';
import { accountMoney, executionLabel } from '../lib/money';
import type { TradingAccount } from '../types';

export function Accounts({
  tenantId,
  onChanged,
  embedded,
  environment = 'ALL',
}: {
  tenantId: string;
  onChanged: () => void;
  embedded?: boolean;
  environment?: 'ALL' | 'DEMO' | 'LIVE' | 'PROP_FIRM';
}) {
  const [rows, setRows] = React.useState<TradingAccount[]>([]);

  React.useEffect(() => {
    if (!tenantId) return;
    get<TradingAccount[]>(`/tenants/${tenantId}/accounts`).then(setRows).catch(() => setRows([]));
  }, [tenantId]);

  const visible = environment === 'ALL' ? rows : rows.filter((a) => a.environment === environment);

  async function setLive(account: TradingAccount, enabled: boolean) {
    if (enabled && !window.confirm(`Enable live order submission on ${account.account_name}? Orders stay sized from the broker account.`)) return;
    await post(`/tenants/${tenantId}/accounts/${account.id}/live-trading`, { enabled });
    setRows(await get<TradingAccount[]>(`/tenants/${tenantId}/accounts`));
  }

  async function setStop(account: TradingAccount) {
    const enabled = !account.emergency_stop;
    if (enabled && !window.confirm(`Stop new orders on ${account.account_name}?`)) return;
    await post(`/tenants/${tenantId}/accounts/${account.id}/emergency-stop`, { enabled });
    setRows(await get<TradingAccount[]>(`/tenants/${tenantId}/accounts`));
  }

  async function addAccount() {
    const account_name = window.prompt('Account name');
    if (!account_name) return;
    const environment = (window.prompt('Environment: DEMO, LIVE or PROP_FIRM', 'DEMO') ?? 'DEMO').toUpperCase();
    const account_currency = (window.prompt('Currency: USD or NGN', 'USD') ?? 'USD').toUpperCase();
    await post(`/tenants/${tenantId}/accounts`, { account_name, environment, account_currency });
    onChanged();
    setRows(await get<TradingAccount[]>(`/tenants/${tenantId}/accounts`));
  }

  const connected = visible.filter((a) => a.connection_status === 'CONNECTED').length;

  return (
    <>
      {!embedded && (
        <PageHeader
          title="Trading Accounts"
          subtitle="Register Demo, Live and Prop Firm accounts without enabling execution by default."
          action={
            <button type="button" className="primary" onClick={addAccount}>
              <Plus />
              Add Trading Account
            </button>
          }
        />
      )}
      {embedded && (
        <div className="toolbar embedded-toolbar">
          <p className="muted">Environment filter: {environment === 'ALL' ? 'All' : environment.replace('_', ' ')}</p>
          <button type="button" className="primary" onClick={addAccount}>
            <Plus />
            Add Account
          </button>
        </div>
      )}
      <div className="metric-grid three">
        <Card className="mini">
          <span>Total Accounts</span>
          <strong>{visible.length}</strong>
          <small>Across active tenant</small>
        </Card>
        <Card className="mini">
          <span>Connected</span>
          <strong>{connected}</strong>
          <small>Local MT5 connections</small>
        </Card>
        <Card className="mini">
          <span>Autonomous Enabled</span>
          <strong>{visible.filter((a) => a.autonomous_trading_enabled).length}</strong>
          <small>Hard control remains off</small>
        </Card>
      </div>
      <Card>
        <div className="card-title">
          <div>
            <h2>Account registry</h2>
            <p>Each account has its own environment, denomination, connection and risk profile.</p>
          </div>
        </div>
        {visible.length === 0 ? (
          <Empty
            title="No trading accounts registered"
            text="Register a trading account here, then link it under System Control → MT5 Connections."
          />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Environment</th>
                  <th>Currency</th>
                  <th>Equity</th>
                  <th>Connection</th>
                  <th>Execution</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {visible.map((a) => (
                  <tr key={a.id}>
                    <td>
                      <b>{a.account_name}</b>
                    </td>
                    <td>{a.environment}</td>
                    <td>{a.account_currency}</td>
                    <td>{accountMoney(a.equity, a.account_currency)}</td>
                    <td>
                      <Status value={a.connection_status} />
                    </td>
                    <td>{executionLabel(a.emergency_stop ? 'EMERGENCY_STOP' : a.live_trading_enabled ? 'LIVE_EXECUTION' : 'SIMULATION')}</td>
                    <td>
                      {a.environment !== 'DEMO' ? (
                        <button type="button" onClick={() => setLive(a, !a.live_trading_enabled)}>
                          {a.live_trading_enabled ? 'Disable live' : 'Enable live'}
                        </button>
                      ) : null}
                      <button type="button" onClick={() => setStop(a)}>{a.emergency_stop ? 'Clear stop' : 'Emergency stop'}</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}

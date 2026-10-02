import React from 'react';
import { Plus, WalletCards } from 'lucide-react';
import { Card, Empty, PageHeader, Status } from '../components/Ui';
import { get, post } from '../lib/api';
import type { TradingAccount } from '../types';

export function Accounts({ tenantId, onChanged }: { tenantId: string; onChanged: () => void }) {
  const [rows, setRows] = React.useState<TradingAccount[]>([]);

  React.useEffect(() => {
    if (!tenantId) return;
    get<TradingAccount[]>(`/tenants/${tenantId}/accounts`).then(setRows).catch(() => setRows([]));
  }, [tenantId]);

  async function addAccount() {
    const account_name = window.prompt('Account name');
    if (!account_name) return;
    const environment = (window.prompt('Environment: DEMO, LIVE or PROP_FIRM', 'DEMO') ?? 'DEMO').toUpperCase();
    const account_currency = (window.prompt('Currency: USD or NGN', 'USD') ?? 'USD').toUpperCase();
    await post(`/tenants/${tenantId}/accounts`, { account_name, environment, account_currency });
    onChanged();
    setRows(await get<TradingAccount[]>(`/tenants/${tenantId}/accounts`));
  }

  const connected = rows.filter((a) => a.connection_status === 'CONNECTED').length;

  return (
    <>
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
      <div className="metric-grid three">
        <Card className="mini">
          <span>Total Accounts</span>
          <strong>{rows.length}</strong>
          <small>Across active tenant</small>
        </Card>
        <Card className="mini">
          <span>Connected</span>
          <strong>{connected}</strong>
          <small>Local MT5 connections</small>
        </Card>
        <Card className="mini">
          <span>Autonomous Enabled</span>
          <strong>{rows.filter((a) => a.autonomous_trading_enabled).length}</strong>
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
        {rows.length === 0 ? (
          <Empty
            title="No trading accounts registered"
            text="Add a Demo account first. Live and Prop Firm accounts use the same registry but retain independent safety controls."
          />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Environment</th>
                  <th>Currency</th>
                  <th>Connection</th>
                  <th>Trading</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((a) => (
                  <tr key={a.id}>
                    <td>
                      <b>{a.account_name}</b>
                    </td>
                    <td>{a.environment}</td>
                    <td>{a.account_currency}</td>
                    <td>
                      <Status value={a.connection_status} />
                    </td>
                    <td>{a.trading_enabled ? 'Enabled' : 'Disabled'}</td>
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

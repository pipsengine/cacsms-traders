import { useState } from 'react';
import { SubTabs } from '../../components/SubTabs';
import { TabPanel } from '../../components/PageTabs';
import { Accounts } from '../Accounts';
import { Card } from '../../components/Ui';
import type { Tenant } from '../../types';

const SUB = [
  { id: 'all', label: 'All Accounts' },
  { id: 'demo', label: 'Demo Accounts' },
  { id: 'live', label: 'Live Accounts' },
  { id: 'prop', label: 'Prop Firm Accounts' },
  { id: 'currency', label: 'Currency / Reporting' },
];

export function AccountsPanel({ tenantId, tenant, onChanged }: { tenantId: string; tenant?: Tenant; onChanged: () => void }) {
  const [sub, setSub] = useState('all');
  const env =
    sub === 'demo' ? 'DEMO' : sub === 'live' ? 'LIVE' : sub === 'prop' ? 'PROP_FIRM' : undefined;

  return (
    <>
      <SubTabs tabs={SUB} active={sub} onChange={setSub} />
      <TabPanel active={sub} id="all">
        <Accounts tenantId={tenantId} onChanged={onChanged} embedded environment="ALL" />
      </TabPanel>
      <TabPanel active={sub} id="demo">
        <Accounts tenantId={tenantId} onChanged={onChanged} embedded environment="DEMO" />
      </TabPanel>
      <TabPanel active={sub} id="live">
        <Accounts tenantId={tenantId} onChanged={onChanged} embedded environment="LIVE" />
      </TabPanel>
      <TabPanel active={sub} id="prop">
        <Accounts tenantId={tenantId} onChanged={onChanged} embedded environment="PROP_FIRM" />
      </TabPanel>
      <TabPanel active={sub} id="currency">
        <Card>
          <div className="card-title">
            <div>
              <h2>Account & reporting currency</h2>
              <p>Tenant reporting currency applies to consolidated views; each account carries its own denomination.</p>
            </div>
          </div>
          <div className="kv-list">
            <div className="kv-row">
              <span>Tenant reporting</span>
              <b>{tenant?.reporting_currency ?? 'USD'}</b>
            </div>
            <div className="kv-row">
              <span>Supported account currencies</span>
              <b>USD · NGN</b>
            </div>
          </div>
          <p className="muted">Account-level currency is set at registration. FX conversion for reporting will use backend services when enabled.</p>
        </Card>
      </TabPanel>
    </>
  );
}

import { useState } from 'react';
import { PageHeader, Notice } from '../components/Ui';
import { PageTabs, TabPanel } from '../components/PageTabs';
import { EnginePlaceholder } from '../components/EnginePlaceholder';

const TABS = [
  { id: 'campaigns', label: 'Campaigns' },
  { id: 'orders', label: 'Orders' },
  { id: 'open', label: 'Open Positions' },
  { id: 'closed', label: 'Closed Positions' },
  { id: 'history', label: 'Execution History' },
];

export function ExecutionPositions() {
  const [tab, setTab] = useState('campaigns');
  return (
    <>
      <PageHeader title="Execution & Positions" subtitle="Campaigns, orders, fills and position state — observability only." />
      <Notice title="Analysis-only boundary" text="Real order submission remains disabled." tone="warning" />
      <PageTabs tabs={TABS} active={tab} onChange={setTab} />
      {TABS.map((t) => (
        <TabPanel key={t.id} active={tab} id={t.id}>
          <EnginePlaceholder title={t.label} body="Execution ledger data will appear when the execution layer is approved and connected." engine="execution_gateway" />
        </TabPanel>
      ))}
    </>
  );
}

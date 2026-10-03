import { useState } from 'react';
import { PageHeader } from '../components/Ui';
import { PageTabs, TabPanel } from '../components/PageTabs';
import { EnginePlaceholder } from '../components/EnginePlaceholder';

const TABS = [
  { id: 'portfolio', label: 'Portfolio' },
  { id: 'account', label: 'Account Risk' },
  { id: 'exposure', label: 'Exposure' },
  { id: 'campaign', label: 'Campaign Allocation' },
  { id: 'auth', label: 'Authorizations' },
];

export function RiskPortfolio() {
  const [tab, setTab] = useState('portfolio');
  return (
    <>
      <PageHeader title="Risk & Portfolio" subtitle="Exposure, budgets, concentration and authorization decisions." />
      <PageTabs tabs={TABS} active={tab} onChange={setTab} />
      {TABS.map((t) => (
        <TabPanel key={t.id} active={tab} id={t.id}>
          <EnginePlaceholder title={t.label} body="Risk views consume authorization APIs. Production algorithms remain disabled in this foundation." engine="risk_authorization" />
        </TabPanel>
      ))}
    </>
  );
}

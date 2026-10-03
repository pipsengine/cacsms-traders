import { useState } from 'react';
import { PageHeader } from '../components/Ui';
import { PageTabs, TabPanel } from '../components/PageTabs';
import { EnginePlaceholder } from '../components/EnginePlaceholder';

const TABS = [
  { id: 'all', label: 'All Opportunities' },
  { id: 'watching', label: 'Watching' },
  { id: 'confirming', label: 'Confirming' },
  { id: 'risk', label: 'Ready for Risk' },
  { id: 'authorized', label: 'Authorized' },
  { id: 'completed', label: 'Completed' },
];

export function TradingOpportunities() {
  const [tab, setTab] = useState('all');
  return (
    <>
      <PageHeader title="Trading Opportunities" subtitle="Central lifecycle for hypotheses — evidence, confirmation and readiness." />
      <PageTabs tabs={TABS} active={tab} onChange={setTab} />
      {TABS.map((t) => (
        <TabPanel key={t.id} active={tab} id={t.id}>
          <EnginePlaceholder title={t.label} body="Opportunity records will stream from the opportunity engine API. No mock hypotheses are shown." engine="opportunity_engine" />
        </TabPanel>
      ))}
    </>
  );
}

import { useState } from 'react';
import { PageHeader } from '../components/Ui';
import { PageTabs, TabPanel } from '../components/PageTabs';
import { EnginePlaceholder } from '../components/EnginePlaceholder';

const TABS = [
  { id: 'performance', label: 'Performance' },
  { id: 'opportunity', label: 'Opportunity Performance' },
  { id: 'trade', label: 'Trade Analysis' },
  { id: 'ai', label: 'AI Learning' },
  { id: 'diagnostics', label: 'Diagnostics' },
];

export function PerformanceLearning() {
  const [tab, setTab] = useState('performance');
  return (
    <>
      <PageHeader title="Performance & Learning" subtitle="Outcomes, strategy analysis and learning diagnostics." />
      <PageTabs tabs={TABS} active={tab} onChange={setTab} />
      {TABS.map((t) => (
        <TabPanel key={t.id} active={tab} id={t.id}>
          <EnginePlaceholder title={t.label} body="Analytics bind to closed-loop learning APIs. No simulated performance is displayed." engine="learning_analytics" />
        </TabPanel>
      ))}
    </>
  );
}

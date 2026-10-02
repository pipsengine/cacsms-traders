import { useState } from 'react';
import { PageHeader } from '../components/Ui';
import { PageTabs, TabPanel } from '../components/PageTabs';
import { EnginePlaceholder } from '../components/EnginePlaceholder';

const TABS = [
  { id: 'regime', label: 'Multi-timeframe regime' },
  { id: 'swing', label: 'Swing structure' },
  { id: 'ranges', label: 'Ranges' },
  { id: 'hierarchy', label: 'Structural hierarchy' },
];

export function MarketStructure() {
  const [tab, setTab] = useState('regime');
  return (
    <>
      <PageHeader title="Market Structure" subtitle="Consolidated structural intelligence — regime, swings, ranges and hierarchy." />
      <PageTabs tabs={TABS} active={tab} onChange={setTab} />
      {TABS.map((t) => (
        <TabPanel key={t.id} active={tab} id={t.id}>
          <EnginePlaceholder
            title={t.label}
            body="Structural models are computed in backend engines and persisted before display. This tab will consume structure APIs when the Market Vision layer is integrated."
            engine="structure_intelligence"
          />
        </TabPanel>
      ))}
    </>
  );
}

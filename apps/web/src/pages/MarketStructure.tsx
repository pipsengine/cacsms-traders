import { useState } from 'react';
import { PageHeader } from '../components/Ui';
import { PageTabs, TabPanel } from '../components/PageTabs';
import { SubTabs } from '../components/SubTabs';
import { EnginePlaceholder } from '../components/EnginePlaceholder';

const TABS = [
  { id: 'mtf', label: 'Multi-Timeframe' },
  { id: 'regime', label: 'Regime' },
  { id: 'swing', label: 'Swing Structure' },
  { id: 'ranges', label: 'Ranges' },
  { id: 'relationships', label: 'Structural Relationships' },
];

const STRUCT_REL = [
  { id: 'tt', label: 'Trend → Trend' },
  { id: 'tc', label: 'Trend → Correction' },
  { id: 'rt', label: 'Range → Trend' },
  { id: 'rrt', label: 'Range → Range → Trend' },
  { id: 'tr', label: 'Trend → Range' },
  { id: 'rb', label: 'Range → Breakout' },
  { id: 'rev', label: 'Trend → Reversal Candidate' },
];

export function MarketStructure() {
  const [tab, setTab] = useState('mtf');
  const [relSub, setRelSub] = useState('tt');

  return (
    <>
      <PageHeader title="Market Structure" subtitle="Multi-timeframe regime, swings, ranges and structural hierarchy." />
      <PageTabs tabs={TABS} active={tab} onChange={setTab} />
      {TABS.filter((t) => t.id !== 'relationships').map((t) => (
        <TabPanel key={t.id} active={tab} id={t.id}>
          <EnginePlaceholder title={t.label} body="Structure models are computed in backend engines and persisted before display." engine="structure_intelligence" />
        </TabPanel>
      ))}
      <TabPanel active={tab} id="relationships">
        <SubTabs tabs={STRUCT_REL} active={relSub} onChange={setRelSub} />
        {STRUCT_REL.map((s) => (
          <TabPanel key={s.id} active={relSub} id={s.id}>
            <EnginePlaceholder title={s.label} body="Structural relationship classification will bind to the structure intelligence engine." engine="structure_intelligence" />
          </TabPanel>
        ))}
      </TabPanel>
    </>
  );
}

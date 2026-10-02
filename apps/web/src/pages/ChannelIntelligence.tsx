import { useState } from 'react';
import { PageHeader } from '../components/Ui';
import { PageTabs, TabPanel } from '../components/PageTabs';
import { EnginePlaceholder } from '../components/EnginePlaceholder';

const TABS = [
  { id: 'channels', label: 'Channel Analysis' },
  { id: 'breakout', label: 'Breakout & Retest' },
  { id: 'tit', label: 'Trend-in-Trend' },
];

export function ChannelIntelligence() {
  const [tab, setTab] = useState('channels');
  return (
    <>
      <PageHeader title="Channel Intelligence" subtitle="Channel, breakout/retest and trend-in-trend views — UI ready for backend engines." />
      <PageTabs tabs={TABS} active={tab} onChange={setTab} />
      {TABS.map((t) => (
        <TabPanel key={t.id} active={tab} id={t.id}>
          <EnginePlaceholder
            title={t.label}
            body="No market results are shown until the channel intelligence engine publishes verified snapshots."
            engine="channel_intelligence"
          />
        </TabPanel>
      ))}
    </>
  );
}

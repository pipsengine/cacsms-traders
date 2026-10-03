import React, { useState } from 'react';
import { PageHeader, Card } from '../components/Ui';
import { PageTabs, TabPanel } from '../components/PageTabs';
import { marketIntelligenceApi } from '../features/market-intelligence/api';
import { useAsync } from '../features/market-intelligence/hooks/useMarketIntelligence';
import { RelationshipTable } from '../features/market-intelligence/components/RelationshipTable';
import { LoadingSkeleton } from '../features/market-intelligence/components/LoadingSkeleton';
import { ErrorState } from '../features/market-intelligence/components/ErrorState';
import { EmptyState } from '../features/market-intelligence/components/EmptyState';
import { get } from '../lib/api';
import { EnginePlaceholder } from '../components/EnginePlaceholder';

const TABS = [
  { id: 'all', label: 'All Markets' },
  { id: 'attention', label: 'Attention Queue' },
  { id: 'episodes', label: 'Active Episodes' },
  { id: 'xauusd', label: 'XAUUSD' },
];

export function MarketScanner() {
  const [tab, setTab] = useState('all');
  const [instrumentCount, setInstrumentCount] = useState(29);
  const [symbols, setSymbols] = useState<string[]>([]);
  const rel = useAsync(() => marketIntelligenceApi.relationships(), []);

  React.useEffect(() => {
    get<{ symbol: string }[]>('/reference/instruments')
      .then((r) => {
        setInstrumentCount(r.length);
        setSymbols(r.map((x) => x.symbol));
      })
      .catch(() => {});
  }, []);

  const escalated =
    rel.data?.filter((r) => r.inspection_priority === 'HIGH' || r.inspection_priority === 'CRITICAL') ?? [];
  const xauRows = rel.data?.filter((r) => r.pair.includes('XAU')) ?? [];

  return (
    <>
      <PageHeader title="Market Scanner" subtitle="Autonomous scanning across the reference universe — attention without fabricated signals." />
      <PageTabs tabs={TABS} active={tab} onChange={setTab} />

      <div className="metric-grid three">
        <Card className="mini">
          <span>Instruments</span>
          <strong>{instrumentCount}</strong>
          <small>Reference universe</small>
        </Card>
        <Card className="mini">
          <span>Attention queue</span>
          <strong>{escalated.length}</strong>
          <small>Live relationship API</small>
        </Card>
        <Card className="mini">
          <span>Active episodes</span>
          <strong>0</strong>
          <small>Scanner worker pending</small>
        </Card>
      </div>

      <TabPanel active={tab} id="all">
        <Card>
          <div className="card-title">
            <div>
              <h2>Reference universe</h2>
              <p>{symbols.length ? `${symbols.length} configured symbols` : 'Loading instrument registry…'}</p>
            </div>
          </div>
          {symbols.length ? (
            <p className="symbol-cloud">{symbols.join(' · ')}</p>
          ) : (
            <EmptyState title="Instrument list unavailable" body="Reference instruments are served from the platform API." />
          )}
        </Card>
      </TabPanel>

      <TabPanel active={tab} id="attention">
        {rel.loading ? (
          <LoadingSkeleton />
        ) : rel.error ? (
          <ErrorState message={rel.error} onRetry={rel.refresh} />
        ) : escalated.length ? (
          <RelationshipTable rows={escalated} />
        ) : (
          <EmptyState title="Attention queue empty" body="High-priority relationships appear when intelligence snapshots exist." />
        )}
      </TabPanel>

      <TabPanel active={tab} id="episodes">
        <EnginePlaceholder
          title="Active episodes"
          body="Continuous scan episodes, condition tags and escalation reasons will publish from the market scanner worker."
          engine="market_scanner"
        />
      </TabPanel>

      <TabPanel active={tab} id="xauusd">
        {rel.loading ? (
          <LoadingSkeleton />
        ) : xauRows.length ? (
          <RelationshipTable rows={xauRows} />
        ) : (
          <EmptyState title="No XAUUSD intelligence snapshot" body="XAUUSD relationship rows appear when XAUUSD is processed by the worker." />
        )}
      </TabPanel>
    </>
  );
}

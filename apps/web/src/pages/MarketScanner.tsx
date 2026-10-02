import React, { useState } from 'react';
import { PageHeader, Card } from '../components/Ui';
import { marketIntelligenceApi } from '../features/market-intelligence/api';
import { useAsync } from '../features/market-intelligence/hooks/useMarketIntelligence';
import { RelationshipTable } from '../features/market-intelligence/components/RelationshipTable';
import { LoadingSkeleton } from '../features/market-intelligence/components/LoadingSkeleton';
import { ErrorState } from '../features/market-intelligence/components/ErrorState';
import { EmptyState } from '../features/market-intelligence/components/EmptyState';
import { get } from '../lib/api';
import { EnginePlaceholder } from '../components/EnginePlaceholder';

export function MarketScanner() {
  const [instrumentCount, setInstrumentCount] = useState(29);
  const rel = useAsync(() => marketIntelligenceApi.relationships(), []);

  React.useEffect(() => {
    get<{ symbol: string }[]>('/reference/instruments')
      .then((r) => setInstrumentCount(r.length))
      .catch(() => {});
  }, []);

  const escalated =
    rel.data?.filter(
      (r) => r.inspection_priority === 'HIGH' || r.inspection_priority === 'CRITICAL',
    ) ?? [];

  return (
    <>
      <PageHeader
        title="Market Scanner"
        subtitle="Autonomous attention across the reference universe — inspection priority and escalation reasons only."
      />
      <div className="metric-grid three">
        <Card className="mini">
          <span>Reference universe</span>
          <strong>{instrumentCount}</strong>
          <small>Configured instruments</small>
        </Card>
        <Card className="mini">
          <span>Escalated relationships</span>
          <strong>{escalated.length}</strong>
          <small>From strength intelligence API</small>
        </Card>
        <Card className="mini">
          <span>Opportunities</span>
          <strong>0</strong>
          <small>Not generated at this layer</small>
        </Card>
      </div>
      <Card>
        <div className="card-title">
          <div>
            <h2>Inspection queue</h2>
            <p>Pairs flagged for deeper structural analysis (live API data only).</p>
          </div>
        </div>
        {rel.loading ? (
          <LoadingSkeleton />
        ) : rel.error ? (
          <ErrorState message={rel.error} onRetry={rel.refresh} />
        ) : escalated.length ? (
          <RelationshipTable rows={escalated} />
        ) : (
          <EmptyState
            title="No escalations in the current snapshot"
            body="When the intelligence worker runs, high-priority relationships appear here. Instruments without data stay empty — nothing is fabricated."
          />
        )}
      </Card>
      <EnginePlaceholder
        title="Instrument-level scanner"
        body="Per-symbol scan results, condition tags and autonomous escalation reasons will bind to the dedicated scanner worker when shipped."
        engine="market_scanner"
      />
    </>
  );
}

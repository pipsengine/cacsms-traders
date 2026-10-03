import { useState } from 'react';
import { SubTabs } from '../../components/SubTabs';
import { TabPanel } from '../../components/PageTabs';
import { RelationshipDetail } from '../../features/market-intelligence/components/RelationshipDetail';
import { LoadingSkeleton } from '../../features/market-intelligence/components/LoadingSkeleton';
import { ErrorState } from '../../features/market-intelligence/components/ErrorState';
import { EmptyState } from '../../features/market-intelligence/components/EmptyState';
import { SectionCard } from '../../components/SectionCard';
import type { RelationshipRow } from '../../features/market-intelligence/types';

const METRIC_TABS = [
  { id: 'overview', label: 'Strength Gap' },
  { id: 'history', label: 'Gap History' },
  { id: 'slope', label: 'Slope' },
  { id: 'velocity', label: 'Velocity' },
  { id: 'acceleration', label: 'Acceleration' },
  { id: 'persistence', label: 'Persistence' },
  { id: 'divergence', label: 'Divergence' },
  { id: 'convergence', label: 'Convergence' },
  { id: 'equilibrium', label: 'Equilibrium' },
  { id: 'rotation', label: 'Rotation' },
  { id: 'transition', label: 'Transition' },
];

export function RelationshipAnalysisPanel({
  pair,
  rows,
  loading,
  error,
  onRetry,
}: {
  pair: string;
  rows: RelationshipRow[] | null;
  loading: boolean;
  error: string;
  onRetry: () => void;
}) {
  const [sub, setSub] = useState('overview');
  const latest = rows?.at(-1);

  if (loading) return <LoadingSkeleton />;
  if (error) return <ErrorState message={error} onRetry={onRetry} />;

  return (
    <>
      <SubTabs tabs={METRIC_TABS} active={sub} onChange={setSub} />
      <TabPanel active={sub} id="overview">
        {latest ? <RelationshipDetail pair={pair} rows={rows ?? []} /> : <EmptyState title="No snapshot" body="Select a pair with relationship history." />}
      </TabPanel>
      <TabPanel active={sub} id="history">
        {rows?.length ? (
          <SectionCard title="Gap history" description="Recent persisted snapshots (newest last).">
            <div className="mini-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>As of</th>
                    <th>Gap</th>
                    <th>State</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.slice(-24).map((r, i) => (
                    <tr key={`${r.as_of}-${i}`}>
                      <td>{r.as_of}</td>
                      <td>{r.gap.toFixed(4)}</td>
                      <td>{r.state}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </SectionCard>
        ) : (
          <EmptyState title="No gap history" body="History appears after relationship snapshots are persisted." />
        )}
      </TabPanel>
      {['slope', 'velocity', 'acceleration', 'persistence'].map((m) => (
        <TabPanel key={m} active={sub} id={m}>
          <MetricView
            title={METRIC_TABS.find((t) => t.id === m)?.label ?? m}
            latest={latest}
            field={m === 'slope' ? 'gap_velocity' : m === 'velocity' ? 'gap_velocity' : m === 'acceleration' ? 'gap_acceleration' : 'persistence'}
          />
        </TabPanel>
      ))}
      {['divergence', 'convergence', 'equilibrium', 'rotation', 'transition'].map((stateKey) => (
        <TabPanel key={stateKey} active={sub} id={stateKey}>
          <StateView stateKey={stateKey} latest={latest} rows={rows ?? []} pair={pair} />
        </TabPanel>
      ))}
    </>
  );
}

function MetricView({
  title,
  latest,
  field,
}: {
  title: string;
  latest?: RelationshipRow;
  field: keyof RelationshipRow;
}) {
  if (!latest) return <EmptyState title="No data" body="Awaiting relationship snapshots from the intelligence worker." />;
  const val = latest[field];
  return (
    <SectionCard title={title}>
      <strong className="overview-stat">{typeof val === 'number' ? val.toFixed(4) : String(val)}</strong>
      <p className="muted section-hint">Computed server-side for {latest.pair} · {latest.timeframe}</p>
    </SectionCard>
  );
}

function StateView({
  stateKey,
  latest,
  rows,
  pair,
}: {
  stateKey: string;
  latest?: RelationshipRow;
  rows: RelationshipRow[];
  pair: string;
}) {
  const target = stateKey.toUpperCase().replace('TRANSITION', 'TRANSITIONING');
  const matches = rows.filter((r) => r.state.toUpperCase().includes(target.slice(0, 4)));
  if (!latest) {
    return <EmptyState title="No state data" body="Relationship states appear after processing." />;
  }
  const active = latest.state.toLowerCase().includes(stateKey.slice(0, 5));
  return (
    <SectionCard title={`${stateKey.charAt(0).toUpperCase()}${stateKey.slice(1)} context`} description={`Pair ${pair}`}>
      <p className="muted">
        Current state: <b>{latest.state}</b> · {active ? 'Active classification for latest bar.' : 'Latest bar classified differently.'}
      </p>
      <p className="muted section-hint">{matches.length} historical snapshots tagged with related states.</p>
    </SectionCard>
  );
}

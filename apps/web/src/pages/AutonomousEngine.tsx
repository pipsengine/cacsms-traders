import { useCallback, useEffect, useRef, useState } from 'react';
import { AlertTriangle, ShieldAlert } from 'lucide-react';
import { usePollingAsync } from '../features/market-intelligence/hooks/useMarketIntelligence';
import { autonomousApi } from '../features/autonomous/api';
import { StatusRibbon } from '../features/autonomous/components/StatusRibbon';
import { StagePipeline } from '../features/autonomous/components/StagePipeline';
import { StageDetails } from '../features/autonomous/components/StageDetails';
import { OpportunitiesTable } from '../features/autonomous/components/OpportunitiesTable';
import { HistoryDrawer } from '../features/autonomous/components/HistoryDrawer';
import type { Opportunity, StageFilters, StageKey } from '../features/autonomous/types';

const LIVE_MS = 1000;
const CATCH_UP_MS = 15000;
const STAGE_KEY = 'ae_stage';
const STAGE_KEYS: StageKey[] = [
  'MARKET_DATA',
  'INTELLIGENCE',
  'SCANNER',
  'STRUCTURE',
  'CHANNEL',
  'OPPORTUNITY',
  'CONFIRMATION',
  'RISK',
  'EXECUTION',
  'MANAGEMENT',
  'LEARNING',
];

function usePageVisible() {
  const [visible, setVisible] = useState(() => typeof document === 'undefined' || document.visibilityState === 'visible');
  useEffect(() => {
    const onVis = () => setVisible(document.visibilityState === 'visible');
    document.addEventListener('visibilitychange', onVis);
    return () => document.removeEventListener('visibilitychange', onVis);
  }, []);
  return visible;
}

export function AutonomousEngine() {
  const visible = usePageVisible();
  const [stage, setStage] = useState<StageKey>(() => {
    const saved = localStorage.getItem(STAGE_KEY) as StageKey | null;
    return saved && STAGE_KEYS.includes(saved) ? saved : 'CHANNEL';
  });
  const [filters, setFilters] = useState<StageFilters>({ symbol: '', timeframe: '', provider: '' });
  const [history, setHistory] = useState<Opportunity | 'ALL' | null>(null);

  const overviewLoader = useCallback(() => autonomousApi.overview(), []);
  const overview = usePollingAsync(overviewLoader, [overviewLoader], { enabled: visible, intervalMs: LIVE_MS });

  const stageLoader = useCallback(() => autonomousApi.stage(stage, filters), [stage, filters]);
  const detail = usePollingAsync(stageLoader, [stageLoader], { enabled: visible, intervalMs: LIVE_MS });

  const oppsLoader = useCallback(() => autonomousApi.opportunities('ALL', 400), []);
  const opps = usePollingAsync(oppsLoader, [oppsLoader], { enabled: visible, intervalMs: LIVE_MS });

  const refreshAll = useRef(() => {});
  refreshAll.current = () => {
    overview.refresh();
    detail.refresh();
    opps.refresh();
  };
  useEffect(() => {
    if (!visible) return;
    let cancelled = false;
    const tick = () =>
      autonomousApi
        .catchUp()
        .then((r) => {
          if (!cancelled && r.ran) refreshAll.current();
        })
        .catch(() => undefined);
    tick();
    const t = window.setInterval(tick, CATCH_UP_MS);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, [visible]);

  const select = (k: StageKey) => {
    setStage(k);
    localStorage.setItem(STAGE_KEY, k);
  };

  const data = overview.data;
  const stages = data?.stages ?? [];
  const summary = stages.find((s) => s.key === stage) ?? null;
  const safety = data?.safety;
  const critical = safety && (safety.status === 'CRITICAL' || safety.status === 'HALTED');

  return (
    <div className="ae-page">
      <StatusRibbon data={data} error={overview.error} />

      {overview.error && data ? (
        <div className="ae-banner is-warn">
          <AlertTriangle size={15} /> Live refresh failed ({overview.error}). Showing the last state received at {new Date(data.ribbon.server_time).toISOString().slice(11, 19)} UTC.
        </div>
      ) : null}
      {overview.error && !data && !overview.loading ? (
        <div className="ae-banner is-bad">
          <AlertTriangle size={15} /> Autonomous engine status unavailable: {overview.error}
          <button type="button" className="ae-btn" onClick={overview.refresh}>
            Retry
          </button>
        </div>
      ) : null}
      {data && !data.enabled ? (
        <div className="ae-banner is-warn">
          <AlertTriangle size={15} /> The autonomous engine is disabled on this deployment (AUTONOMOUS_ENGINE_ENABLED). Showing the last persisted state.
        </div>
      ) : null}
      {critical ? (
        <div className="ae-banner is-bad">
          <ShieldAlert size={15} />
          <span>
            <b>Safety supervisor: {safety.status}.</b> {safety.blockers.join(' · ') || 'Progression is held until the condition clears.'}
          </span>
        </div>
      ) : safety?.status === 'DEGRADED' && safety.warnings.length ? (
        <div className="ae-banner is-warn">
          <AlertTriangle size={15} /> Safety supervisor degraded: {safety.warnings.slice(0, 3).join(' · ')}
        </div>
      ) : null}

      <StagePipeline stages={stages} selected={stage} onSelect={select} loading={overview.loading} />

      <StageDetails
        summary={summary}
        detail={detail.data}
        loading={detail.loading}
        error={detail.error}
        filters={filters}
        onFilters={setFilters}
        onRefresh={detail.refresh}
        refreshing={detail.refreshing}
        warnings={safety?.warnings ?? []}
      />

      <OpportunitiesTable
        data={opps.data}
        loading={opps.loading}
        error={opps.error}
        stages={stages}
        onHistory={setHistory}
        onLog={() => setHistory('ALL')}
        onRefresh={opps.refresh}
      />

      <HistoryDrawer target={history} onClose={() => setHistory(null)} />
    </div>
  );
}

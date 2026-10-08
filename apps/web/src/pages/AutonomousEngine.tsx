import { useCallback, useEffect, useRef, useState } from 'react';
import { AlertTriangle, ShieldAlert } from 'lucide-react';
import { usePollingAsync } from '../features/market-intelligence/hooks/useMarketIntelligence';
import { autonomousApi } from '../features/autonomous/api';
import { StatusRibbon } from '../features/autonomous/components/StatusRibbon';
import { StagePipeline } from '../features/autonomous/components/StagePipeline';
import { StageDetails } from '../features/autonomous/components/StageDetails';
import { OpportunitiesTable } from '../features/autonomous/components/OpportunitiesTable';
import { HistoryDrawer } from '../features/autonomous/components/HistoryDrawer';
import type { Opportunity, StageFilters, StageKey, StageSummary } from '../features/autonomous/types';

const LIVE_MS = 1000;
const CATCH_UP_MS = 15000;
const PIN_KEY = 'ae_stage_pin';
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

/** Furthest stage that still has open work. Channel is not the end of the pipeline. */
function furthestLive(stages: StageSummary[]): StageKey | null {
  const order: StageKey[] = ['RISK', 'CONFIRMATION', 'OPPORTUNITY'];
  const by = new Map(stages.map((s) => [s.key, s]));
  for (const key of order) {
    const s = by.get(key);
    if (!s || s.status === 'PENDING') continue;
    if (s.active > 0 || s.waiting > 0 || s.status === 'RUNNING') return key;
  }
  return null;
}

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
  const [pinned, setPinned] = useState<StageKey | null>(() => {
    const saved = localStorage.getItem(PIN_KEY) as StageKey | null;
    return saved && STAGE_KEYS.includes(saved) ? saved : null;
  });
  const [stage, setStage] = useState<StageKey>(pinned ?? 'OPPORTUNITY');
  const [filters, setFilters] = useState<StageFilters>({ symbol: '', timeframe: '', provider: '' });
  const [history, setHistory] = useState<Opportunity | 'ALL' | null>(null);
  const [resumeError, setResumeError] = useState('');

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
          if (cancelled) return;
          setResumeError(r.error ? `Engine resume failed (${r.error}).` : '');
          if (r.ran || r.error) refreshAll.current();
        })
        .catch((err: unknown) => {
          if (!cancelled) setResumeError(err instanceof Error ? err.message : 'Engine resume failed.');
        });
    tick();
    const t = window.setInterval(tick, CATCH_UP_MS);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, [visible]);

  const select = (k: StageKey) => {
    setPinned(k);
    setStage(k);
    localStorage.setItem(PIN_KEY, k);
  };
  const follow = () => {
    setPinned(null);
    localStorage.removeItem(PIN_KEY);
  };

  const data = overview.data;
  const stages = data?.stages ?? [];
  const live = furthestLive(stages);
  useEffect(() => {
    if (pinned) return;
    if (live) setStage(live);
  }, [pinned, live]);
  const summary = stages.find((s) => s.key === stage) ?? null;
  const safety = data?.safety;
  const critical = safety && (safety.status === 'CRITICAL' || safety.status === 'HALTED');

  return (
    <div className="ae-page">
      <div className="ae-top">
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
      {resumeError ? (
        <div className="ae-banner is-bad">
          <AlertTriangle size={15} /> {resumeError}
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
      </div>

      <div className="ae-pipeline-bar">
        <StagePipeline stages={stages} selected={stage} live={live} onSelect={select} loading={overview.loading} />
        {pinned ? (
          <button type="button" className="ae-follow" onClick={follow}>
            Follow live stage
          </button>
        ) : (
          <span className="ae-follow is-on">Following the live stage</span>
        )}
      </div>

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

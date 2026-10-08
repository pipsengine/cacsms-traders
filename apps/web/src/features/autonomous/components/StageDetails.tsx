import type { CSSProperties } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { pretty, tone, utc, utcFull, until } from '../format';
import type { StageDetail, StageFilters, StageSummary } from '../types';
import { ChannelStage } from './ChannelStage';
import { GenericStage } from './GenericStage';
import { useNow } from './DetailParts';
import { STAGE_ICON } from './StagePipeline';

const PURPOSE: Record<string, string> = {
  MARKET_DATA: 'Normalised closed-bar market data from the active provider, with freshness and provenance for every instrument.',
  INTELLIGENCE: 'Currency strength and relationships computed on closed bars across the 28 major pairs.',
  SCANNER: 'Ranks the instrument universe by strength alignment and structure, selecting candidates for deep inspection.',
  STRUCTURE: 'Swing structure, BOS / CHoCH and trend state on closed bars across W, D1, H8 and H1.',
  CHANNEL: 'Analysing channel structures, ERZ, touches, breaks, retests and Trend-in-Trend (TiT) across multiple timeframes.',
  OPPORTUNITY: 'P1 retracement, P2 breakout-retest, continuation and TiT setups detected autonomously, waiting for their entry zone.',
  CONFIRMATION: 'Inside the entry zone: a rejection candle, then a close beyond it or an H1 BOS confirms the reaction.',
  RISK: 'Reward-to-risk, confidence, concurrency and currency-exposure rules authorise, defer or reject confirmed setups.',
  EXECUTION: 'Analysis-only: every authorised plan stops at EXECUTION_BLOCKED_ANALYSIS_ONLY. No broker orders are submitted.',
  MANAGEMENT: 'Manages broker positions when execution is enabled. In analysis-only mode there are no positions to manage.',
  LEARNING: 'Shadow outcomes of analysis-only plans (target before stop) feed performance statistics by setup type.',
};

const TIMEFRAMES = ['W', 'D1', 'H8', 'H1'];

export function StageDetails({
  summary,
  detail,
  loading,
  error,
  filters,
  onFilters,
  onRefresh,
  refreshing,
  warnings,
}: {
  summary: StageSummary | null;
  detail: StageDetail | null;
  loading: boolean;
  error: string;
  filters: StageFilters;
  onFilters: (f: StageFilters) => void;
  onRefresh: () => void;
  refreshing: boolean;
  warnings: string[];
}) {
  const now = useNow();
  const head = detail ?? summary;
  const status = detail?.status ?? summary?.status ?? 'PENDING';
  const color = head?.color ?? '#2563eb';
  const symbols = detail?.symbols ?? [];
  const showDetail = detail && detail.key === summary?.key;

  return (
    <section className="ae-details" style={{ '--stage': color } as CSSProperties} aria-label="Stage details">
      <header className="ae-details-head">
        <div className="ae-details-title">
          <span className="ae-details-icon" aria-hidden>
            {summary ? STAGE_ICON[summary.key] : null}
          </span>
          <div>
            <h2>
              Stage {head?.number ?? '—'} — {head?.label ?? 'Loading'}
              <span className={`ae-badge is-${tone(status)}`}>{summary?.stale ? 'Stale' : pretty(status)}</span>
            </h2>
            <p>{summary ? PURPOSE[summary.key] : ''}</p>
          </div>
        </div>
        <div className="ae-filters">
          <label>
            Provider
            <select value={filters.provider} onChange={(e) => onFilters({ ...filters, provider: e.target.value })}>
              <option value="">All</option>
              <option value="mt5">MT5</option>
              <option value="ctrader">cTrader</option>
            </select>
          </label>
          <label>
            Timeframe
            <select value={filters.timeframe} onChange={(e) => onFilters({ ...filters, timeframe: e.target.value })}>
              <option value="">All</option>
              {TIMEFRAMES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>
          <label>
            Symbol
            <select value={filters.symbol} onChange={(e) => onFilters({ ...filters, symbol: e.target.value })}>
              <option value="">All</option>
              {symbols.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <button type="button" className="ae-icon-btn" onClick={onRefresh} title="Reload stage data (read-only)" aria-label="Reload stage data">
            <RefreshCw size={15} className={refreshing ? 'ae-spin' : ''} />
          </button>
        </div>
        <dl className="ae-times">
          <div>
            <dt>Last Update</dt>
            <dd>{utcFull(detail?.last_update)}</dd>
          </div>
          <div>
            <dt>Last Successful Cycle</dt>
            <dd>{detail?.last_successful_cycle ? utc(detail.last_successful_cycle, true) : '—'}</dd>
          </div>
          <div>
            <dt>Next Cycle</dt>
            <dd className="is-next">{detail?.next_cycle_at ? until(detail.next_cycle_at, now) : '—'}</dd>
          </div>
        </dl>
      </header>

      {detail?.provider_mismatch ? (
        <div className="ae-banner is-warn">
          <AlertTriangle size={15} /> This stage last ran on {detail.provider?.toUpperCase()}; the {filters.provider.toUpperCase()} filter has no data for it.
        </div>
      ) : null}
      {summary?.stale ? (
        <div className="ae-banner is-warn">
          <AlertTriangle size={15} /> Stage data is stale — the last update was {utc(summary.last_update, true)} UTC. The engine resumes and replays missed closed bars
          automatically.
        </div>
      ) : null}
      {detail && !detail.available ? (
        <div className="ae-banner is-info">This stage has not completed a cycle yet. It populates on the next autonomous cycle.</div>
      ) : null}

      {error && !showDetail ? (
        <div className="ae-banner is-bad">
          <AlertTriangle size={15} /> Stage details unavailable: {error}
          <button type="button" className="ae-btn" onClick={onRefresh}>
            Retry
          </button>
        </div>
      ) : loading && !showDetail ? (
        <div className="ae-skeleton-block" aria-busy="true">
          <div className="ae-kpis" style={{ '--n': 6 } as CSSProperties}>
            {Array.from({ length: 6 }, (_, i) => (
              <div key={i} className="ae-kpi is-skeleton">
                <span className="ae-skel" style={{ width: '70%' }} />
                <span className="ae-skel" style={{ width: '40%', height: 18 }} />
              </div>
            ))}
          </div>
          <div className="ae-grid ae-grid-3">
            {Array.from({ length: 3 }, (_, i) => (
              <div key={i} className="ae-card is-skeleton" style={{ height: 220 }} />
            ))}
          </div>
        </div>
      ) : showDetail ? (
        detail.key === 'CHANNEL' ? (
          <ChannelStage d={detail} onRefresh={onRefresh} />
        ) : (
          <GenericStage d={detail} warnings={warnings} />
        )
      ) : null}
    </section>
  );
}

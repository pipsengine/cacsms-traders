import { useCallback, useMemo, useState, type ReactNode } from 'react';
import { Brain, Microscope, TrendingDown, TrendingUp, Minus } from 'lucide-react';
import { marketIntelligenceApi } from '../api';
import { usePollingAsync } from '../hooks/useMarketIntelligence';
import type { HistoryPeriod, KeyLabel, RelationshipAnalysisPayload } from '../types';
import { CoverageNotice, IntelBadge, PeriodPills, ageText, signed } from '../intelUi';
import { CurrencyFlag } from './CurrencyFlag';
import { EmptyState } from './EmptyState';
import { MatrixBlockingState, MatrixStatusBanners } from './MatrixPanelStates';
import { DifferentialBar } from './PairRelationshipsTab';
import { TimeSeriesChart, fmtUtc } from './TimeSeriesChart';

const POLL_MS = 2000;
export const FX_PAIRS_28 = [
  'AUDCAD', 'AUDCHF', 'AUDJPY', 'AUDNZD', 'AUDUSD', 'CADCHF', 'CADJPY', 'CHFJPY', 'EURAUD', 'EURCAD',
  'EURCHF', 'EURGBP', 'EURJPY', 'EURNZD', 'EURUSD', 'GBPAUD', 'GBPCAD', 'GBPCHF', 'GBPJPY', 'GBPNZD',
  'GBPUSD', 'NZDCAD', 'NZDCHF', 'NZDJPY', 'NZDUSD', 'USDCAD', 'USDCHF', 'USDJPY',
];

function DirectionIcon({ k }: { k: string }) {
  if (k === 'STRENGTHENING') return <TrendingUp size={14} className="up" />;
  if (k === 'WEAKENING') return <TrendingDown size={14} className="down" />;
  return <Minus size={14} className="muted" />;
}

function CurrencySide({
  code,
  role,
  score,
  cls,
  direction,
}: {
  code: string;
  role: 'Base' | 'Quote';
  score: number;
  cls: { label: string; tone: string };
  direction: KeyLabel & { change: number | null };
}) {
  return (
    <div className={`si-side si-side--${role.toLowerCase()}`}>
      <span className="si-side-role">{role} currency</span>
      <div className="si-side-head">
        <CurrencyFlag code={code} size={26} />
        <strong>{code}</strong>
        <span className={`si-currency-pill si-currency-pill--${cls.tone}`}>{cls.label}</span>
      </div>
      <div className="si-side-score">
        {score.toFixed(1)}
        <small>/100</small>
      </div>
      <span className="si-side-dir">
        <DirectionIcon k={direction.key} />
        {direction.label}
        {direction.change !== null ? ` (${signed(direction.change)})` : ''}
      </span>
    </div>
  );
}

function Kpi({ title, children, foot }: { title: string; children: ReactNode; foot?: ReactNode }) {
  return (
    <div className="si-kpi">
      <span className="si-kpi-title">{title}</span>
      <div className="si-kpi-body">{children}</div>
      {foot ? <span className="si-kpi-foot">{foot}</span> : null}
    </div>
  );
}

function AnalysisBody({ data }: { data: RelationshipAnalysisPayload }) {
  const r = data.relationship;
  const s = data.summary;
  const t = data.thresholds;
  const rel = Object.fromEntries(t.relationship.map((x) => [x.key, x.min]));
  const maxAbs = Math.max(rel.STRONG_DIVERGENCE + 10, ...data.history.map((h) => Math.abs(h.differential)), Math.abs(r.differential));
  const lim = Math.ceil(maxAbs / 10) * 10;
  const side = (x: string) => (x === 'BASE' ? r.base : x === 'QUOTE' ? r.quote : '—');
  const chartSeries = useMemo(
    () => [{ key: 'diff', label: `${r.base}−${r.quote}`, color: '#2563eb', values: data.history.map((h) => h.differential), area: true, emphasis: true }],
    [data.history, r.base, r.quote],
  );
  const times = useMemo(() => data.history.map((h) => h.at), [data.history]);
  const refAge = ageText(data.meta.reference_age_minutes);

  return (
    <>
      <div className="si-hero">
        <CurrencySide code={r.base} role="Base" score={r.base_strength} cls={r.base_class} direction={s.base_direction} />
        <div className="si-hero-mid">
          <span className="si-side-role">Strength differential (base − quote)</span>
          <div className={`si-hero-diff ${r.differential >= 0 ? 'base' : 'quote'}`}>{signed(r.differential)}</div>
          <DifferentialBar value={r.differential} max={lim} />
          <div className="si-hero-badges">
            <IntelBadge k={r.relationship.key} label={r.relationship.label} />
            <IntelBadge k={s.state.key} label={s.state.label} />
          </div>
          <span className="si-hero-note">
            {r.dominant === 'NONE' ? 'Neither currency dominates' : `${side(r.dominant)} is the stronger currency`}
          </span>
        </div>
        <CurrencySide code={r.quote} role="Quote" score={r.quote_strength} cls={r.quote_class} direction={s.quote_direction} />
      </div>

      <div className="si-kpis">
        <Kpi title="Structural state" foot={refAge ? `vs snapshot ${refAge} ago` : 'Awaiting reference snapshot'}>
          <IntelBadge k={s.state.key} label={s.state.label} />
        </Kpi>
        <Kpi title="Timeframe alignment" foot={`Favouring ${side(s.alignment.direction)}`}>
          <strong>
            {s.alignment.aligned}/{s.alignment.total}
          </strong>
          <span className="si-kpi-sub">{s.alignment.pct.toFixed(0)}%</span>
          <IntelBadge k={s.alignment.key} label={s.alignment.label} />
        </Kpi>
        <Kpi title="HTF vs LTF" foot={`HTF ${side(s.htf_ltf.htf)} · LTF ${side(s.htf_ltf.ltf)}`}>
          <IntelBadge k={s.htf_ltf.key} label={s.htf_ltf.label} />
        </Kpi>
        <Kpi
          title="Persistence"
          foot={
            s.run.since
              ? `${s.run.bounded_by_history ? 'Same side since history start' : 'Current side since'} ${fmtUtc(s.run.since)}`
              : undefined
          }
        >
          {s.persistence.pct !== undefined ? <strong>{s.persistence.pct.toFixed(0)}%</strong> : null}
          <IntelBadge k={s.persistence.key} label={s.persistence.label} />
        </Kpi>
        <Kpi
          title="Differential trajectory"
          foot={s.trajectory.slope_per_hour !== null ? `${signed(s.trajectory.slope_per_hour, 2)} pts/hour` : undefined}
        >
          <IntelBadge k={s.trajectory.key} label={s.trajectory.label} />
          {s.trajectory.window_change !== null ? <span className="si-kpi-sub">{signed(s.trajectory.window_change)} pts</span> : null}
        </Kpi>
        <Kpi title="Dynamics" foot={r.dynamics.previous !== null ? `Was ${signed(r.dynamics.previous)}` : undefined}>
          <IntelBadge k={r.dynamics.key} label={r.dynamics.label} />
          {r.dynamics.change !== null ? <span className="si-kpi-sub">{signed(r.dynamics.change)}</span> : null}
        </Kpi>
      </div>

      <div className="si-analysis-grid">
        <section className="si-panel">
          <header className="si-subhead">
            <h3>Multi-timeframe differential matrix</h3>
            <p>Base − quote score per timeframe; change and state vs the reference snapshot.</p>
          </header>
          <div className="si-table-wrap">
            <table className="si-table si-mtf-table">
              <thead>
                <tr>
                  <th className="left">TF</th>
                  <th>{r.base}</th>
                  <th>{r.quote}</th>
                  <th>Differential</th>
                  <th>Change</th>
                  <th>Relationship</th>
                  <th>State</th>
                  <th>Persistence</th>
                </tr>
              </thead>
              <tbody>
                {data.matrix.map((m, i) => (
                  <tr key={m.timeframe} className={i === t.htf.length ? 'si-group-break' : undefined}>
                    <td className="left">
                      <strong>{m.timeframe}</strong> <small className="muted">{m.group}</small>
                    </td>
                    {m.available ? (
                      <>
                        <td className="num">{m.base?.toFixed(1)}</td>
                        <td className="num">{m.quote?.toFixed(1)}</td>
                        <td>
                          <DifferentialBar value={m.differential ?? 0} max={lim} />
                        </td>
                        <td className={`num ${(m.change ?? 0) > 0 ? 'up' : (m.change ?? 0) < 0 ? 'down' : ''}`}>{signed(m.change)}</td>
                        <td>{m.relationship ? <IntelBadge k={m.relationship.key} label={m.relationship.label} /> : null}</td>
                        <td>{m.state ? <IntelBadge k={m.state.key} label={m.state.label} /> : null}</td>
                        <td className="num">{m.persistence === null || m.persistence === undefined ? '—' : `${Math.round(m.persistence * 100)}%`}</td>
                      </>
                    ) : (
                      <td colSpan={7} className="muted">
                        No strength data for this timeframe
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="si-panel si-interpretation">
          <header className="si-subhead">
            <h3>
              <Brain size={15} aria-hidden /> Structural interpretation
            </h3>
            <p>Machine-generated from the computed fields above.</p>
          </header>
          <ul>
            {data.interpretation.map((line, i) => (
              <li key={i} className={i === data.interpretation.length - 1 ? 'si-disclaimer' : undefined}>
                {line}
              </li>
            ))}
          </ul>
        </section>
      </div>

      <section className="si-panel">
        <header className="si-subhead">
          <h3>Historical differential — {data.meta.period}</h3>
          <p>
            Composite (AVG) {r.base} − {r.quote} from persisted snapshots. Bands mark the Moderate (±{rel.MODERATE}), Divergence (±
            {rel.DIVERGENCE}) and Strong Divergence (±{rel.STRONG_DIVERGENCE}) thresholds.
          </p>
        </header>
        <div className={`si-chart-card ${data.meta.stale ? 'is-stale' : ''}`}>
          {data.history.length < 2 ? (
            <EmptyState title="Not enough history yet" body="The differential chart appears once two or more snapshots exist in this window." />
          ) : (
            <TimeSeriesChart
              times={times}
              series={chartSeries}
              yDomain={[-lim, lim]}
              height={260}
              minGapMs={data.meta.snapshot_interval_seconds * 3000}
              formatValue={(v) => signed(v)}
              ariaLabel={`${r.pair} strength differential ${data.meta.period}`}
              refLines={[
                { y: 0, label: 'Equilibrium', color: '#64748b' },
                { y: rel.DIVERGENCE, label: `${r.base} divergence`, color: '#93c5fd', dashed: true },
                { y: -rel.DIVERGENCE, label: `${r.quote} divergence`, color: '#fcd34d', dashed: true },
              ]}
              bands={[
                { from: -rel.MODERATE, to: rel.MODERATE, color: 'rgba(100,116,139,0.07)' },
                { from: rel.STRONG_DIVERGENCE, to: lim, color: 'rgba(37,99,235,0.06)' },
                { from: -lim, to: -rel.STRONG_DIVERGENCE, color: 'rgba(217,119,6,0.06)' },
              ]}
            />
          )}
        </div>
      </section>
    </>
  );
}

export function RelationshipAnalysisTab({
  enabled,
  pair,
  onPairChange,
}: {
  enabled: boolean;
  pair: string;
  onPairChange: (pair: string) => void;
}) {
  const [period, setPeriod] = useState<HistoryPeriod>('24H');
  const loader = useCallback(() => marketIntelligenceApi.relationshipAnalysis(pair, period), [pair, period]);
  const q = usePollingAsync(loader, [loader], { enabled, intervalMs: POLL_MS });
  const data = q.data && q.data.meta.pair === pair && q.data.meta.period === period ? q.data : null;

  return (
    <section className="mi-card si-intel-card">
      <header className="mi-matrix-card-head">
        <div className="si-card-head">
          <span className="si-icon-block" aria-hidden>
            <Microscope size={16} />
          </span>
          <div>
            <h2>Relationship analysis</h2>
            <p className="mi-matrix-sub">
              Is the strength difference expanding, contracting, persistent, converging or reversing? Structural analysis only —
              no trade signals.
            </p>
          </div>
        </div>
        <div className="si-intel-controls">
          <label>
            Pair
            <select value={pair} onChange={(e) => onPairChange(e.target.value)} aria-label="Pair">
              {FX_PAIRS_28.map((p) => (
                <option key={p} value={p}>
                  {p.slice(0, 3)}/{p.slice(3)}
                </option>
              ))}
            </select>
          </label>
          <PeriodPills value={period} onChange={setPeriod} />
        </div>
      </header>

      {!data ? (
        <MatrixBlockingState loading={q.loading || enabled} error={q.error} onRetry={q.refresh} label={`${pair} analysis`} />
      ) : (
        <>
          <div className="si-intel-banners">
            <MatrixStatusBanners meta={data.meta} error={q.error} hasScores onRetry={q.refresh} />
            <CoverageNotice coverage={data.meta.coverage} period={period} />
          </div>
          <div className={`si-analysis ${data.meta.stale ? 'is-stale' : ''}`}>
            <AnalysisBody data={data} />
          </div>
          <footer className="si-matrix-footer">
            <span className="si-footer-item">
              Calculated <strong>{fmtUtc(data.meta.as_of ?? data.meta.to)}</strong>
            </span>
            <span className="si-footer-item">
              History <strong>{data.meta.history_points}</strong> snapshots · coverage <strong>{data.meta.coverage.pct.toFixed(0)}%</strong>
            </span>
            <span className="si-footer-item">
              HTF <strong>{data.thresholds.htf.join(' ')}</strong> · LTF <strong>{data.thresholds.ltf.join(' ')}</strong>
            </span>
          </footer>
        </>
      )}
    </section>
  );
}

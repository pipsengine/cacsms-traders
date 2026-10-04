import { useCallback, useMemo, useState } from 'react';
import { ArrowDown, ArrowUp, GitCompareArrows, LineChart, RefreshCcw, Repeat2 } from 'lucide-react';
import { marketIntelligenceApi } from '../api';
import { usePollingAsync } from '../hooks/useMarketIntelligence';
import type { CurrencyHistoryStats, HistoryPeriod, StrengthEvent } from '../types';
import { CURRENCY_COLORS, CoverageNotice, IntelBadge, PeriodPills, SI_CURRENCIES, signed } from '../intelUi';
import { CurrencyFlag } from './CurrencyFlag';
import { EmptyState } from './EmptyState';
import { MatrixBlockingState, MatrixStatusBanners } from './MatrixPanelStates';
import { TimeSeriesChart, fmtUtc, type ChartSeries } from './TimeSeriesChart';

const POLL_MS = 10_000;
const TIMEFRAMES = ['AVG', 'YTD', 'Q', 'MN', 'W', 'D1', 'H8', 'H1', 'M15', 'M5', 'M1'];
type SortKey = 'current' | 'change' | 'change_pct' | 'high' | 'low' | 'average';
const COLUMNS: { key: SortKey; label: string }[] = [
  { key: 'current', label: 'Current' },
  { key: 'change', label: 'Change' },
  { key: 'change_pct', label: '% Change' },
  { key: 'high', label: 'High' },
  { key: 'low', label: 'Low' },
  { key: 'average', label: 'Average' },
];

const EVENT_ICON = {
  REVERSAL: <Repeat2 size={14} />,
  CROSSOVER: <GitCompareArrows size={14} />,
  MIDLINE: <RefreshCcw size={14} />,
};

function eventCurrencies(e: StrengthEvent) {
  return e.currencies ?? (e.currency ? [e.currency] : []);
}

export function HistoricalStrengthTab({ enabled }: { enabled: boolean }) {
  const [period, setPeriod] = useState<HistoryPeriod>('24H');
  const [timeframe, setTimeframe] = useState('AVG');
  const [selected, setSelected] = useState<string[]>([...SI_CURRENCIES]);
  const [focus, setFocus] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>('current');
  const [sortAsc, setSortAsc] = useState(false);

  const loader = useCallback(() => marketIntelligenceApi.historicalStrength(period, timeframe), [period, timeframe]);
  const q = usePollingAsync(loader, [loader], { enabled, intervalMs: POLL_MS });
  const data = q.data && q.data.period === period && q.data.meta.timeframe === timeframe ? q.data : null;

  const toggle = (c: string) =>
    setSelected((s) => (s.includes(c) ? s.filter((x) => x !== c) : [...s, c]));

  const series: ChartSeries[] = useMemo(
    () =>
      data
        ? SI_CURRENCIES.filter((c) => selected.includes(c)).map((c) => ({
            key: c,
            label: c,
            color: CURRENCY_COLORS[c],
            values: data.chart.values[c] ?? [],
            emphasis: focus === c,
            dimmed: focus !== null && focus !== c,
          }))
        : [],
    [data, selected, focus],
  );

  const stats = useMemo(() => {
    if (!data) return [];
    const rows = data.currencies.filter((s) => selected.includes(s.currency));
    const val = (s: CurrencyHistoryStats) => (s.available ? (s[sortKey] as number | null | undefined) ?? -Infinity : -Infinity);
    return [...rows].sort((a, b) => (sortAsc ? val(a) - val(b) : val(b) - val(a)));
  }, [data, selected, sortKey, sortAsc]);

  const events = useMemo(
    () => (data ? data.events.filter((e) => eventCurrencies(e).some((c) => selected.includes(c))) : []),
    [data, selected],
  );

  const sortBy = (k: SortKey) => {
    setSortAsc((a) => (k === sortKey ? !a : false));
    setSortKey(k);
  };

  const strong = data?.thresholds.classification.find((c) => c.key === 'STRONG')?.min ?? 60;
  const weak = data?.thresholds.classification.find((c) => c.key === 'WEAK')?.min ?? 40;

  return (
    <>
      <section className="mi-card si-intel-card">
        <header className="mi-matrix-card-head">
          <div className="si-card-head">
            <span className="si-icon-block" aria-hidden>
              <LineChart size={16} />
            </span>
            <div>
              <h2>Historical currency strength</h2>
              <p className="mi-matrix-sub">
                How each currency’s normalized strength (0–100) has changed, from persisted Strength Engine snapshots.
              </p>
            </div>
          </div>
          <div className="si-intel-controls">
            <PeriodPills value={period} onChange={setPeriod} />
            <label>
              Strength
              <select value={timeframe} onChange={(e) => setTimeframe(e.target.value)} aria-label="Strength timeframe">
                {TIMEFRAMES.map((tf) => (
                  <option key={tf} value={tf}>
                    {tf === 'AVG' ? 'AVG (composite)' : tf}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </header>

        {!data ? (
          <MatrixBlockingState loading={q.loading || enabled} error={q.error} onRetry={q.refresh} label="historical strength" />
        ) : (
          <>
            <div className="si-intel-banners">
              <MatrixStatusBanners meta={data.meta} error={q.error} hasScores onRetry={q.refresh} />
              <CoverageNotice coverage={data.coverage} period={period} />
            </div>

            <div className="si-chip-row" role="group" aria-label="Currencies">
              {SI_CURRENCIES.map((c) => {
                const s = data.currencies.find((x) => x.currency === c);
                const on = selected.includes(c);
                return (
                  <button
                    key={c}
                    type="button"
                    className={`si-chip ${on ? 'on' : ''}`}
                    style={on ? { borderColor: CURRENCY_COLORS[c] } : undefined}
                    aria-pressed={on}
                    onClick={() => toggle(c)}
                    onMouseEnter={() => on && setFocus(c)}
                    onMouseLeave={() => setFocus(null)}
                  >
                    <i style={{ background: CURRENCY_COLORS[c] }} />
                    <CurrencyFlag code={c} size={16} />
                    {c}
                    <b>{s?.available ? s.current?.toFixed(1) : '—'}</b>
                  </button>
                );
              })}
              <span className="si-chip-actions">
                <button type="button" onClick={() => setSelected([...SI_CURRENCIES])}>
                  All
                </button>
                <button type="button" onClick={() => setSelected([])}>
                  None
                </button>
              </span>
            </div>

            <div className={`si-chart-card ${data.meta.stale ? 'is-stale' : ''}`}>
              {data.points < 2 ? (
                <EmptyState
                  title="Not enough history yet"
                  body="The chart appears once the Strength Engine has persisted at least two snapshots in this window."
                />
              ) : !series.length ? (
                <EmptyState title="No currencies selected" body="Select one or more currencies above." />
              ) : (
                <TimeSeriesChart
                  times={data.chart.times}
                  series={series}
                  yDomain={[0, 100]}
                  height={320}
                  minGapMs={data.meta.snapshot_interval_seconds * 3000}
                  ariaLabel={`Currency strength ${period} ${timeframe}`}
                  refLines={[
                    { y: 50, label: 'Neutral 50', dashed: true },
                    { y: strong, label: `Strong ≥ ${strong}`, color: '#86efac', dashed: true },
                    { y: weak, label: `Weak < ${weak}`, color: '#fca5a5', dashed: true },
                  ]}
                  bands={[
                    { from: strong, to: 100, color: 'rgba(34,197,94,0.05)' },
                    { from: 0, to: weak, color: 'rgba(239,68,68,0.05)' },
                  ]}
                />
              )}
            </div>
            <footer className="si-matrix-footer">
              <span className="si-footer-item">
                Window <strong>{fmtUtc(data.from)}</strong> → <strong>{fmtUtc(data.to)}</strong>
              </span>
              <span className="si-footer-item">
                Snapshots <strong>{data.points}</strong>
              </span>
              <span className="si-footer-item">
                Coverage <strong>{data.coverage.pct.toFixed(0)}%</strong>
              </span>
              <span className="si-footer-item">Latest point = current engine calculation; earlier points are persisted snapshots.</span>
            </footer>
          </>
        )}
      </section>

      {data ? (
        <div className="si-intel-grid">
          <section className="mi-card si-intel-card">
            <header className="si-subhead">
              <h3>Strength statistics — {period}</h3>
              <p>Trend uses ±{data.thresholds.trend_band} points; momentum compares the latest third of the window with the third before it.</p>
            </header>
            <div className="si-table-wrap">
              <table className="si-table">
                <thead>
                  <tr>
                    <th className="left">Currency</th>
                    {COLUMNS.map((c) => (
                      <th key={c.key}>
                        <button
                          type="button"
                          className={`mi-th-sort ${sortKey === c.key ? 'active' : ''}`}
                          onClick={() => sortBy(c.key)}
                        >
                          {c.label}
                          {sortKey === c.key ? sortAsc ? <ArrowUp size={11} /> : <ArrowDown size={11} /> : null}
                        </button>
                      </th>
                    ))}
                    <th>Trend</th>
                    <th>Momentum</th>
                  </tr>
                </thead>
                <tbody>
                  {stats.map((s) => (
                    <tr key={s.currency} onMouseEnter={() => setFocus(s.currency)} onMouseLeave={() => setFocus(null)}>
                      <td className="left">
                        <span className="si-cur">
                          <i style={{ background: CURRENCY_COLORS[s.currency] }} />
                          <CurrencyFlag code={s.currency} size={18} />
                          <strong>{s.currency}</strong>
                          {s.classification ? (
                            <span className={`si-currency-pill si-currency-pill--${s.classification.tone}`}>
                              {s.classification.label}
                            </span>
                          ) : null}
                        </span>
                      </td>
                      {s.available ? (
                        <>
                          <td className="num strong">{s.current?.toFixed(1)}</td>
                          <td className={`num ${(s.change ?? 0) > 0 ? 'up' : (s.change ?? 0) < 0 ? 'down' : ''}`}>
                            {signed(s.change)}
                          </td>
                          <td className="num">{s.change_pct === null || s.change_pct === undefined ? '—' : `${signed(s.change_pct)}%`}</td>
                          <td className="num" title={s.high_at ? fmtUtc(s.high_at) : undefined}>
                            {s.high?.toFixed(1)}
                          </td>
                          <td className="num" title={s.low_at ? fmtUtc(s.low_at) : undefined}>
                            {s.low?.toFixed(1)}
                          </td>
                          <td className="num">{s.average?.toFixed(1)}</td>
                          <td>{s.trend ? <IntelBadge k={s.trend.key} label={s.trend.label} /> : null}</td>
                          <td>
                            {s.momentum ? (
                              <IntelBadge
                                k={s.momentum.key}
                                label={s.momentum.label}
                                title={
                                  s.momentum.recent !== null
                                    ? `Latest third ${signed(s.momentum.recent)} vs prior ${signed(s.momentum.prior)} points`
                                    : undefined
                                }
                              />
                            ) : null}
                          </td>
                        </>
                      ) : (
                        <td colSpan={8} className="muted">
                          No persisted history in this window
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="mi-card si-intel-card">
            <header className="si-subhead">
              <h3>Reversals &amp; crossovers</h3>
              <p>
                Swings ≥ {data.thresholds.reversal_amplitude} points, rank crossovers and 50-line crosses (gap ≥{' '}
                {data.thresholds.crossover_min_gap}).
              </p>
            </header>
            {events.length ? (
              <ul className="si-events">
                {events.map((e, i) => (
                  <li key={`${e.type}-${e.at}-${i}`} className={`si-event si-event--${e.type.toLowerCase()}`}>
                    <span className="si-event-icon">{EVENT_ICON[e.type]}</span>
                    <div>
                      <strong>{e.detail}</strong>
                      <span>
                        {e.type === 'REVERSAL' ? 'Reversal' : e.type === 'CROSSOVER' ? 'Crossover' : 'Neutral-line cross'} ·{' '}
                        {fmtUtc(e.at)}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState title="No meaningful events" body="No reversals or crossovers met the thresholds in this window." />
            )}
            {data.event_count > data.events.length ? (
              <p className="si-note">Showing the latest {data.events.length} of {data.event_count} events.</p>
            ) : null}
          </section>
        </div>
      ) : null}
    </>
  );
}

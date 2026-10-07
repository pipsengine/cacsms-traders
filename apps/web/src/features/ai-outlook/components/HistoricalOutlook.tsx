import { useMemo, useState } from 'react';
import { ArrowLeftRight, Award, BarChart3, ChartCandlestick, Lightbulb, ListChecks, Star, Target, TrendingDown, TrendingUp } from 'lucide-react';
import { StructureChart, type ChartOverlay } from '../../market-structure/components/StructureChart';
import { InstrumentIcon } from '../../market-scanner/components/InstrumentIcon';
import type { HistoryPayload, HistoryRow, Performance, VCandle } from '../types';
import { LivePill, barLabel, type CandleState } from './OutlookChart';
import { Card, Chip, Kpi, Spark, dayLabel, dirTone, dirWord, pct, px } from './shared';

export const HISTORY_RANGES = [
  { key: '1M', days: 30 },
  { key: '3M', days: 90 },
  { key: '6M', days: 180 },
  { key: '12M', days: 365 },
] as const;
const CONF_BUCKETS: [string, number, number][] = [
  ['<40', 0, 40],
  ['40-50', 40, 50],
  ['50-60', 50, 60],
  ['60-70', 60, 70],
  ['70-80', 70, 80],
  ['>80', 80, 101],
];
const INSIGHT_TABS = ['Outlook Trend', 'Accuracy Analysis', 'Average Range', 'Win/Loss Ratio', 'Insights'] as const;

const outlookTone = (d: string | null) => (d === 'BULLISH' ? 'is-green' : d === 'BEARISH' ? 'is-red' : 'is-blue');
const outlookWord = (d: string | null) => (d === 'RANGE' ? 'Consolidation' : dirWord(d));

function resultCell(r: HistoryRow) {
  const e = r.evaluation;
  if (!e) return <Chip tone="is-amber">Pending</Chip>;
  const mv = e.move_pct ?? 0;
  const word = mv > 0 ? 'Up' : mv < 0 ? 'Down' : 'Flat';
  const tone = e.outcome === 'WIN' ? 'is-green' : e.outcome === 'LOSS' ? 'is-red' : 'is-gray';
  return (
    <Chip tone={tone} title={`${e.scenario_result} scenario · ${e.target1_hit ? 'Objective 1 hit' : 'Objective 1 not reached'}${e.invalidated ? ' · invalidated' : ''}`}>
      {word} {mv > 0 ? '+' : ''}
      {mv.toFixed(2)}%
    </Chip>
  );
}

function Donut({ parts }: { parts: { label: string; value: number; color: string }[] }) {
  const total = parts.reduce((s, p) => s + p.value, 0) || 1;
  let acc = 0;
  const R = 34;
  const C = 2 * Math.PI * R;
  return (
    <svg viewBox="0 0 90 90" width={104} height={104} className="mao-donut">
      <circle cx={45} cy={45} r={R} fill="none" stroke="#edf1f6" strokeWidth={13} />
      {parts.map((p) => {
        const len = (p.value / total) * C;
        const el = <circle key={p.label} cx={45} cy={45} r={R} fill="none" stroke={p.color} strokeWidth={13} strokeDasharray={`${len} ${C - len}`} strokeDashoffset={-acc} transform="rotate(-90 45 45)" />;
        acc += len;
        return el;
      })}
      <text x={45} y={44} textAnchor="middle" className="mao-donut-n">
        {total === 1 && !parts.some((p) => p.value) ? 0 : total}
      </text>
      <text x={45} y={56} textAnchor="middle" className="mao-donut-l">
        Analyses
      </text>
    </svg>
  );
}

function insights(rows: HistoryRow[], perf: Performance) {
  const out: string[] = [];
  const n = rows.filter((r) => r.direction).length;
  if (!n) return ['No published outlooks in this window yet.'];
  const counts = { BULLISH: 0, BEARISH: 0, RANGE: 0 } as Record<string, number>;
  rows.forEach((r) => r.direction && (counts[r.direction] += 1));
  const lead = Object.entries(counts).sort((a, b) => b[1] - a[1])[0];
  out.push(`${outlookWord(lead[0])} outlooks dominate (${((lead[1] / n) * 100).toFixed(1)}%) over the selected window.`);
  if (perf.avg_confidence != null) out.push(`Average published confidence is ${perf.avg_confidence.toFixed(1)}%${perf.direction_accuracy != null ? ` against a realised next-day direction accuracy of ${perf.direction_accuracy.toFixed(1)}%` : ''}.`);
  const best = Object.entries(perf.by_direction).filter(([, v]) => v.accuracy != null).sort((a, b) => (b[1].accuracy ?? 0) - (a[1].accuracy ?? 0))[0];
  if (best) out.push(`Highest accuracy on ${outlookWord(best[0]).toLowerCase()} calls (${best[1].accuracy}% of ${best[1].wins + best[1].losses} decided).`);
  if (perf.target1_rate != null) out.push(`Objective 1 reached on ${perf.target1_rate}% of directional outlooks; invalidated on ${perf.invalidation_rate}%.`);
  const over = perf.buckets.filter((b) => b.n >= 3 && b.hit_rate != null && b.hit_rate < b.expected - 10);
  if (over.length) out.push(`Over-confidence detected in the ${over.map((b) => b.bucket).join(', ')} bucket(s) — calibration is shrinking those probabilities.`);
  if (perf.false_positives) out.push(`${perf.false_positives} qualified outlook(s) were wrong (false positives); ${perf.false_negatives} unqualified outlook(s) reached Objective 1 (false negatives).`);
  const latest = rows.find((r) => r.direction) ?? rows[0];
  out.push(`Latest outlook (${dayLabel(latest.analysis_date)}) is ${outlookWord(latest.direction).toLowerCase()} at ${pct(latest.confidence)} — ${latest.regime_label?.toLowerCase() ?? 'regime n/a'}.`);
  return out;
}

export function HistoricalOutlook({
  symbol,
  digits,
  data,
  loading,
  error,
  days,
  onDays,
  candles,
  chartHeight,
}: {
  symbol: string;
  digits: number;
  data: HistoryPayload | null;
  loading: boolean;
  error: string | null;
  days: number;
  onDays: (d: number) => void;
  candles: CandleState;
  chartHeight: number;
}) {
  const [itab, setItab] = useState<(typeof INSIGHT_TABS)[number]>('Outlook Trend');
  const rows = useMemo(() => data?.rows ?? [], [data]);
  const perf = data?.performance.all;
  const n = rows.filter((r) => r.direction).length;
  const skipped = rows.length - n;
  const count = (d: string) => rows.filter((r) => r.direction === d).length;
  const evaluated = rows.filter((r) => r.evaluation);

  const overlay = useMemo<ChartOverlay>(() => {
    const ov: ChartOverlay = { markers: [], tags: [] };
    const ordered = [...rows].reverse().filter((r) => r.price != null && r.direction);
    const step = Math.max(2, Math.ceil(ordered.length / 4));
    ordered.forEach((r, i) => {
      const at = `${r.analysis_date}T12:00:00+00:00`;
      const tone = r.direction === 'BULLISH' ? 'green' : r.direction === 'BEARISH' ? 'red' : 'blue';
      ov.markers!.push({ at, price: r.price!, shape: r.direction === 'BULLISH' ? 'up' : r.direction === 'BEARISH' ? 'down' : 'dot', tone, muted: r.origin === 'REPLAY' && !r.evaluation });
      if ((ordered.length - 1 - i) % step === 0 && r.targets?.length) {
        const mv = r.evaluation?.move_pct;
        ov.tags!.push({
          at,
          price: r.direction === 'BEARISH' ? Math.min(r.price ?? 0, r.targets[0].price) : Math.max(r.price ?? 0, r.targets[0].price),
          title: `${outlookWord(r.direction)} ${dayLabel(r.analysis_date, { day: '2-digit', month: 'short' })}`,
          value: `${px(r.price, digits)} → ${px(r.targets[0].price, digits)}${mv != null ? ` ${mv > 0 ? '+' : ''}${mv.toFixed(1)}%` : ' (next)'}`,
          tone: r.direction === 'BULLISH' ? 'sup' : r.direction === 'BEARISH' ? 'res' : 'blue',
          place: r.direction === 'BEARISH' ? 'below' : 'above',
        });
      }
    });
    return ov;
  }, [rows, digits]);

  const closesAround = (date: string, all: VCandle[]) => {
    const i = all.findIndex((c) => c.t.slice(0, 10) >= date);
    const end = i < 0 ? all.length : Math.min(all.length, i + 2);
    return all.slice(Math.max(0, end - 9), end).map((c) => c.c);
  };

  if (!data) {
    return (
      <section className={`mao-card mst-blocking ${error ? 'is-error' : ''}`}>
        {error ? (
          <>
            <strong>Historical outlooks unavailable</strong>
            <span>{error}</span>
          </>
        ) : (
          <>
            <span className="mst-spinner" aria-hidden /> {loading ? 'Loading immutable outlook history…' : 'No history'}
          </>
        )}
      </section>
    );
  }

  const conf = CONF_BUCKETS.map(([bucket, lo, hi]) => {
    const inBucket = rows.filter((r) => r.confidence != null && r.confidence >= lo && r.confidence < hi);
    const decided = inBucket.filter((r) => r.evaluation?.outcome === 'WIN' || r.evaluation?.outcome === 'LOSS');
    return { bucket, n: inBucket.length, hit_rate: decided.length ? (decided.filter((r) => r.evaluation?.outcome === 'WIN').length / decided.length) * 100 : null };
  });
  const confMax = Math.max(1, ...conf.map((b) => b.n));
  const ins = perf ? insights(rows, perf) : [];

  return (
    <>
      <div className="mao-kpis is-six">
        <Kpi icon={<BarChart3 size={18} />} tone="is-purple" label="Total Analyses" value={n} sub={`Published outlooks (last ${days} days)${skipped ? ` · ${skipped} insufficient data` : ''}`} />
        <Kpi icon={<TrendingUp size={18} />} tone="is-bull" label="Bullish Outlook" value={<>{count('BULLISH')} <small>({n ? ((count('BULLISH') / n) * 100).toFixed(1) : '0'}%)</small></>} bar={n ? (count('BULLISH') / n) * 100 : 0} />
        <Kpi icon={<TrendingDown size={18} />} tone="is-bear" label="Bearish Outlook" value={<>{count('BEARISH')} <small>({n ? ((count('BEARISH') / n) * 100).toFixed(1) : '0'}%)</small></>} bar={n ? (count('BEARISH') / n) * 100 : 0} />
        <Kpi icon={<ArrowLeftRight size={18} />} tone="is-blue" label="Consolidation" value={<>{count('RANGE')} <small>({n ? ((count('RANGE') / n) * 100).toFixed(1) : '0'}%)</small></>} bar={n ? (count('RANGE') / n) * 100 : 0} />
        <Kpi icon={<Star size={18} />} tone="is-amber" label="Average Confidence" value={pct(perf?.avg_confidence, 1)} sub="Across all analysed days" />
        <Kpi icon={<Target size={18} />} tone="is-blue" label="Accuracy Rate" value={pct(perf?.direction_accuracy, 1)} sub={`Based on next day direction (${evaluated.length} evaluated)`} />
      </div>

      <div className="mao-main is-wide-side">
        <div className="mao-chart-wrap">
          <StructureChart
            key={days}
            zoomable
            defaultSpan={Math.round((days * 5) / 7) + 6}
            symbol={symbol}
            title={`Historical Daily Outlook (Last ${days} Days)`}
            tf="D1"
            candles={candles.candles}
            digits={digits}
            lastPrice={candles.price ?? candles.candles.at(-1)?.c ?? null}
            barLabel={barLabel(candles)}
            height={chartHeight}
            loading={candles.loading}
            error={candles.error ?? undefined}
            overlay={overlay}
            className="mao-chart"
            heading={
              <strong>
                <InstrumentIcon base={symbol.slice(0, 3)} quote={symbol.slice(3, 6)} size="sm" /> {symbol} – Historical Daily Outlook (Last {days} Days) <LivePill live={candles.live} />
              </strong>
            }
            actions={<span className="mst-tf-badge">D1</span>}
            legend={[
              { label: 'Bullish outlook', swatch: 'is-fl' },
              { label: 'Bearish outlook', swatch: 'is-fh' },
              { label: 'Consolidation', swatch: 'is-rt' },
            ]}
          />
          <div className="mao-ranges">
            {HISTORY_RANGES.map((r) => (
              <button key={r.key} className={days === r.days ? 'is-on' : ''} onClick={() => onDays(r.days)}>
                {r.key}
              </button>
            ))}
          </div>
        </div>
        <Card
          title="Historical Analysis List"
          icon={<ListChecks size={15} />}
          extra={
            <select className="mao-select" value={days} onChange={(e) => onDays(Number(e.target.value))} aria-label="History window">
              {HISTORY_RANGES.map((r) => (
                <option key={r.days} value={r.days}>
                  Last {r.days} Days
                </option>
              ))}
            </select>
          }
        >
          <div className="mao-scroll">
            <table className="mao-table is-compact">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Outlook</th>
                  <th>Confidence</th>
                  <th>Key Notes</th>
                  <th>Result (Next Day)</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.outlook_id} title={`Snapshot ${r.snapshot_id} · ${r.engine_version}${r.origin === 'REPLAY' ? ' · walk-forward replay (frozen bars as of that close)' : ''}`}>
                    <td>
                      {dayLabel(r.analysis_date)}
                      {r.origin === 'REPLAY' ? <small className="mao-replay">Replay</small> : null}
                    </td>
                    <td>
                      <Chip tone={outlookTone(r.direction)}>{r.status === 'PUBLISHED' ? outlookWord(r.direction) : 'No data'}</Chip>
                    </td>
                    <td className="num">{pct(r.confidence)}</td>
                    <td className="mao-notes">{r.status === 'PUBLISHED' ? `${r.expected_next_move?.label ?? ''} · ${r.regime_label ?? ''}` : r.reason}</td>
                    <td>{r.status === 'PUBLISHED' ? resultCell(r) : '—'}</td>
                  </tr>
                ))}
                {!rows.length ? (
                  <tr>
                    <td colSpan={5} className="mao-muted center">
                      No published outlooks for {symbol} in this window.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      <div className="mao-row2">
        <Card title="Past Analyses (Last 10 Days)" icon={<ChartCandlestick size={15} />}>
          <table className="mao-table is-compact">
            <thead>
              <tr>
                <th>Date</th>
                <th>Chart Snapshot</th>
                <th>Outlook</th>
                <th>Confidence</th>
                <th>Predicted Range</th>
                <th>Actual Move</th>
                <th>Result</th>
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 10).map((r) => (
                <tr key={r.outlook_id}>
                  <td>{dayLabel(r.analysis_date)}</td>
                  <td>
                    <Spark values={closesAround(r.analysis_date, candles.candles)} tone={dirTone(r.direction)} />
                  </td>
                  <td>
                    <Chip tone={outlookTone(r.direction)}>{outlookWord(r.direction)}</Chip>
                  </td>
                  <td className="num">{pct(r.confidence)}</td>
                  <td className="num">{r.targets?.length ? `${px(r.direction === 'RANGE' ? r.invalidation?.price : r.erz?.mid, digits)} – ${px(r.targets[0].price, digits)}` : '—'}</td>
                  <td className="num">{r.evaluation ? `${px(r.evaluation.low, digits)} → ${px(r.evaluation.high, digits)}` : <Chip tone="is-amber">Pending</Chip>}</td>
                  <td>{r.evaluation ? resultCell(r) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
        <Card title="Key Observations & Insights" icon={<Lightbulb size={15} />}>
          <div className="mao-subtabs" role="tablist">
            {INSIGHT_TABS.map((t) => (
              <button key={t} role="tab" aria-selected={itab === t} className={itab === t ? 'is-on' : ''} onClick={() => setItab(t)}>
                {t}
              </button>
            ))}
          </div>
          {perf ? (
            <div className="mao-insight-body">
              {itab === 'Outlook Trend' ? (
                <div className="mao-trend">
                  <div>
                    <h4>Outlook Distribution (Last {days} Days)</h4>
                    <div className="mao-dist">
                      <Donut
                        parts={[
                          { label: 'Bullish', value: count('BULLISH'), color: '#12b76a' },
                          { label: 'Bearish', value: count('BEARISH'), color: '#f04438' },
                          { label: 'Consolidation', value: count('RANGE'), color: '#2e6cf6' },
                        ]}
                      />
                      <ul>
                        {[
                          ['Bullish', 'BULLISH', 'is-green'],
                          ['Bearish', 'BEARISH', 'is-red'],
                          ['Consolidation', 'RANGE', 'is-blue'],
                        ].map(([l, k, t]) => (
                          <li key={k}>
                            <i className={t} /> {l} <b>{count(k)}</b> <small>({n ? ((count(k) / n) * 100).toFixed(1) : '0'}%)</small>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                  <div>
                    <h4>Confidence Distribution</h4>
                    <div className="mao-bars">
                      {conf.map((b) => (
                        <div key={b.bucket} title={`${b.n} outlooks · hit rate ${pct(b.hit_rate)}`}>
                          <b>{b.n}</b>
                          <i style={{ height: `${(b.n / confMax) * 64 + 2}px` }} />
                          <small>{b.bucket}</small>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              ) : itab === 'Accuracy Analysis' ? (
                <table className="mao-table is-compact">
                  <thead>
                    <tr>
                      <th>Confidence bucket</th>
                      <th className="num">Outlooks</th>
                      <th className="num">Hit rate</th>
                      <th className="num">Expected</th>
                      <th>Calibration</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(perf?.buckets ?? []).map((b) => (
                      <tr key={b.bucket}>
                        <td>{b.bucket}</td>
                        <td className="num">{b.n}</td>
                        <td className="num">{pct(b.hit_rate, 1)}</td>
                        <td className="num">{b.expected}%</td>
                        <td>{b.hit_rate == null ? <span className="mao-muted">No samples</span> : <Chip tone={Math.abs(b.hit_rate - b.expected) <= 10 ? 'is-green' : b.hit_rate < b.expected ? 'is-red' : 'is-blue'}>{Math.abs(b.hit_rate - b.expected) <= 10 ? 'Calibrated' : b.hit_rate < b.expected ? 'Over-confident' : 'Under-confident'}</Chip>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : itab === 'Average Range' ? (
                <div className="mao-statgrid">
                  {[
                    ['Avg next-day move', evaluated.length ? `${(evaluated.reduce((s, r) => s + Math.abs(r.evaluation!.move_pct ?? 0), 0) / evaluated.length).toFixed(2)}%` : '—'],
                    ['Avg move (ATR)', evaluated.length ? `${(evaluated.reduce((s, r) => s + Math.abs(r.evaluation!.move_atr ?? 0), 0) / evaluated.length).toFixed(2)}` : '—'],
                    ['Objective 1 hit', pct(perf.target1_rate, 1)],
                    ['Objective 2 hit', pct(perf.target2_rate, 1)],
                    ['ERZ touched', pct(perf.erz_touch_rate, 1)],
                    ['Invalidated', pct(perf.invalidation_rate, 1)],
                  ].map(([l, v]) => (
                    <div key={l}>
                      <small>{l}</small>
                      <b>{v}</b>
                    </div>
                  ))}
                </div>
              ) : itab === 'Win/Loss Ratio' ? (
                <table className="mao-table is-compact">
                  <thead>
                    <tr>
                      <th>Outlook</th>
                      <th className="num">Outlooks</th>
                      <th className="num">Wins</th>
                      <th className="num">Losses</th>
                      <th className="num">Accuracy</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(perf.by_direction).map(([k, v]) => (
                      <tr key={k}>
                        <td>
                          <Chip tone={outlookTone(k)}>{outlookWord(k)}</Chip>
                        </td>
                        <td className="num">{v.n}</td>
                        <td className="num is-bull">{v.wins}</td>
                        <td className="num is-bear">{v.losses}</td>
                        <td className="num">{pct(v.accuracy, 1)}</td>
                      </tr>
                    ))}
                    <tr>
                      <td colSpan={5}>
                        <small>
                          Scenario realised: {Object.entries(perf.by_scenario).map(([k, v]) => `${k.toLowerCase()} ${v}`).join(' · ') || '—'} · Brier {perf.brier ?? '—'}
                        </small>
                      </td>
                    </tr>
                  </tbody>
                </table>
              ) : null}
            </div>
          ) : null}
          <div className="mao-insights">
            <h4>
              <Award size={14} /> Insights
            </h4>
            <ul>
              {ins.map((t) => (
                <li key={t}>{t}</li>
              ))}
            </ul>
          </div>
        </Card>
      </div>
    </>
  );
}

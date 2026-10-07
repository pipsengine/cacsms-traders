import { useMemo, useState } from 'react';
import {
  Activity,
  BadgeCheck,
  BarChart3,
  ClipboardList,
  Crosshair,
  History,
  Layers,
  Lightbulb,
  Radar,
  Repeat2,
  Rocket,
  Sparkles,
  Workflow,
  XOctagon,
} from 'lucide-react';
import { InstrumentIcon } from '../../market-scanner/components/InstrumentIcon';
import { fmtPrice } from '../../market-scanner/format';
import { StructureChart, type ChartOverlay } from '../../market-structure/components/StructureChart';
import { Kpi, Kv, Lifecycle, Panel, Pill, TfSwitch, eventTime, rowDigits, statusTone } from '../../market-structure/components/StructureUi';
import type { VCandle } from '../../market-structure/types';
import type { BreakoutDetail, BreakoutRow, ChannelPayload, EventTf } from '../types';
import { dirTone, signed } from './shared';

export const BREAKOUT_TFS: EventTf[] = ['W', 'D1', 'H8', 'H1'];

function Kpis({ counts }: { counts: ChannelPayload['counts'] }) {
  return (
    <div className="mtr-kpis">
      <Kpi tone="is-blue" icon={<Activity size={20} />} label="Total Channel Events" value={counts.events_7d} sub={`${counts.events_24h} in last 24h · W / D1 / H8 / H1`} />
      <Kpi tone="is-purple" icon={<Rocket size={20} />} label="Breakout Events" value={counts.breakouts_7d} sub="Last 7 days" />
      <Kpi tone="is-amber" icon={<Repeat2 size={20} />} label="Retest in Progress" value={counts.retest_in_progress} sub="Price at broken boundary" />
      <Kpi tone="is-green" icon={<BadgeCheck size={21} />} label="Confirmed" value={counts.confirmed} sub="Held beyond boundary (7d)" />
      <Kpi tone="is-red" icon={<XOctagon size={20} />} label="Failed" value={counts.failed} sub="Closed back inside (7d)" />
      <Kpi tone="is-rose" icon={<Sparkles size={20} />} label="High-Probability Setups" value={counts.high_probability} sub="Confirmed, near retest level" />
    </div>
  );
}

function EventsTable({
  rows,
  selected,
  onPick,
}: {
  rows: BreakoutRow[];
  selected: string | null;
  onPick: (r: BreakoutRow) => void;
}) {
  const [asset, setAsset] = useState('ALL');
  const [tf, setTf] = useState('ALL');
  const [status, setStatus] = useState('ALL');
  const list = useMemo(
    () => rows.filter((r) => (asset === 'ALL' || r.asset === asset) && (tf === 'ALL' || r.tf === tf) && (status === 'ALL' || r.status.key === status)),
    [rows, asset, tf, status],
  );
  return (
    <section className="mst-card mst-panel mtr-matrix">
      <header className="mtr-panel-head">
        <h3>
          <History size={14} /> Recent Breakout & Retest Events <small>({list.length})</small>
        </h3>
        <div className="mtr-tools">
          <select value={asset} onChange={(e) => setAsset(e.target.value)} aria-label="Asset class">
            <option value="ALL">All Assets</option>
            <option value="Forex">Forex</option>
            <option value="Commodity">Commodity</option>
          </select>
          <select value={tf} onChange={(e) => setTf(e.target.value)} aria-label="Timeframe">
            <option value="ALL">All Timeframes</option>
            {BREAKOUT_TFS.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
            <option value="ALL">All Status</option>
            {(
              [
                ['CONFIRMED', 'Confirmed'],
                ['RETESTING', 'Retesting'],
                ['TESTING', 'Testing'],
                ['DEVELOPING', 'Developing'],
                ['INSIDE', 'Back Inside'],
                ['FAILED', 'Failed'],
              ] as const
            ).map(([k, label]) => (
              <option key={k} value={k}>
                {label}
              </option>
            ))}
          </select>
        </div>
      </header>
      <div className="mtr-scroll">
        <table className="mtr-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Symbol</th>
              <th className="center">TF</th>
              <th>Event</th>
              <th className="num">Level</th>
              <th className="num">Retest Level</th>
              <th className="num">Result</th>
              <th className="center">Retest</th>
              <th className="center">Status</th>
            </tr>
          </thead>
          <tbody>
            {list.map((r, i) => {
              const d = rowDigits(r);
              const key = `${r.symbol}|${r.tf}|${r.at}`;
              return (
                <tr
                  key={`${key}-${i}`}
                  className={selected === key ? 'is-selected' : ''}
                  onClick={() => onPick(r)}
                  tabIndex={0}
                  onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && onPick(r)}
                  aria-selected={selected === key}
                >
                  <td className="mtr-muted" title={new Date(r.at).toUTCString()}>
                    {eventTime(r.at, r.tf)}
                  </td>
                  <td>
                    <span className="mtr-symcell">
                      <InstrumentIcon base={r.base} quote={r.quote} size="sm" />
                      <b>{r.symbol}</b>
                    </span>
                  </td>
                  <td className="center mtr-muted">{r.tf}</td>
                  <td className={r.direction === 'UP' ? 'up' : 'down'}>{r.label}</td>
                  <td className="num">{fmtPrice(r.level, d)}</td>
                  <td className="num">{fmtPrice(r.retest_now, d)}</td>
                  <td className={`num ${r.result_pips != null && r.result_pips >= 0 ? 'up' : 'down'}`}>{signed(r.result_pips, 1, ' pips')}</td>
                  <td className="center">
                    <Pill tone={statusTone(r.retest.key)}>{r.retest.label}</Pill>
                  </td>
                  <td className="center">
                    <Pill tone={statusTone(r.status.key)}>{r.status.label}</Pill>
                  </td>
                </tr>
              );
            })}
            {!list.length ? (
              <tr>
                <td colSpan={9} className="mtr-empty">
                  No channel breakouts match the selected filters
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function CandidatesPanel({ data, onPick }: { data: ChannelPayload; onPick: (s: string, tf: EventTf) => void }) {
  return (
    <Panel title="Breakout Setup Candidates" icon={<Radar size={14} />} extra={<small className="mtr-muted">Price approaching a boundary</small>}>
      <div className="mtr-scroll is-events mci-short">
        <table className="mtr-table is-compact">
          <thead>
            <tr>
              <th>Symbol</th>
              <th className="center">TF</th>
              <th>State</th>
              <th className="num">Distance</th>
              <th>Expected</th>
              <th className="center">Quality</th>
            </tr>
          </thead>
          <tbody>
            {data.candidates.map((c, i) => (
              <tr key={`${c.symbol}-${c.tf}-${i}`} className="is-click" onClick={() => onPick(c.symbol, c.tf)}>
                <td>
                  <span className="mtr-symcell">
                    <InstrumentIcon base={c.base} quote={c.quote} size="sm" />
                    <b>{c.symbol}</b>
                  </span>
                </td>
                <td className="center mtr-muted">{c.tf}</td>
                <td>
                  {c.state} <small className="mtr-muted">{c.boundary === 'UPPER' ? 'upper' : 'lower'}</small>
                </td>
                <td className="num">{c.distance_atr != null ? `${c.distance_atr.toFixed(2)} ATR` : '—'}</td>
                <td className={c.expected === 'Breakout' ? (c.boundary === 'UPPER' ? 'up' : 'down') : 'amber'}>{c.expected}</td>
                <td className="center">
                  <Pill tone={c.quality.key === 'HIGH' ? 'is-green' : c.quality.key === 'MEDIUM' ? 'is-amber' : 'is-gray'}>{c.quality.label}</Pill>
                </td>
              </tr>
            ))}
            {!data.candidates.length ? (
              <tr>
                <td colSpan={6} className="mtr-empty">
                  No channel boundary is being approached
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function RetestsPanel({ data, onPick }: { data: ChannelPayload; onPick: (s: string, tf: EventTf) => void }) {
  return (
    <Panel title="Retest Monitoring" icon={<Crosshair size={14} />}>
      <div className="mtr-scroll is-events mci-short">
        <table className="mtr-table is-compact">
          <thead>
            <tr>
              <th>Symbol</th>
              <th className="center">TF</th>
              <th className="num">Retest Level</th>
              <th className="num">Distance</th>
              <th className="center">Status</th>
            </tr>
          </thead>
          <tbody>
            {data.retests.map((r, i) => (
              <tr key={`${r.symbol}-${r.tf}-${r.at}-${i}`} className="is-click" onClick={() => onPick(r.symbol, r.tf)}>
                <td>
                  <span className="mtr-symcell">
                    <InstrumentIcon base={r.base} quote={r.quote} size="sm" />
                    <b>{r.symbol}</b>
                  </span>
                </td>
                <td className="center mtr-muted">{r.tf}</td>
                <td className="num">{fmtPrice(r.retest_now, rowDigits(r))}</td>
                <td className="num">{r.distance_atr != null ? `${r.distance_atr.toFixed(2)} ATR` : '—'}</td>
                <td className="center">
                  <Pill tone={statusTone(r.retest.key)}>{r.retest.key === 'PENDING' ? 'Awaiting' : r.retest.label}</Pill>
                </td>
              </tr>
            ))}
            {!data.retests.length ? (
              <tr>
                <td colSpan={5} className="mtr-empty">
                  No confirmed breakout awaiting a retest
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function StatsPanel({ stats }: { stats: ChannelPayload['stats'] }) {
  const bull = stats.total ? Math.round((stats.bullish / stats.total) * 100) : 0;
  const r = 34;
  const circ = 2 * Math.PI * r;
  const rate = stats.success_rate ?? 0;
  return (
    <Panel title="Breakout Statistics" icon={<BarChart3 size={14} />} extra={<small className="mtr-muted">Last {stats.total} breakouts</small>}>
      <div className="mci-bstats">
        <div className="mci-donut">
          <svg width={86} height={86} viewBox="0 0 86 86" aria-hidden>
            <circle cx={43} cy={43} r={r} className="mci-donut-bg" />
            <circle cx={43} cy={43} r={r} className="mci-donut-fg" strokeDasharray={`${(rate / 100) * circ} ${circ}`} transform="rotate(-90 43 43)" />
          </svg>
          <div>
            <b>{stats.success_rate != null ? `${stats.success_rate}%` : '—'}</b>
            <small>Success</small>
          </div>
        </div>
        <dl className="mtr-kv is-tight">
          <Kv label="Confirmed" tone="up">
            {stats.confirmed}
          </Kv>
          <Kv label="Failed" tone="down">
            {stats.failed}
          </Kv>
          <Kv label="Retest Pending">{stats.retest_pending}</Kv>
          <Kv label="Retest in Progress">{stats.retest_in_progress}</Kv>
          <Kv label="Avg Follow-through">{stats.avg_move_atr != null ? `${stats.avg_move_atr.toFixed(1)} ATR` : '—'}</Kv>
        </dl>
      </div>
      <div className="mci-split" title={`${stats.bullish} bullish / ${stats.bearish} bearish`}>
        <span className="is-up" style={{ width: `${bull}%` }}>
          {bull ? `Bullish ${bull}%` : ''}
        </span>
        <span className="is-down" style={{ width: `${100 - bull}%` }}>
          {100 - bull ? `Bearish ${100 - bull}%` : ''}
        </span>
      </div>
    </Panel>
  );
}

function breakoutOverlay(b: Extract<BreakoutDetail, { available: true }>, digits: number): ChartOverlay {
  const up = b.event.direction === 'UP';
  const edge = up ? b.lines.upper : b.lines.lower;
  const markers: NonNullable<ChartOverlay['markers']> = [
    { at: b.marks.breakout.at, price: b.marks.breakout.price, shape: up ? 'up' : 'down', tone: 'blue', label: 'Breakout' },
  ];
  if (b.marks.retest) markers.push({ at: b.marks.retest.at, price: b.marks.retest.price, shape: 'dot', tone: 'amber', label: 'Retest' });
  if (b.marks.continuation) markers.push({ at: b.marks.continuation.at, price: b.marks.continuation.price, shape: 'diamond', tone: 'green', label: 'Continuation' });
  return {
    bands: [{ upper: b.lines.upper, lower: b.lines.lower, tone: 'blue' }],
    lines: [
      { from: b.lines.upper[0], to: b.lines.upper[1], tone: 'blue', dashed: up ? false : true },
      { from: b.lines.lower[0], to: b.lines.lower[1], tone: 'blue', dashed: up ? true : false },
      { from: b.lines.mid[0], to: b.lines.mid[1], tone: 'blue', dashed: true, width: 1 },
    ],
    levels: [{ price: b.details.next_objective, tone: 'green', label: `Next channel objective ${fmtPrice(b.details.next_objective, digits)}`, from: b.marks.breakout.at }],
    markers,
    tags: [{ price: edge[1][1], title: up ? 'Channel Resistance' : 'Channel Support', value: fmtPrice(edge[1][1], digits), tone: up ? 'res' : 'sup', place: up ? 'below' : 'above' }],
  };
}

function DetailPanel({ b, digits }: { b: Extract<BreakoutDetail, { available: true }>; digits: number }) {
  const x = b.details;
  return (
    <Panel title="Event Detail" icon={<ClipboardList size={14} />} extra={<Pill tone={statusTone(b.event.status.key)}>{b.event.status.label}</Pill>}>
      <dl className="mtr-kv is-tight">
        <Kv label="Event Type" tone={b.event.direction === 'UP' ? 'up' : 'down'}>
          {x.type}
        </Kv>
        <Kv label="Breakout Level">{fmtPrice(x.level, digits)}</Kv>
        <Kv label="Break Candle">{eventTime(x.break_candle, b.tf)}</Kv>
        <Kv label="Close">{x.close_side} channel</Kv>
        <Kv label="Body Acceptance" tone={x.body_acceptance ? 'up' : 'down'}>
          {x.body_acceptance ? 'Yes' : 'No'}
        </Kv>
        <Kv label="Retest Level">{fmtPrice(x.retest_level, digits)}</Kv>
        <Kv label="Retest">
          <Pill tone={statusTone(x.retest.key)}>{x.retest.label}</Pill>
        </Kv>
        <Kv label="Follow-through">
          {x.follow_through_atr != null ? `${x.follow_through_atr.toFixed(2)} ATR` : '—'} <small>({x.follow_through_pips} pips)</small>
        </Kv>
        <Kv label="Valid Structure" tone={x.valid_structure ? 'up' : undefined}>
          {x.valid_structure ? 'Yes' : 'No'} <small>({x.valid_note})</small>
        </Kv>
        <Kv label="Next Objective" tone="up">
          {fmtPrice(x.next_objective, digits)}
        </Kv>
        <Kv label="Invalidation" tone="down">
          {fmtPrice(x.invalidation, digits)}
        </Kv>
      </dl>
    </Panel>
  );
}

export function BreakoutRetest({
  data,
  symbol,
  breakout,
  digits,
  tf,
  onTf,
  onSelect,
  candles,
  chartHeight,
  price,
}: {
  data: ChannelPayload;
  symbol: string;
  breakout: BreakoutDetail | null;
  digits: number;
  tf: EventTf;
  onTf: (tf: EventTf) => void;
  onSelect: (s: string) => void;
  candles: { candles: VCandle[]; loading: boolean; error: string };
  chartHeight: number;
  price: number | null | undefined;
}) {
  const [picked, setPicked] = useState<string | null>(null);
  const b = breakout?.available && breakout.tf === tf ? breakout : null;
  const overlay = useMemo(() => (b ? breakoutOverlay(b, digits) : null), [b, digits]);
  const pick = (s: string, t: EventTf) => {
    onSelect(s);
    onTf(t);
  };
  return (
    <>
      <Kpis counts={data.counts} />
      <div className={`mtr-row2 ${data.meta.stale ? 'is-stale' : ''}`}>
        <EventsTable
          rows={data.breakouts}
          selected={picked}
          onPick={(r) => {
            setPicked(`${r.symbol}|${r.tf}|${r.at}`);
            pick(r.symbol, r.tf);
          }}
        />
        <div className="mtr-chart">
          <StructureChart
            symbol={symbol}
            title="Breakout & Retest"
            tf={tf}
            candles={candles.candles}
            loading={candles.loading}
            error={candles.error}
            digits={digits}
            lastPrice={price}
            overlay={overlay}
            height={chartHeight}
            heading={
              <strong className="mtr-chart-title">
                <InstrumentIcon base={symbol.slice(0, 3)} quote={symbol.slice(3, 6)} size="sm" /> {symbol} – Breakout & Retest
                {b ? <span className={`mtr-state-pill ${dirTone(b.event.direction === 'UP' ? 'UPTREND' : 'DOWNTREND')}`}>{b.event.label.toUpperCase()}</span> : null}
              </strong>
            }
            actions={<TfSwitch tfs={BREAKOUT_TFS} value={tf} onChange={onTf} label="Breakout chart timeframe" />}
            legend={[
              { label: 'Channel (frozen at break)', swatch: 'is-chan' },
              { label: 'Breakout', swatch: 'is-bk' },
              { label: 'Retest', swatch: 'is-rt' },
              { label: 'Continuation', swatch: 'is-ct' },
            ]}
          />
        </div>
      </div>
      <div className="mci-row3">
        <CandidatesPanel data={data} onPick={pick} />
        <RetestsPanel data={data} onPick={pick} />
        <StatsPanel stats={data.stats} />
      </div>
      {b ? (
        <div className="mci-row4b">
          <DetailPanel b={b} digits={digits} />
          <Panel title="Event Lifecycle" icon={<Workflow size={14} />}>
            <Lifecycle steps={b.lifecycle} />
          </Panel>
          <Panel title="Related Structure (Multi-TF)" icon={<Layers size={14} />}>
            <table className="mtr-mini">
              <tbody>
                {b.related.map((r) => (
                  <tr key={r.tf} className={r.tf === tf ? 'is-on' : ''}>
                    <td>{r.tf}</td>
                    <td>
                      <span className={`mtr-regime ${r.direction.key === 'UPTREND' ? 'is-bull' : r.direction.key === 'DOWNTREND' ? 'is-bear' : 'is-range'}`}>{r.direction.label}</span>
                    </td>
                    <td className="mtr-swings">{r.state.label}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>
          <Panel title="Key Takeaway" icon={<Lightbulb size={14} />} className="mci-takeaway">
            <p>{b.takeaway}</p>
            <small className="mtr-foot">Structural analysis on closed bars · not a trade instruction</small>
          </Panel>
        </div>
      ) : (
        <section className="mst-card mst-blocking">
          <strong>
            {symbol} · {tf}
          </strong>
          <span>{breakout && !breakout.available ? breakout.reason : 'Loading breakout detail…'}</span>
        </section>
      )}
    </>
  );
}

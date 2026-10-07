import { useMemo } from 'react';
import { ArrowDownRight, ArrowLeftRight, ArrowUpRight, BarChart3, ClipboardList, Compass, Gauge, History, Layers, MoveVertical, Ruler, Target } from 'lucide-react';
import { InstrumentIcon } from '../../market-scanner/components/InstrumentIcon';
import { fmtPrice } from '../../market-scanner/format';
import { StructureChart } from '../../market-structure/components/StructureChart';
import { Kpi, Kv, Panel, Pill, eventTime } from '../../market-structure/components/StructureUi';
import type { VCandle } from '../../market-structure/types';
import type { ChannelDetail, ChannelTf, ChannelView, LiveChannelView, Spark } from '../types';
import { CHANNEL_TFS, TF_NAMES, channelOverlay, dirTone, kpiTone, signed } from './shared';

type Live = Extract<ChannelDetail, { available: true }>;

const dirIcon = (k: string, size = 20) =>
  k === 'UPTREND' ? <ArrowUpRight size={size} /> : k === 'DOWNTREND' ? <ArrowDownRight size={size} /> : <ArrowLeftRight size={size} />;

const stateTone = (k: string) => (k.startsWith('BREAKOUT') ? 'is-red' : k.startsWith('TESTING') ? 'is-amber' : 'is-green');

function Kpis({ d }: { d: Live }) {
  const v = d.view;
  return (
    <div className="mci-kpis5">
      <Kpi tone={kpiTone(v.direction.key)} icon={dirIcon(v.direction.key, 22)} label="Channel Direction" value={v.direction.label.toUpperCase()} sub={`Slope: ${v.slope_strength}`} />
      <Kpi
        tone="is-blue"
        icon={<MoveVertical size={20} />}
        label="Price Position"
        value={v.position != null ? `${v.position.toFixed(0)}%` : '—'}
        bar={v.position}
        sub={v.half ?? undefined}
      />
      <Kpi
        tone="is-purple"
        icon={<Ruler size={20} />}
        label="Channel Width (ATR)"
        value={v.width_atr != null ? `${v.width_atr.toFixed(1)}×` : '—'}
        sub={`${v.width_trend.charAt(0)}${v.width_trend.slice(1).toLowerCase()} · ${v.period} bars`}
      />
      <Kpi tone={stateTone(v.state.key) as 'is-green'} icon={<Gauge size={20} />} label="Channel State" value={v.state.label.toUpperCase()} sub={v.validity.label} />
      <Kpi
        tone="is-blue"
        icon={<Layers size={20} />}
        label="Multi-TF Alignment"
        value={
          <>
            {d.alignment.aligned}
            <small> / {d.alignment.total}</small>
          </>
        }
        bar={d.alignment.total ? (d.alignment.aligned / d.alignment.total) * 100 : 0}
        sub={`Timeframes ${d.alignment.direction ? d.alignment.direction.toLowerCase() : 'aligned'}`}
      />
    </div>
  );
}

function DetailsPanel({ d, digits }: { d: Live; digits: number }) {
  const v = d.view;
  return (
    <Panel title="Channel Details" icon={<ClipboardList size={14} />} extra={<span className="mst-tf-badge">{TF_NAMES[d.tf]}</span>}>
      <dl className="mtr-kv is-tight">
        <Kv label="Direction" tone={dirTone(v.direction.key) === 'is-up' ? 'up' : dirTone(v.direction.key) === 'is-down' ? 'down' : 'amber'}>
          {v.direction.label} <small>({v.slope_strength})</small>
        </Kv>
        <Kv label="Slope / bar">{fmtPrice(v.slope, digits + 1)}</Kv>
        <Kv label="Upper Boundary">{fmtPrice(v.upper, digits)}</Kv>
        <Kv label="Mid Line">{fmtPrice(v.mid, digits)}</Kv>
        <Kv label="Lower Boundary">{fmtPrice(v.lower, digits)}</Kv>
        <Kv label="Width">
          {fmtPrice(v.width, digits)} <small>({v.width_atr?.toFixed(1)}× ATR)</small>
        </Kv>
        <Kv label="Touches (Upper / Lower)">
          {v.touches_upper} / {v.touches_lower}
        </Kv>
        <Kv label="Validity">{v.validity.label}</Kv>
        <Kv label="Channel Age">
          {v.age} <small>{v.age_unit}</small>
        </Kv>
      </dl>
    </Panel>
  );
}

function ContextPanel({ d, digits }: { d: Live; digits: number }) {
  const c = d.context;
  const sc = d.scenarios;
  return (
    <Panel title="Channel Context" icon={<Compass size={14} />}>
      <dl className="mtr-kv is-tight">
        <Kv label="Parent Channel">
          {c.parent && c.parent_tf ? (
            <span className={dirTone(c.parent.direction.key) === 'is-up' ? 'up' : dirTone(c.parent.direction.key) === 'is-down' ? 'down' : 'amber'}>
              {c.parent_tf} {c.parent.direction.label}
            </span>
          ) : (
            '—'
          )}
        </Kv>
        <Kv label="Position in Parent">{c.position_in_parent != null ? `${c.position_in_parent.toFixed(0)}%` : '—'}</Kv>
        <Kv label={`Next Level (${c.next_level_role})`}>{fmtPrice(c.next_level, digits)}</Kv>
        <Kv label="Next Expected Event">{c.next_event}</Kv>
        <Kv label="Structural Invalidation" tone="down">
          {fmtPrice(c.invalidation, digits)}
        </Kv>
      </dl>
      <div className="mci-probs">
        <h4>Structural Scenarios</h4>
        {(
          [
            ['Channel Continuation', sc.continue, 'is-green'],
            ['Boundary Breakout', sc.breakout, 'is-blue'],
            ['Channel Reversal', sc.reversal, 'is-red'],
          ] as const
        ).map(([label, value, tone]) => (
          <div key={label} className="mci-prob">
            <span>{label}</span>
            <span className={`mtr-meter ${tone}`}>
              <i style={{ width: `${value}%` }} />
            </span>
            <b>{value}%</b>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function Sparkline({ spark, tone }: { spark: Spark; tone: string }) {
  const w = 132;
  const h = 46;
  const cs = spark.candles;
  if (cs.length < 2) return <svg width={w} height={h} />;
  const lo = Math.min(...cs.map((c) => c.l), spark.lower[0], spark.lower[1]);
  const hi = Math.max(...cs.map((c) => c.h), spark.upper[0], spark.upper[1]);
  const x = (i: number) => 2 + (i / (cs.length - 1)) * (w - 4);
  const y = (v: number) => 3 + ((hi - v) / (hi - lo || 1)) * (h - 6);
  const x0 = x(spark.from);
  const x1 = x(cs.length - 1);
  return (
    <svg className="mci-spark" width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-hidden>
      <polygon className="mci-spark-band" points={`${x0},${y(spark.upper[0])} ${x1},${y(spark.upper[1])} ${x1},${y(spark.lower[1])} ${x0},${y(spark.lower[0])}`} />
      <line className="mci-spark-edge" x1={x0} y1={y(spark.upper[0])} x2={x1} y2={y(spark.upper[1])} />
      <line className="mci-spark-edge" x1={x0} y1={y(spark.lower[0])} x2={x1} y2={y(spark.lower[1])} />
      <polyline className={`mci-spark-line ${tone}`} points={cs.map((c, i) => `${x(i)},${y(c.c)}`).join(' ')} />
    </svg>
  );
}

function MtfCard({ tf, v, spark, on, onPick }: { tf: ChannelTf; v: ChannelView; spark: Spark | null; on: boolean; onPick: (tf: ChannelTf) => void }) {
  if (!v.available) {
    return (
      <button className="mci-tfcard is-off" disabled>
        <header>
          <b>{tf}</b>
        </header>
        <span className="mtr-muted">Insufficient history</span>
      </button>
    );
  }
  const tone = dirTone(v.direction.key);
  return (
    <button className={`mci-tfcard ${on ? 'is-on' : ''}`} onClick={() => onPick(tf)} aria-pressed={on}>
      <header>
        <b>{tf}</b>
        <span className={`mci-dir ${tone}`}>
          {dirIcon(v.direction.key, 12)} {v.direction.label}
        </span>
      </header>
      {spark ? <Sparkline spark={spark} tone={tone} /> : null}
      <div className="mci-pos">
        <span className="mci-pos-track">
          <i style={{ left: `${Math.max(0, Math.min(100, v.position ?? 50))}%` }} />
        </span>
        <small>
          <b>{v.position != null ? `${v.position.toFixed(0)}%` : '—'}</b> {v.state.label}
        </small>
      </div>
    </button>
  );
}

function StatsPanel({ d, digits }: { d: Live; digits: number }) {
  const s = d.stats;
  const success = s.breakout_attempts ? Math.round((s.successful_breakouts / s.breakout_attempts) * 100) : null;
  return (
    <Panel title="Channel Statistics" icon={<BarChart3 size={14} />}>
      <div className="mci-statgrid">
        <div>
          <small>Average Width</small>
          <b>{fmtPrice(s.avg_width, digits)}</b>
          <em>{s.atr ? `${(s.avg_width / s.atr).toFixed(1)}× ATR` : ''}</em>
        </div>
        <div>
          <small>Width Range</small>
          <b>
            {fmtPrice(s.min_width, digits)} – {fmtPrice(s.max_width, digits)}
          </b>
        </div>
        <div>
          <small>Average Slope / bar</small>
          <b className={s.avg_slope >= 0 ? 'up' : 'down'}>{fmtPrice(s.avg_slope, digits + 1)}</b>
        </div>
        <div>
          <small>Boundary Touches</small>
          <b>{s.touches}</b>
          <em>
            {s.touches_upper} upper · {s.touches_lower} lower
          </em>
        </div>
        <div>
          <small>Breakout Attempts</small>
          <b>{s.breakout_attempts}</b>
          <em>
            {s.successful_breakouts} held · {s.false_breakouts} failed
          </em>
        </div>
        <div>
          <small>Breakout Success</small>
          <b>{success != null ? `${success}%` : '—'}</b>
        </div>
      </div>
    </Panel>
  );
}

function EventsPanel({ d, digits }: { d: Live; digits: number }) {
  return (
    <Panel title="Recent Channel Events" icon={<History size={14} />}>
      <div className="mtr-scroll is-events mci-events">
        <table className="mtr-table is-compact">
          <thead>
            <tr>
              <th>Time</th>
              <th>TF</th>
              <th>Event</th>
              <th className="num">Level</th>
              <th className="center">Result</th>
            </tr>
          </thead>
          <tbody>
            {d.events.map((e, i) => (
              <tr key={`${e.tf}-${e.at}-${e.event}-${i}`}>
                <td className="mtr-muted">{eventTime(e.at, e.tf)}</td>
                <td className="mtr-muted">{e.tf}</td>
                <td>{e.event}</td>
                <td className="num">{fmtPrice(e.level, digits)}</td>
                <td className="center">
                  <Pill
                    tone={
                      ['Respect', 'Rebound', 'Confirmed', 'Completed'].includes(e.result) ? 'is-green' : e.result === 'Failed' ? 'is-red' : e.result === 'Pressing' ? 'is-amber' : 'is-blue'
                    }
                  >
                    {e.result}
                  </Pill>
                </td>
              </tr>
            ))}
            {!d.events.length ? (
              <tr>
                <td colSpan={5} className="mtr-empty">
                  No recent channel events
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function LevelsPanel({ d, digits }: { d: Live; digits: number }) {
  const k = d.key_levels;
  const rows: [string, number, string][] = [
    ['Upper Extension 2', k.upper_ext_2, 'is-ext'],
    ['Upper Extension 1', k.upper_ext_1, 'is-ext'],
    ['Channel Resistance', k.upper, 'is-res'],
    ['Mid Line', k.mid, 'is-mid'],
    ['Channel Support', k.lower, 'is-sup'],
    ['Lower Extension 1', k.lower_ext_1, 'is-ext'],
    ['Lower Extension 2', k.lower_ext_2, 'is-ext'],
  ];
  const at = rows.findIndex(([, p]) => p < d.price);
  const ladder: [string, number, string][] = [...rows];
  ladder.splice(at < 0 ? rows.length : at, 0, ['Current Price', d.price, 'is-price']);
  return (
    <Panel title="Key Levels & Projection" icon={<Target size={14} />} extra={<small className="mtr-muted">ATR {fmtPrice(k.atr, digits)}</small>}>
      <ol className="mci-ladder">
        {ladder.map(([label, price, cls]) => {
          const dist = price - d.price;
          return (
            <li key={label} className={cls}>
              <span>{label}</span>
              <b>{fmtPrice(price, digits)}</b>
              <small>{cls === 'is-price' ? 'now' : `${signed(k.atr ? dist / k.atr : null, 1)} ATR`}</small>
            </li>
          );
        })}
      </ol>
      {k.invalidation != null ? (
        <p className="mci-note">
          Structural invalidation: close {d.view.direction.key === 'UPTREND' ? 'below' : 'above'} <b>{fmtPrice(k.invalidation, digits)}</b>
        </p>
      ) : null}
    </Panel>
  );
}

export function ChannelAnalysis({
  symbol,
  d,
  digits,
  tf,
  onTf,
  candles,
  chartHeight,
}: {
  symbol: string;
  d: Live;
  digits: number;
  tf: ChannelTf;
  onTf: (tf: ChannelTf) => void;
  candles: { candles: VCandle[]; loading: boolean; error: string };
  chartHeight: number;
}) {
  const v: LiveChannelView = d.view;
  const overlay = useMemo(() => (d.tf === tf ? channelOverlay(d.lines, digits) : null), [d, tf, digits]);
  return (
    <>
      <Kpis d={d} />
      <div className="mci-row2">
        <div className="mtr-chart">
          <StructureChart
            symbol={symbol}
            title="Channel"
            tf={tf}
            candles={candles.candles}
            loading={candles.loading}
            error={candles.error}
            digits={digits}
            lastPrice={d.price}
            overlay={overlay}
            height={chartHeight}
            heading={
              <strong className="mtr-chart-title">
                <InstrumentIcon base={symbol.slice(0, 3)} quote={symbol.slice(3, 6)} size="sm" /> {symbol} – {TF_NAMES[tf]} Channel
                <span className={`mtr-state-pill ${dirTone(v.direction.key)}`}>{v.direction.label.toUpperCase()}</span>
              </strong>
            }
            actions={<span className="mst-tf-badge">{v.period} bars · ±2σ regression</span>}
            legend={[
              { label: 'Channel boundaries', swatch: 'is-chan' },
              { label: 'Mid line', swatch: 'is-chan-mid' },
              { label: 'Live price', swatch: 'is-last' },
            ]}
          />
        </div>
        <div className="mci-side">
          <DetailsPanel d={d} digits={digits} />
          <ContextPanel d={d} digits={digits} />
        </div>
      </div>
      <Panel title="Multi-Timeframe Channel View" icon={<Layers size={14} />} className="mci-mtf" extra={<small className="mtr-muted">Select a timeframe to chart it</small>}>
        <div className="mci-tfgrid">
          {CHANNEL_TFS.map((t) => (
            <MtfCard key={t} tf={t} v={d.views[t]} spark={d.sparks[t]} on={t === tf} onPick={onTf} />
          ))}
        </div>
      </Panel>
      <div className="mci-row4">
        <StatsPanel d={d} digits={digits} />
        <EventsPanel d={d} digits={digits} />
        <LevelsPanel d={d} digits={digits} />
      </div>
    </>
  );
}

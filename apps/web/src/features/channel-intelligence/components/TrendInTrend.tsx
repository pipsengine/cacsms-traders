import { useMemo } from 'react';
import {
  ArrowDownRight,
  ArrowUpRight,
  CalendarClock,
  Gauge,
  GitMerge,
  Hourglass,
  Layers,
  Lightbulb,
  ListOrdered,
  Network,
  Star,
  Target,
  TrendingDown,
  Workflow,
} from 'lucide-react';
import { InstrumentIcon } from '../../market-scanner/components/InstrumentIcon';
import { fmtPrice } from '../../market-scanner/format';
import { StructureChart } from '../../market-structure/components/StructureChart';
import { Kpi, Kv, Lifecycle, Meter, Panel, Pill, statusTone } from '../../market-structure/components/StructureUi';
import type { VCandle } from '../../market-structure/types';
import type { ChannelLines, ChannelPayload, EventTf, TitView } from '../types';
import { channelOverlay, dirTone } from './shared';

type Candles = { candles: VCandle[]; loading: boolean; error: string };
type LiveTit = Extract<TitView, { available: true }>;

export function titCharts(tit: TitView | null | undefined): { L1: EventTf; CT: EventTf; EXEC: EventTf } {
  if (tit?.available && tit.charts) return tit.charts;
  const p = tit?.available ? tit.parent.tf : 'W';
  return p === 'W' ? { L1: 'W', CT: 'D1', EXEC: 'H8' } : { L1: 'D1', CT: 'H8', EXEC: 'H1' };
}

const bull = (d?: string) => d === 'UPTREND';

function Kpis({ tit }: { tit: TitView }) {
  if (!tit.available) {
    return (
      <div className="mtr-kpis">
        <Kpi tone="is-gray" icon={<GitMerge size={20} />} label="TiT State" value="NO PARENT" sub={tit.reason} />
      </div>
    );
  }
  const ct = tit.countertrend;
  const up = bull(tit.parent.direction);
  return (
    <div className="mtr-kpis">
      <Kpi
        tone={tit.state.key === 'ACTIVE' ? 'is-green' : tit.state.key === 'ALIGNED' ? 'is-blue' : 'is-amber'}
        icon={<GitMerge size={20} />}
        label="TiT State"
        value={tit.tit_layer ? `${tit.tit_layer} ${tit.state.label.toUpperCase()}` : tit.state.label.toUpperCase()}
        sub={tit.summary}
      />
      <Kpi
        tone={up ? 'is-green' : 'is-red'}
        icon={up ? <ArrowUpRight size={22} /> : <ArrowDownRight size={22} />}
        label="HTF Parent Trend"
        value={up ? 'BULLISH' : 'BEARISH'}
        sub={`${tit.parent.layer} · ${tit.parent.tf} channel · ${tit.parent.state.label}`}
      />
      <Kpi
        tone="is-amber"
        icon={<TrendingDown size={20} />}
        label="LTF Countertrend"
        value={ct ? (up ? 'PULLBACK' : 'RALLY') : 'NONE'}
        sub={ct ? `${ct.layer} · ${ct.tf} · ${ct.phase}` : 'Layers aligned with parent'}
      />
      <Kpi tone="is-purple" icon={<Hourglass size={20} />} label="Countertrend Maturity" value={ct ? `${ct.maturity}%` : '—'} bar={ct?.maturity ?? null} />
      <Kpi
        tone="is-blue"
        icon={<CalendarClock size={20} />}
        label="Next TiT Event"
        value={tit.next_event?.label ?? '—'}
        sub={tit.next_event?.bars ? `Est. ${tit.next_event.bars[0]}–${tit.next_event.bars[1]} ${ct?.tf ?? ''} bars` : undefined}
      />
      <Kpi
        tone="is-rose"
        icon={<Star size={20} />}
        label="Setup Quality"
        value={
          tit.quality ? (
            <>
              {tit.quality.score}
              <small> / 100</small>
            </>
          ) : (
            '—'
          )
        }
        bar={tit.quality?.score ?? null}
        sub={tit.quality?.label}
      />
    </div>
  );
}

function LayerChart({
  symbol,
  label,
  tf,
  lines,
  candles,
  digits,
  price,
  height,
  state,
  tone,
}: {
  symbol: string;
  label: string;
  tf: EventTf;
  lines: ChannelLines | null | undefined;
  candles: Candles;
  digits: number;
  price: number | null | undefined;
  height: number;
  state?: { text: string; tone: string };
  tone: 'blue' | 'purple';
}) {
  const overlay = useMemo(() => channelOverlay(lines, digits, true, tone), [lines, digits, tone]);
  return (
    <div className="mtr-chart">
      <StructureChart
        symbol={symbol}
        title={label}
        tf={tf}
        candles={candles.candles}
        loading={candles.loading}
        error={candles.error}
        digits={digits}
        lastPrice={price}
        overlay={overlay}
        height={height}
        showVolume={false}
        compact
        className="mci-layer-chart"
        heading={
          <strong className="mtr-chart-title is-sm">
            {label} <span className="mst-tf-badge">{tf}</span>
          </strong>
        }
        actions={state ? <span className={`mtr-state-pill ${state.tone}`}>{state.text}</span> : <span />}
      />
    </div>
  );
}

function LayersPanel({ tit }: { tit: TitView }) {
  return (
    <Panel title="Trend-in-Trend Analysis" icon={<Layers size={14} />}>
      <table className="mtr-table is-compact">
        <thead>
          <tr>
            <th>Layer</th>
            <th className="center">TF</th>
            <th>Trend</th>
            <th>Channel State</th>
            <th className="num">Position</th>
            <th>Alignment</th>
          </tr>
        </thead>
        <tbody>
          {tit.layers.map((l) =>
            l.available ? (
              <tr key={l.id} className={tit.available && tit.tit_layer === l.id ? 'is-selected' : ''}>
                <td>
                  <b>{l.id}</b>
                </td>
                <td className="center mtr-muted">{l.tf}</td>
                <td>
                  <span className={`mtr-regime ${l.layer_dir > 0 ? 'is-bull' : l.layer_dir < 0 ? 'is-bear' : 'is-range'}`}>{l.trend.label}</span>
                </td>
                <td>
                  <Pill tone={l.state.key === 'PULLBACK' ? 'is-amber' : statusTone(l.state.key.startsWith('BREAKOUT') ? 'FAILED' : 'ACTIVE')}>{l.state.label}</Pill>
                </td>
                <td className="num">{l.position != null ? `${l.position.toFixed(0)}%` : '—'}</td>
                <td className={l.alignment === 'Countertrend' ? 'amber' : l.alignment === 'With L1' ? 'up' : 'mtr-muted'}>{l.alignment}</td>
              </tr>
            ) : (
              <tr key={l.id}>
                <td>
                  <b>{l.id}</b>
                </td>
                <td className="center mtr-muted">{l.tf}</td>
                <td colSpan={4} className="mtr-muted">
                  Insufficient history
                </td>
              </tr>
            ),
          )}
        </tbody>
      </table>
    </Panel>
  );
}

function MetricsPanel({ tit, digits }: { tit: LiveTit; digits: number }) {
  const ct = tit.countertrend;
  if (!ct) {
    return (
      <Panel title="Countertrend Metrics" icon={<Gauge size={14} />}>
        <p className="mtr-muted">No lower-timeframe channel is moving against the {tit.parent.tf} parent trend.</p>
      </Panel>
    );
  }
  const up = bull(tit.parent.direction);
  return (
    <Panel title="Countertrend Metrics" icon={<Gauge size={14} />} extra={<span className="mst-tf-badge">{ct.layer} · {ct.tf}</span>}>
      <dl className="mtr-kv is-tight">
        <Kv label="Countertrend Type">{ct.type}</Kv>
        <Kv label="Direction" tone={dirTone(ct.direction.key) === 'is-up' ? 'up' : 'down'}>
          {ct.direction.label}
        </Kv>
        <Kv label="Phase">{ct.phase}</Kv>
        <Kv label="Maturity">
          <span className="mci-inline-meter">
            <Meter value={ct.maturity} tone="is-amber" /> <b>{ct.maturity}%</b>
          </span>
        </Kv>
        <Kv label="Position in Channel">
          {ct.position != null ? `${ct.position.toFixed(0)}%` : '—'} <small>({ct.half})</small>
        </Kv>
        <Kv label={up ? 'Distance to Lower' : 'Distance to Upper'}>
          {fmtPrice(up ? ct.distance_lower : ct.distance_upper, digits)}{' '}
          <small>({(up ? ct.distance_lower_atr : ct.distance_upper_atr)?.toFixed(2)} ATR)</small>
        </Kv>
        <Kv label="Rejoin Level">{fmtPrice(ct.rejoin_level, digits)}</Kv>
        <Kv label="Expected Duration">{ct.expected_bars ? `${ct.expected_bars[0]}–${ct.expected_bars[1]} ${ct.tf} bars` : '—'}</Kv>
        <Kv label="Rejoin Score">
          <span className="mci-inline-meter">
            <Meter value={ct.rejoin_score} /> <b>{ct.rejoin_score}%</b>
          </span>
        </Kv>
        <Kv label="Execution Layer">
          {ct.exec_layer} · {ct.exec_tf}
        </Kv>
      </dl>
    </Panel>
  );
}

function SetupPanel({ tit, digits }: { tit: LiveTit; digits: number }) {
  const s = tit.setup;
  return (
    <Panel title="Continuation Setup" icon={<Target size={14} />} extra={s ? <Pill tone={statusTone(s.status.key)}>{s.status.label}</Pill> : null}>
      {s ? (
        <>
          <div className={`mtr-setup ${bull(s.direction) ? 'is-green' : 'is-red'}`}>
            <span className="mtr-setup-icon">{bull(s.direction) ? <ArrowUpRight size={18} /> : <ArrowDownRight size={18} />}</span>
            <div>
              <strong>{s.type.toUpperCase()}</strong>
              <small>{s.direction_label.toUpperCase()}</small>
            </div>
          </div>
          <dl className="mtr-kv is-tight">
            <Kv label="Continuation Zone">
              {fmtPrice(s.zone[0], digits)} – {fmtPrice(s.zone[1], digits)}
            </Kv>
            <Kv label={`Objective 1 (${s.objective_1_label})`} tone="up">
              {fmtPrice(s.objective_1, digits)}
            </Kv>
            <Kv label={`Objective 2 (${s.objective_2_label})`} tone="up">
              {fmtPrice(s.objective_2, digits)}
            </Kv>
            <Kv label={`Invalidation (${s.invalidation_label})`} tone="down">
              {fmtPrice(s.invalidation, digits)}
            </Kv>
            <Kv label="Reward : Risk">{s.ratio != null ? `${s.ratio.toFixed(2)} : 1` : '—'}</Kv>
            <Kv label="Setup Quality">
              <b>{s.quality}</b> / 100
            </Kv>
          </dl>
          <p className="mtr-foot">Structural zones only · handed to the Opportunity Engine for any further evaluation</p>
        </>
      ) : (
        <p className="mtr-muted">Layers are aligned with the parent trend — no countertrend pullback to measure.</p>
      )}
    </Panel>
  );
}

function CandidatesPanel({ rows, selected, onSelect }: { rows: ChannelPayload['tit']; selected: string; onSelect: (s: string) => void }) {
  return (
    <Panel title="Trend-in-Trend Candidates" icon={<ListOrdered size={14} />} extra={<small className="mtr-muted">{rows.length} symbols</small>}>
      <div className="mtr-scroll is-events mci-short">
        <table className="mtr-table is-compact mtr-matrix-rows">
          <thead>
            <tr>
              <th>Symbol</th>
              <th className="center">Layer</th>
              <th>Setup</th>
              <th>Direction</th>
              <th className="center">Maturity</th>
              <th className="center">Quality</th>
              <th className="center">Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.symbol} className={`is-click ${selected === r.symbol ? 'is-selected' : ''}`} onClick={() => onSelect(r.symbol)}>
                <td>
                  <span className="mtr-symcell">
                    <InstrumentIcon base={r.base} quote={r.quote} size="sm" />
                    <b>{r.symbol}</b>
                  </span>
                </td>
                <td className="center mtr-muted">
                  {r.layer} · {r.tf}
                </td>
                <td>{r.setup_type}</td>
                <td className={bull(r.direction) ? 'up' : 'down'}>{bull(r.direction) ? 'Bullish' : 'Bearish'}</td>
                <td className="center">{r.maturity}%</td>
                <td className="center">
                  <span className={`mtr-score ${r.quality >= 70 ? 'is-strong' : r.quality >= 50 ? 'is-mid' : 'is-weak'}`}>{r.quality}</span>
                </td>
                <td className="center">
                  <Pill tone={statusTone(r.status.key)}>{r.status.label}</Pill>
                </td>
              </tr>
            ))}
            {!rows.length ? (
              <tr>
                <td colSpan={7} className="mtr-empty">
                  No symbol has a countertrend channel inside a trending parent
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

export function TrendInTrend({
  data,
  symbol,
  onSelect,
  tit,
  tfLines,
  digits,
  price,
  candles,
  chartHeight,
}: {
  data: ChannelPayload;
  symbol: string;
  onSelect: (s: string) => void;
  tit: TitView;
  tfLines: Record<string, ChannelLines | null>;
  digits: number;
  price: number | null | undefined;
  candles: { L1: Candles; CT: Candles; EXEC: Candles };
  chartHeight: number;
}) {
  const charts = titCharts(tit);
  const live = tit.available ? tit : null;
  const layerOf = (tf: EventTf) => tit.layers.find((l) => l.tf === tf);
  const stateFor = (tf: EventTf) => {
    const l = layerOf(tf);
    return l?.available ? { text: `${l.trend.label.toUpperCase()} · ${l.state.label.toUpperCase()}`, tone: l.layer_dir > 0 ? 'is-up' : l.layer_dir < 0 ? 'is-down' : 'is-amber' } : undefined;
  };
  const id = (tf: EventTf) => layerOf(tf)?.id ?? '';
  return (
    <>
      <Kpis tit={tit} />
      <div className={`mci-charts3 ${data.meta.stale ? 'is-stale' : ''}`}>
        <LayerChart
          symbol={symbol}
          label={`HTF Parent Channel (${id(charts.L1)})`}
          tf={charts.L1}
          lines={tfLines[charts.L1]}
          candles={candles.L1}
          digits={digits}
          price={price}
          height={chartHeight}
          state={stateFor(charts.L1)}
          tone="blue"
        />
        <LayerChart
          symbol={symbol}
          label={`LTF Countertrend Channel (${id(charts.CT)})`}
          tf={charts.CT}
          lines={tfLines[charts.CT]}
          candles={candles.CT}
          digits={digits}
          price={price}
          height={chartHeight}
          state={stateFor(charts.CT)}
          tone="purple"
        />
        <LayerChart
          symbol={symbol}
          label={`Execution TF (${id(charts.EXEC)})`}
          tf={charts.EXEC}
          lines={tfLines[charts.EXEC]}
          candles={candles.EXEC}
          digits={digits}
          price={price}
          height={chartHeight}
          state={stateFor(charts.EXEC)}
          tone="blue"
        />
      </div>
      <div className="mci-row3">
        <LayersPanel tit={tit} />
        {live ? <MetricsPanel tit={live} digits={digits} /> : <Panel title="Countertrend Metrics" icon={<Gauge size={14} />}><p className="mtr-muted">{!tit.available ? tit.reason : ''}</p></Panel>}
        {live ? <SetupPanel tit={live} digits={digits} /> : <Panel title="Continuation Setup" icon={<Target size={14} />}><p className="mtr-muted">No trending parent channel.</p></Panel>}
      </div>
      <div className="mci-row4t">
        <CandidatesPanel rows={data.tit} selected={symbol} onSelect={onSelect} />
        <Panel title="TiT Setup Lifecycle" icon={<Workflow size={14} />}>
          {live ? <Lifecycle steps={live.lifecycle} /> : <p className="mtr-muted">—</p>}
        </Panel>
        <Panel title="Key Takeaways" icon={<Lightbulb size={14} />} className="mci-takeaway">
          {live ? (
            <ul className="mci-takeaways">
              {live.takeaways.map((t) => (
                <li key={t}>
                  <Network size={12} /> {t}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mtr-muted">{!tit.available ? tit.reason : ''}</p>
          )}
          <small className="mtr-foot">Structural analysis on closed bars · not a trade instruction</small>
        </Panel>
      </div>
    </>
  );
}

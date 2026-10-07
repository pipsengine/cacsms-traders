import { useMemo, useState } from 'react';
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  ClipboardList,
  Compass,
  History,
  Hourglass,
  Layers,
  ListChecks,
  Repeat2,
  Ruler,
  Shuffle,
  Workflow,
} from 'lucide-react';
import { InstrumentIcon } from '../../market-scanner/components/InstrumentIcon';
import { fmtPrice } from '../../market-scanner/format';
import type { BosDetail, BosEvent, BosPayload, BosTf, VCandle } from '../types';
import { StructureChart, type ChartOverlay } from './StructureChart';
import { Blocking, EvidenceList, Kpi, Kv, Lifecycle, Panel, Pill, TfSwitch, eventTime, regimeTone, rowDigits, statusTone, titleCase } from './StructureUi';

export const BOS_TFS: BosTf[] = ['W', 'D1', 'H8', 'H1'];
const TF_NAMES: Record<BosTf, string> = { W: 'Weekly (W)', D1: 'Daily (D1)', H8: 'H8', H1: 'H1' };
const PERIODS = [
  { key: '1', label: 'Last 24 hours', days: 1 },
  { key: '7', label: 'Last 7 days', days: 7 },
  { key: '30', label: 'Last 30 days', days: 30 },
];
const EVENT_FILTERS = [
  { key: 'ALL', label: 'All Events' },
  { key: 'BOS', label: 'BOS only' },
  { key: 'CHOCH', label: 'CHoCH only' },
  { key: 'UP', label: 'Bullish' },
  { key: 'DOWN', label: 'Bearish' },
];

const eventLabel = (e: { kind: string; direction: string }) => `${e.direction === 'UP' ? 'Bullish' : 'Bearish'} ${e.kind === 'BOS' ? 'BOS' : 'CHoCH'}`;

function Kpis({ counts }: { counts: BosPayload['counts'] }) {
  return (
    <div className="mtr-kpis">
      <Kpi
        tone="is-blue"
        icon={<Activity size={21} />}
        label="Total Structure Events"
        value={
          <>
            {counts.total}
            {counts.new_24h ? <small className="mbo-new"> +{counts.new_24h} new</small> : null}
          </>
        }
        sub="Last 7 days · closed bars"
      />
      <Kpi tone="is-green" icon={<ArrowUpRight size={22} />} label="Bullish BOS" value={counts.bullish_bos} sub="Break of structure ↑" />
      <Kpi tone="is-red" icon={<ArrowDownRight size={22} />} label="Bearish BOS" value={counts.bearish_bos} sub="Break of structure ↓" />
      <Kpi tone="is-green" icon={<Shuffle size={20} />} label="Bullish CHoCH" value={counts.bullish_choch} sub="Change of character ↑" />
      <Kpi tone="is-red" icon={<Shuffle size={20} />} label="Bearish CHoCH" value={counts.bearish_choch} sub="Change of character ↓" />
      <Kpi tone="is-amber" icon={<Hourglass size={20} />} label="Awaiting Confirmation" value={counts.awaiting} sub="Developing or retesting" />
    </div>
  );
}

function EventsTable({
  data,
  selected,
  onPick,
}: {
  data: BosPayload;
  selected: { symbol: string; at: string | null };
  onPick: (e: BosEvent) => void;
}) {
  const [asset, setAsset] = useState('ALL');
  const [kind, setKind] = useState('ALL');
  const [tf, setTf] = useState('ALL');
  const [period, setPeriod] = useState('7');
  const list = useMemo(() => {
    const since = Date.now() - PERIODS.find((p) => p.key === period)!.days * 86400000;
    return data.events.filter(
      (e) =>
        Date.parse(e.at) >= since &&
        (asset === 'ALL' || e.asset === asset) &&
        (tf === 'ALL' || e.tf === tf) &&
        (kind === 'ALL' || e.kind === kind || e.direction === kind),
    );
  }, [data.events, asset, kind, tf, period]);

  return (
    <section className="mst-card mst-panel mtr-matrix">
      <header className="mtr-panel-head">
        <h3>
          <History size={14} /> Recent BOS / CHoCH Events <small>({list.length})</small>
        </h3>
        <div className="mtr-tools">
          <select value={asset} onChange={(e) => setAsset(e.target.value)} aria-label="Asset class">
            <option value="ALL">All Assets</option>
            <option value="Forex">Forex</option>
            <option value="Commodity">Commodity</option>
          </select>
          <select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Event type">
            {EVENT_FILTERS.map((f) => (
              <option key={f.key} value={f.key}>
                {f.label}
              </option>
            ))}
          </select>
          <select value={tf} onChange={(e) => setTf(e.target.value)} aria-label="Timeframe">
            <option value="ALL">All Timeframes</option>
            {BOS_TFS.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <select value={period} onChange={(e) => setPeriod(e.target.value)} aria-label="Period">
            {PERIODS.map((p) => (
              <option key={p.key} value={p.key}>
                {p.label}
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
              <th className="num">Close</th>
              <th className="center">Retest</th>
              <th className="center">Status</th>
            </tr>
          </thead>
          <tbody>
            {list.map((e, i) => {
              const d = rowDigits(e);
              const on = selected.symbol === e.symbol && selected.at === `${e.tf}|${e.at}`;
              return (
                <tr
                  key={`${e.symbol}-${e.tf}-${e.at}-${e.kind}-${i}`}
                  className={on ? 'is-selected' : ''}
                  onClick={() => onPick(e)}
                  tabIndex={0}
                  onKeyDown={(ev) => (ev.key === 'Enter' || ev.key === ' ') && onPick(e)}
                  aria-selected={on}
                >
                  <td className="mtr-muted" title={new Date(e.at).toUTCString()}>
                    {eventTime(e.at, e.tf)}
                  </td>
                  <td>
                    <span className="mtr-symcell">
                      <InstrumentIcon base={e.base} quote={e.quote} size="sm" />
                      <b>{e.symbol}</b>
                    </span>
                  </td>
                  <td className="center mtr-muted">{e.tf}</td>
                  <td>
                    <span className={`mbo-event ${e.direction === 'UP' ? 'is-up' : 'is-down'} ${e.kind === 'CHOCH' ? 'is-choch' : ''}`}>{eventLabel(e)}</span>
                  </td>
                  <td className="num">{fmtPrice(e.level, d)}</td>
                  <td className="num">{e.close != null ? fmtPrice(e.close, d) : <span className="mtr-muted">open bar</span>}</td>
                  <td className="center">
                    <Pill tone={statusTone(e.retest.key)}>{e.retest.label}</Pill>
                  </td>
                  <td className="center">
                    <Pill tone={statusTone(e.status.key)}>{e.status.label}</Pill>
                  </td>
                </tr>
              );
            })}
            {!list.length ? (
              <tr>
                <td colSpan={8} className="mtr-empty">
                  No structure events match the selected filters
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function BosChart({
  symbol,
  detail,
  digits,
  tf,
  onTf,
  candles,
  height,
}: {
  symbol: string;
  detail: BosDetail | null;
  digits: number;
  tf: BosTf;
  onTf: (tf: BosTf) => void;
  candles: { candles: VCandle[]; loading: boolean; error: string };
  height: number;
}) {
  const ok = detail?.available && detail.tf === tf ? detail : null;
  const overlay = useMemo<ChartOverlay | null>(() => {
    if (!ok) return null;
    const lines: NonNullable<ChartOverlay['lines']> = [];
    const markers: NonNullable<ChartOverlay['markers']> = [];
    for (const e of ok.marks.events) {
      if (!e.swing_at || !e.break_at) continue;
      const tone = e.direction === 'UP' ? ('green' as const) : ('red' as const);
      lines.push({ from: [e.swing_at, e.level], to: [e.break_at, e.level], tone, dashed: e.failed, width: 1.4 });
      const mid = new Date((Date.parse(e.swing_at) + Date.parse(e.break_at)) / 2).toISOString();
      markers.push({ at: mid, price: e.level, shape: 'text', tone, label: e.kind === 'BOS' ? 'BOS' : 'CHoCH', muted: e.failed, below: e.direction === 'DOWN' });
    }
    for (const s of ok.marks.swings.slice(-14)) {
      markers.push({ at: s.at, price: s.price, shape: 'text', tone: 'gray', label: s.label, below: s.side === 'LOW' });
    }
    const levels: NonNullable<ChartOverlay['levels']> = [];
    const inv = ok.details?.invalidation;
    if (inv != null) levels.push({ price: inv, tone: 'red', label: 'Invalidation' });
    return { lines, markers, levels };
  }, [ok]);
  const view = detail?.available ? detail : null;
  return (
    <div className="mtr-chart">
      <StructureChart
        symbol={symbol}
        title="BOS / CHoCH"
        tf={tf}
        candles={candles.candles}
        loading={candles.loading}
        error={candles.error}
        digits={digits}
        lastPrice={view?.context.price ?? detail?.summary.price}
        overlay={overlay}
        height={height}
        heading={
          <strong className="mtr-chart-title">
            <InstrumentIcon base={symbol.slice(0, 3)} quote={symbol.slice(3, 6)} size="sm" /> {symbol} – BOS / CHoCH
            {view?.details ? (
              <span className={`mtr-state-pill ${view.details.direction === 'UP' ? 'is-up' : 'is-down'}`}>{view.details.label.toUpperCase()}</span>
            ) : null}
          </strong>
        }
        actions={<TfSwitch tfs={BOS_TFS} value={tf} onChange={onTf} label="BOS chart timeframe" />}
        legend={[
          { label: 'Bullish break', swatch: 'is-bull-line' },
          { label: 'Bearish break', swatch: 'is-bear-line' },
          { label: 'Failed break', swatch: 'is-failed-line' },
          { label: 'Swing labels (HH / HL / LH / LL)', swatch: 'is-swing' },
        ]}
      />
    </div>
  );
}

const regimeWord = (r?: string | null) => titleCase(r ?? 'NEUTRAL');

function ContextPanel({ d, digits }: { d: Extract<BosDetail, { available: true }>; digits: number }) {
  const c = d.context;
  const lvl = (x: { level: number; tf: string; direction: string } | null) =>
    x ? (
      <span className={x.direction === 'UP' ? 'up' : 'down'}>
        {fmtPrice(x.level, digits)} <small>({x.tf})</small>
      </span>
    ) : (
      '—'
    );
  return (
    <Panel title="Structure Context" icon={<Compass size={14} />}>
      <dl className="mtr-kv">
        <Kv label="Parent Structure (W)">
          <span className={`mtr-regime ${regimeTone(c.parent)}`}>{regimeWord(c.parent)}</span>
          {c.parent_band ? <small> {c.parent_band}</small> : null}
        </Kv>
        <Kv label="D1 Structure">
          <span className={`mtr-regime ${regimeTone(c.d1)}`}>{regimeWord(c.d1)}</span>
        </Kv>
        <Kv label="Market Phase">{c.phase?.label ?? '—'}</Kv>
        <Kv label="Last BOS">{lvl(c.last_bos)}</Kv>
        <Kv label="Last CHoCH">{lvl(c.last_choch)}</Kv>
        <Kv label="Current Price">{fmtPrice(c.price, digits)}</Kv>
        <Kv label="Nearest Resistance">
          {c.nearest_resistance ? (
            <>
              {fmtPrice(c.nearest_resistance.price, digits)} <small>({c.nearest_resistance.tf})</small>
            </>
          ) : (
            '—'
          )}
        </Kv>
        <Kv label="Nearest Support">
          {c.nearest_support ? (
            <>
              {fmtPrice(c.nearest_support.price, digits)} <small>({c.nearest_support.tf})</small>
            </>
          ) : (
            '—'
          )}
        </Kv>
        <Kv label="Structural Bias" tone={c.bias.startsWith('Bullish') ? 'up' : c.bias.startsWith('Bearish') ? 'down' : undefined}>
          {c.bias}
        </Kv>
      </dl>
    </Panel>
  );
}

function DetailsPanel({ d, digits }: { d: Extract<BosDetail, { available: true }>; digits: number }) {
  const x = d.details;
  return (
    <Panel
      title="Event Details"
      icon={<ClipboardList size={14} />}
      extra={x ? <span className={`mbo-event ${x.direction === 'UP' ? 'is-up' : 'is-down'} ${x.kind === 'CHOCH' ? 'is-choch' : ''}`}>{x.label}</span> : null}
    >
      {x ? (
        <dl className="mtr-kv">
          <Kv label="Timeframe">{TF_NAMES[x.tf]}</Kv>
          <Kv label="Break Level">{fmtPrice(x.level, digits)}</Kv>
          <Kv label="Break Candle">{x.break_candle ? eventTime(x.break_candle, x.tf) : 'Open bar'}</Kv>
          <Kv label="Close">{x.closed ? `${x.close_side} level` : 'Awaiting bar close'}</Kv>
          <Kv label="Body Acceptance" tone={x.body_acceptance ? 'up' : x.body_acceptance === false ? 'down' : undefined}>
            {x.body_acceptance == null ? '—' : x.body_acceptance ? 'Yes' : 'No'}
          </Kv>
          <Kv label="Structure After">{x.structure_after}</Kv>
          <Kv label="Volume" tone={x.volume_confirmed ? 'up' : undefined}>
            {x.volume_ratio != null ? `${x.volume_ratio.toFixed(2)}× average` : '—'}
          </Kv>
          <Kv label="Retest">
            <Pill tone={statusTone(x.retest.key)}>{x.retest.label}</Pill>
          </Kv>
          <Kv label="Status">
            <Pill tone={statusTone(x.status.key)}>{x.status.label}</Pill>
          </Kv>
          <Kv label="Invalidation" tone="down">
            {fmtPrice(x.invalidation, digits)}
          </Kv>
          <Kv label="Since Break">{x.since}</Kv>
        </dl>
      ) : (
        <p className="mtr-muted">No structure break recorded on the analysed timeframes.</p>
      )}
    </Panel>
  );
}

function MtfPanel({ d }: { d: Extract<BosDetail, { available: true }> }) {
  return (
    <Panel title="Multi-Timeframe Structure" icon={<Layers size={14} />}>
      <table className="mtr-mini">
        <tbody>
          {d.mtf.map((r) => (
            <tr key={r.tf}>
              <td>{TF_NAMES[r.tf]}</td>
              <td>
                <span className={`mtr-regime ${regimeTone(r.structure)}`}>{regimeWord(r.structure)}</span>
              </td>
              <td className="mtr-swings">
                {r.last_event ? <span className={r.last_direction === 'UP' ? 'up' : 'down'}>{r.last_event}</span> : '—'}{' '}
                <small className="mtr-muted">{r.status}</small>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}

function LevelsPanel({ d, digits }: { d: Extract<BosDetail, { available: true }>; digits: number }) {
  return (
    <Panel title="Related Levels" icon={<Ruler size={14} />}>
      <table className="mtr-table is-compact">
        <thead>
          <tr>
            <th>Level</th>
            <th>Type</th>
            <th className="center">TF</th>
            <th className="num">Distance</th>
          </tr>
        </thead>
        <tbody>
          {d.levels.map((l, i) => (
            <tr key={`${l.price}-${i}`}>
              <td className="num">{fmtPrice(l.price, digits)}</td>
              <td className={l.type === 'Resistance' ? 'down' : l.type === 'Support' ? 'up' : 'mbo-key'}>{l.type}</td>
              <td className="center mtr-muted">{l.tf}</td>
              <td className={`num ${l.distance != null && l.distance >= 0 ? 'up' : 'down'}`}>
                {l.distance != null ? `${l.distance >= 0 ? '+' : ''}${fmtPrice(l.distance, digits)}` : '—'}
              </td>
            </tr>
          ))}
          {!d.levels.length ? (
            <tr>
              <td colSpan={4} className="mtr-empty">
                No confirmed swings yet
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </Panel>
  );
}

export function BosStructure({
  data,
  detail,
  detailError,
  symbol,
  onSelect,
  tf,
  onTf,
  candles,
  chartHeight,
}: {
  data: BosPayload;
  detail: BosDetail | null;
  detailError: string;
  symbol: string;
  onSelect: (s: string) => void;
  tf: BosTf;
  onTf: (tf: BosTf) => void;
  candles: { candles: VCandle[]; loading: boolean; error: string };
  chartHeight: number;
}) {
  const [picked, setPicked] = useState<string | null>(null);
  const summary = detail?.summary ?? data.symbols.find((r) => r.symbol === symbol) ?? null;
  const digits = summary ? rowDigits(summary) : 2;
  const d = detail?.available ? detail : null;
  return (
    <>
      <Kpis counts={data.counts} />
      <div className={`mtr-row2 ${data.meta.stale ? 'is-stale' : ''}`}>
        <EventsTable
          data={data}
          selected={{ symbol, at: picked }}
          onPick={(e) => {
            setPicked(`${e.tf}|${e.at}`);
            onSelect(e.symbol);
            onTf(e.tf);
          }}
        />
        <BosChart symbol={symbol} detail={detail} digits={digits} tf={tf} onTf={onTf} candles={candles} height={chartHeight} />
      </div>
      {d ? (
        <div className="mbo-row3">
          <ContextPanel d={d} digits={digits} />
          <DetailsPanel d={d} digits={digits} />
          <div className="mtr-stack">
            <MtfPanel d={d} />
            <Panel title="Event Lifecycle" icon={<Workflow size={14} />}>
              {d.lifecycle ? <Lifecycle steps={d.lifecycle} horizontal /> : <p className="mtr-muted">No active event</p>}
            </Panel>
          </div>
          <div className="mtr-stack">
            <Panel title="Supporting Evidence" icon={<ListChecks size={14} />}>
              {d.evidence ? <EvidenceList items={d.evidence} /> : <p className="mtr-muted">No active event</p>}
            </Panel>
            <LevelsPanel d={d} digits={digits} />
          </div>
        </div>
      ) : detail && !detail.available ? (
        <Blocking title={`${symbol} — structure events unavailable`} reason="Insufficient closed history" />
      ) : detailError ? (
        <Blocking title="BOS / CHoCH analysis unavailable" error={detailError} />
      ) : (
        <Blocking loading={`Loading ${symbol} structure events…`} />
      )}
      <p className="mtr-foot">
        <Repeat2 size={11} /> Structure breaks are evaluated on closed bars; developing breaks use the live price and are labelled as such. Analysis only — not
        a trade instruction.
      </p>
    </>
  );
}

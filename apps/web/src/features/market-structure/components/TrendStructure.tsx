import { useMemo, useState, type ReactNode } from 'react';
import {
  ArrowDownRight,
  ArrowLeftRight,
  ArrowUpRight,
  Bot,
  ClipboardList,
  Clock3,
  Grid3x3,
  HeartPulse,
  History,
  Layers,
  Minus,
  Search,
  ShieldAlert,
  Target,
  TrendingUp,
  Waves,
} from 'lucide-react';
import { InstrumentIcon } from '../../market-scanner/components/InstrumentIcon';
import { fmtPrice, priceDigits } from '../../market-scanner/format';
import type { TrendDetail, TrendEvent, TrendMtfRow, TrendPayload, TrendRow, TrendTf, TrendView, VCandle } from '../types';
import { StructureChart } from './StructureChart';

export const TREND_TFS: TrendTf[] = ['W', 'D1', 'H8', 'H1'];
const TF_NAMES: Record<TrendTf, string> = { W: 'Weekly (W)', D1: 'Daily (D1)', H8: 'H8', H1: 'H1' };

const FILTERS: { key: string; label: string; test: (r: TrendRow) => boolean }[] = [
  { key: 'ALL', label: 'All Symbols', test: () => true },
  { key: 'TRENDING', label: 'Trending', test: (r) => !!r.direction },
  { key: 'BULLISH', label: 'Bullish', test: (r) => r.direction === 'BULLISH' },
  { key: 'BEARISH', label: 'Bearish', test: (r) => r.direction === 'BEARISH' },
  { key: 'PULLBACK', label: 'In Pullback', test: (r) => !!r.pullback },
  { key: 'CONTINUATION', label: 'Continuation Setup', test: (r) => r.setup === 'CONTINUATION' },
  { key: 'REVERSAL', label: 'Reversal Risk', test: (r) => !!r.reversal_risk },
];

const pct = (n: number, d: number) => (d ? Math.round((n / d) * 100) : 0);

const cellTone = (k?: string) =>
  k === 'BULL' ? 'is-bull' : k === 'BEAR' ? 'is-bear' : k === 'RANGE' ? 'is-range' : k === 'PULLBACK' ? 'is-pull' : 'is-neutral';

const stateTone = (k?: string) =>
  !k ? 'is-gray' : k.includes('UPTREND') ? 'is-up' : k.includes('DOWNTREND') ? 'is-down' : k === 'RANGING' ? 'is-amber' : 'is-gray';

const strengthTone = (v: number, strong: number) => (v >= strong ? 'is-strong' : v >= 50 ? 'is-mid' : 'is-weak');

const statusTone = (k?: string) =>
  k === 'CONFIRMED' || k === 'IN_ZONE'
    ? 'is-green'
    : k === 'RETESTING' || k === 'DEVELOPING' || k === 'MONITORING'
      ? 'is-blue'
      : k === 'EXTENDED' || k === 'WATCHING'
        ? 'is-amber'
        : k === 'FAILED' || k === 'INVALIDATED'
          ? 'is-red'
          : 'is-gray';

const setupTone = (k?: string) =>
  k === 'CONTINUATION' || k === 'EXTENSION' ? 'is-green' : k === 'REVERSAL_RISK' ? 'is-red' : k === 'DEVELOPING' ? 'is-blue' : 'is-gray';

const SETUP_TYPES: Record<string, string> = {
  CONTINUATION: 'Pullback Continuation',
  EXTENSION: 'Trend Extension',
  REVERSAL_RISK: 'Reversal Watch',
  DEVELOPING: 'Early Trend',
  NO_TREND: 'No Directional Setup',
};

function ageLabel(weeks: number | null | undefined, long = false) {
  if (weeks == null) return '—';
  if (weeks < 1) {
    const days = Math.max(1, Math.round(weeks * 7));
    return `${days} ${days === 1 ? 'day' : 'days'}`;
  }
  const w = Math.round(weeks);
  return long ? `${w} ${w === 1 ? 'week' : 'weeks'}` : `${w} wks`;
}

function eventTime(iso: string, tf: TrendTf) {
  const d = new Date(iso);
  const day = new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short' }).format(d);
  if (tf === 'W' || tf === 'D1') return day;
  return `${day} ${new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false }).format(d)}`;
}

function rowDigits(r: Pick<TrendRow, 'digits' | 'symbol' | 'quote'>) {
  return priceDigits({ digits: r.digits ?? undefined, symbol: r.symbol, quote: r.quote });
}

/* ---------- KPI row ---------- */

function Kpi({ tone, icon, label, value, total, note }: { tone: string; icon: ReactNode; label: string; value: number; total?: number; note?: string }) {
  const share = total != null ? pct(value, total) : null;
  return (
    <section className={`mst-card mtr-kpi ${tone}`}>
      <span className="mtr-kpi-icon">{icon}</span>
      <div>
        <span className="mtr-kpi-label">{label}</span>
        <strong>
          {value}
          {total != null ? (
            <small>
              {label === 'Trending Symbols' ? ` / ${total}` : ''} ({share}%)
            </small>
          ) : null}
        </strong>
        {share != null ? (
          <span className="mtr-bar">
            <i style={{ width: `${share}%` }} />
          </span>
        ) : (
          <small className="mtr-kpi-note">{note}</small>
        )}
      </div>
    </section>
  );
}

function Kpis({ counts }: { counts: TrendPayload['counts'] }) {
  const n = counts.analysed;
  return (
    <div className="mtr-kpis">
      <Kpi tone="is-green" icon={<TrendingUp size={22} />} label="Trending Symbols" value={counts.trending} total={n} />
      <Kpi tone="is-green" icon={<ArrowUpRight size={22} />} label="Bullish Trends" value={counts.bullish} total={n} />
      <Kpi tone="is-red" icon={<ArrowDownRight size={22} />} label="Bearish Trends" value={counts.bearish} total={n} />
      <Kpi tone="is-amber" icon={<Waves size={22} />} label="Pullback in Trend" value={counts.pullback} total={n} />
      <Kpi tone="is-blue" icon={<Clock3 size={22} />} label="Continuation Setup" value={counts.continuation} note="Pullbacks inside a valid trend" />
      <Kpi tone="is-rose" icon={<Target size={22} />} label="Reversal Risk" value={counts.reversal_risk} note="Weakening trend structure" />
    </div>
  );
}

/* ---------- Matrix ---------- */

function Matrix({ data, selected, onSelect }: { data: TrendPayload; selected: string; onSelect: (s: string) => void }) {
  const [query, setQuery] = useState('');
  const [asset, setAsset] = useState('ALL');
  const [filter, setFilter] = useState('ALL');
  const strong = data.meta.trend_settings?.strong_min ?? 75;
  const list = useMemo(() => {
    const q = query.trim().toUpperCase();
    const test = FILTERS.find((f) => f.key === filter)!.test;
    return data.rows.filter(
      (r) => (!q || r.symbol.includes(q) || r.name.toUpperCase().includes(q)) && (asset === 'ALL' || r.asset === asset) && (filter === 'ALL' || (r.available && test(r))),
    );
  }, [data.rows, query, asset, filter]);

  return (
    <section className="mst-card mst-panel mtr-matrix">
      <header className="mtr-panel-head">
        <h3>
          <Grid3x3 size={14} /> Trend Structure Matrix <small>({data.counts.analysed} Symbols)</small>
        </h3>
        <div className="mtr-tools">
          <label className="mtr-search">
            <Search size={13} aria-hidden />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search symbol…" aria-label="Search symbol" />
          </label>
          <select value={asset} onChange={(e) => setAsset(e.target.value)} aria-label="Asset class">
            <option value="ALL">All Assets</option>
            <option value="Forex">Forex</option>
            <option value="Commodity">Commodity</option>
          </select>
          <select value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Trend filter">
            {FILTERS.map((f) => (
              <option key={f.key} value={f.key}>
                {f.label}
              </option>
            ))}
          </select>
        </div>
      </header>
      <div className="mtr-scroll">
        <table className="mtr-table">
          <thead>
            <tr>
              <th className="center">#</th>
              <th>Symbol</th>
              {TREND_TFS.map((tf) => (
                <th key={tf} className="center">
                  {tf}
                </th>
              ))}
              <th>Trend State</th>
              <th className="center">Strength</th>
              <th className="center">Trend Age</th>
            </tr>
          </thead>
          <tbody>
            {list.map((r, i) => (
              <tr
                key={r.symbol}
                className={selected === r.symbol ? 'is-selected' : ''}
                onClick={() => onSelect(r.symbol)}
                tabIndex={0}
                onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && onSelect(r.symbol)}
                aria-selected={selected === r.symbol}
              >
                <td className="center mtr-muted">{i + 1}</td>
                <td>
                  <span className="mtr-symcell">
                    <InstrumentIcon base={r.base} quote={r.quote} size="sm" />
                    <b>{r.symbol}</b>
                  </span>
                </td>
                {r.available && r.cells ? (
                  <>
                    {TREND_TFS.map((tf) => {
                      const c = r.cells![tf];
                      return (
                        <td key={tf} className="center">
                          {c ? <span className={`mso-cell ${cellTone(c.key)}`}>{c.key}</span> : <span className="mtr-muted">—</span>}
                        </td>
                      );
                    })}
                    <td className={`mtr-state ${stateTone(r.state?.key)}`}>{r.state?.label}</td>
                    <td className="center">
                      <span className={`mtr-score ${strengthTone(r.strength ?? 0, strong)}`}>{r.strength}</span>
                    </td>
                    <td className="center mtr-muted">{ageLabel(r.age_weeks)}</td>
                  </>
                ) : (
                  <td colSpan={7} className="mtr-muted">
                    {r.reason ?? 'Insufficient closed history'}
                  </td>
                )}
              </tr>
            ))}
            {!list.length ? (
              <tr>
                <td colSpan={9} className="mtr-empty">
                  No symbols match the selected filters
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/* ---------- Chart ---------- */

function TrendChart({
  symbol,
  view,
  detail,
  digits,
  tf,
  onTf,
  candles,
  height,
}: {
  symbol: string;
  view: TrendView | null;
  detail: TrendDetail | null;
  digits: number;
  tf: TrendTf;
  onTf: (tf: TrendTf) => void;
  candles: { candles: VCandle[]; loading: boolean; error: string };
  height: number;
}) {
  const channel = detail?.available ? detail.channels[tf] : null;
  return (
    <div className="mtr-chart">
      <StructureChart
        symbol={symbol}
        title="Trend Analysis"
        tf={tf}
        candles={candles.candles}
        loading={candles.loading}
        error={candles.error}
        digits={digits}
        lastPrice={view?.price ?? detail?.summary.price}
        channel={channel}
        height={height}
        heading={
          <strong className="mtr-chart-title">
            <InstrumentIcon base={symbol.slice(0, 3)} quote={symbol.slice(3, 6)} size="sm" /> {symbol} – Trend Analysis
            {view ? <span className={`mtr-state-pill ${stateTone(view.state.key)}`}>{view.state.label.toUpperCase()}</span> : null}
          </strong>
        }
        actions={
          <div className="mtr-tf" role="group" aria-label="Trend chart timeframe">
            {TREND_TFS.map((x) => (
              <button key={x} className={tf === x ? 'is-on' : ''} onClick={() => onTf(x)} aria-pressed={tf === x}>
                {x}
              </button>
            ))}
          </div>
        }
      />
    </div>
  );
}

/* ---------- Intelligence panels ---------- */

function Kv({ label, children, tone }: { label: string; children: ReactNode; tone?: string }) {
  return (
    <div className="mtr-kv-row">
      <dt>{label}</dt>
      <dd className={tone}>{children}</dd>
    </div>
  );
}

function DetailPanel({ view, digits }: { view: TrendView; digits: number }) {
  const g = view.geometry;
  const dir = view.direction === 'BULLISH' ? 'Bullish' : view.direction === 'BEARISH' ? 'Bearish' : 'No clear direction';
  const kl = view.key_levels;
  return (
    <section className="mst-card mst-panel mtr-detail">
      <h3>
        <ClipboardList size={14} /> Trend Structure Detail
      </h3>
      <dl className="mtr-kv">
        <Kv label="Trend Direction" tone={view.direction === 'BULLISH' ? 'up' : view.direction === 'BEARISH' ? 'down' : 'mtr-muted'}>
          {dir}
        </Kv>
        <Kv label="Trend State">{view.state.label}</Kv>
        <Kv label="Structure">{view.structure_sequence.length ? view.structure_sequence.join(' → ') : '—'}</Kv>
        <Kv label="Key Level (Support)">
          {fmtPrice(kl.support, digits)} <small>(Channel Support)</small>
        </Kv>
        <Kv label="Key Level (Resistance)">
          {fmtPrice(kl.resistance, digits)} <small>(Channel Resistance)</small>
        </Kv>
        <Kv label="Current Price">{fmtPrice(view.price, digits)}</Kv>
        <Kv label="Trend Strength">
          <b>{view.strength}</b> / 100
        </Kv>
        <Kv label="Trend Age">
          <span title={view.trend_started_at ? `Since ${new Date(view.trend_started_at).toUTCString()}` : undefined}>{ageLabel(view.age_weeks, true)}</span>
        </Kv>
        <Kv label="Pullback State">{g ? g.pullback.label : view.direction ? 'No measurable leg' : '—'}</Kv>
        <Kv label="Continuation Zone">{g ? `${fmtPrice(g.zone[0], digits)} – ${fmtPrice(g.zone[1], digits)}` : '—'}</Kv>
        <Kv label="Invalidation Level" tone={g ? 'down' : undefined}>
          {g ? fmtPrice(g.invalidation, digits) : '—'}
        </Kv>
      </dl>
      <p className="mtr-foot">Key levels: {kl.basis}</p>
    </section>
  );
}

function RegimeTag({ row }: { row: TrendMtfRow }) {
  const r = row.cell?.regime;
  if (!r) return <span className="mtr-muted">—</span>;
  const map: Record<string, [string, ReactNode, string]> = {
    BULLISH: ['is-bull', <ArrowUpRight size={12} key="i" />, 'Bullish'],
    BEARISH: ['is-bear', <ArrowDownRight size={12} key="i" />, 'Bearish'],
    RANGING: ['is-range', <ArrowLeftRight size={12} key="i" />, 'Ranging'],
  };
  const [tone, icon, label] = map[r] ?? ['is-neutral', <Minus size={12} key="i" />, 'Transition'];
  return (
    <span className={`mtr-regime ${tone}`}>
      {icon} {label}
    </span>
  );
}

function MtfPanel({ rows }: { rows: TrendMtfRow[] }) {
  return (
    <section className="mst-card mst-panel mtr-mtf">
      <h3>
        <Layers size={14} /> Multi-Timeframe Structure
      </h3>
      <table className="mtr-mini">
        <tbody>
          {rows.map((r) => (
            <tr key={r.tf}>
              <td>{TF_NAMES[r.tf]}</td>
              <td>
                <RegimeTag row={r} />
              </td>
              <td className="mtr-swings">
                {r.swings}
                {r.cell?.key === 'PULLBACK' ? <span className="mtr-pull">Pullback</span> : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function HealthPanel({ view }: { view: TrendView }) {
  const h = view.health;
  const items: { label: string; value: number | null; tone?: string; hint: string }[] = [
    { label: 'Structure Strength', value: h.structure_strength, hint: 'Consecutive with-trend swings on the analysis timeframe' },
    { label: 'Channel Position', value: h.channel_position, hint: 'Price position inside the regression channel (0 = support, 100 = resistance)' },
    { label: 'Momentum Alignment', value: h.momentum_alignment, hint: 'Share of W / D1 / H8 / H1 channels sloping with the trend' },
    { label: 'Pullback Depth', value: h.pullback_depth, tone: 'is-amber', hint: 'Retracement of the last impulse leg' },
    { label: 'Trend Continuation', value: h.trend_continuation, hint: 'Composite continuation confidence' },
  ];
  const tone = (v: number) => (v >= 60 ? 'is-green' : v >= 40 ? 'is-amber' : 'is-red');
  return (
    <section className="mst-card mst-panel mtr-health">
      <h3>
        <HeartPulse size={14} /> Trend Health Indicators
      </h3>
      <ul>
        {items.map((it) => (
          <li key={it.label} title={it.hint}>
            <span>{it.label}</span>
            <b>{it.value ?? '—'}</b>
            <span className={`mtr-meter ${it.value == null ? '' : it.tone ?? tone(it.value)}`}>
              <i style={{ width: `${it.value ?? 0}%` }} />
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function EventsPanel({ events, digits }: { events: TrendEvent[]; digits: number }) {
  return (
    <section className="mst-card mst-panel mtr-events">
      <h3>
        <History size={14} /> Recent Trend Events
      </h3>
      <div className="mtr-scroll is-events">
        <table className="mtr-table is-compact">
          <thead>
            <tr>
              <th>Time</th>
              <th>TF</th>
              <th>Event</th>
              <th className="num">Level</th>
              <th className="center">Status</th>
            </tr>
          </thead>
          <tbody>
            {events.map((e, i) => (
              <tr key={`${e.tf}-${e.at}-${e.event}-${i}`}>
                <td className="mtr-muted" title={new Date(e.at).toUTCString()}>
                  {eventTime(e.at, e.tf)}
                </td>
                <td className="mtr-muted">{e.tf}</td>
                <td className={e.direction === 'UP' ? 'up' : 'down'}>{e.event}</td>
                <td className="num">{fmtPrice(e.level, digits)}</td>
                <td className="center">
                  <span className={`mtr-status ${statusTone(e.status.key)}`}>{e.status.label}</span>
                </td>
              </tr>
            ))}
            {!events.length ? (
              <tr>
                <td colSpan={5} className="mtr-empty">
                  No confirmed swings or structure breaks yet
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function narrative(view: TrendView, digits: number, zoneBand: [number, number], strongMin: number) {
  const g = view.geometry;
  const word = view.direction === 'BULLISH' ? 'bullish' : 'bearish';
  const trend = `${view.strength >= strongMin ? 'a strong' : 'a'} ${word} trend`;
  const zone = g ? `${fmtPrice(g.zone[0], digits)} – ${fmtPrice(g.zone[1], digits)}` : '';
  const band = `${Math.round(zoneBand[0] * 1000) / 10}–${Math.round(zoneBand[1] * 1000) / 10}%`;
  switch (view.setup.key) {
    case 'CONTINUATION':
      return `Price is in a pullback within ${trend} (${g?.depth_pct.toFixed(0)}% of the last ${view.analysis_tf} impulse). Structural continuation zone ${zone} (${band} retracement).`;
    case 'EXTENSION':
      return `Price is extending within ${trend}; no pullback has formed on the ${view.analysis_tf} leg yet.`;
    case 'REVERSAL_RISK':
      return `The ${word} trend structure is weakening: ${view.reversal_reasons.join('; ')}.`;
    case 'DEVELOPING':
      return `A ${word} structure is developing on ${view.analysis_tf}${view.age_weeks != null ? ` (${ageLabel(view.age_weeks, true)} old)` : ''}; higher timeframes have not confirmed it yet.`;
    default:
      return 'No directional structure across W / D1 / H8 / H1. Waiting for a trend to form.';
  }
}

function AnalysisPanel({ view, digits, zoneBand, strongMin }: { view: TrendView; digits: number; zoneBand: [number, number]; strongMin: number }) {
  const g = view.geometry;
  const tone = setupTone(view.setup.key);
  return (
    <section className="mst-card mst-panel mtr-analysis">
      <h3>
        <Bot size={14} /> Autonomous Analysis
      </h3>
      <div className={`mtr-setup ${tone}`}>
        <span className="mtr-setup-icon">{view.setup.key === 'REVERSAL_RISK' ? <ShieldAlert size={18} /> : <TrendingUp size={18} />}</span>
        <div>
          <strong>{view.setup.title.toUpperCase()}</strong>
          <small>{view.setup.subtitle.toUpperCase()}</small>
        </div>
      </div>
      <p className="mtr-narrative">{narrative(view, digits, zoneBand, strongMin)}</p>
      <dl className="mtr-kv is-tight">
        <Kv label="Confidence">
          <b>{view.confidence}%</b>
        </Kv>
        <Kv label="Setup Type">{SETUP_TYPES[view.setup.key]}</Kv>
        <Kv label="Continuation Zone">{g ? `${fmtPrice(g.zone[0], digits)} – ${fmtPrice(g.zone[1], digits)}` : '—'}</Kv>
        <Kv label="Objective 1" tone={g ? 'up' : undefined}>
          {g ? fmtPrice(g.objective_1, digits) : '—'}
        </Kv>
        <Kv label="Objective 2" tone={g ? 'up' : undefined}>
          {g ? fmtPrice(g.objective_2, digits) : '—'}
        </Kv>
        <Kv label="Invalidation" tone={g ? 'down' : undefined}>
          {g ? fmtPrice(g.invalidation, digits) : '—'}
        </Kv>
        <Kv label="Risk : Reward">{g?.ratio != null ? `1 : ${g.ratio.toFixed(2)}` : '—'}</Kv>
        <Kv label="Status">
          <span className={`mtr-status ${statusTone(g?.status.key)}`}>{g ? g.status.label : 'Not applicable'}</span>
        </Kv>
      </dl>
      <p className="mtr-foot">Structural analysis on closed bars · not a trade instruction</p>
    </section>
  );
}

/* ---------- Tab ---------- */

export function TrendStructure({
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
  data: TrendPayload;
  detail: TrendDetail | null;
  detailError: string;
  symbol: string;
  onSelect: (s: string) => void;
  tf: TrendTf;
  onTf: (tf: TrendTf) => void;
  candles: { candles: VCandle[]; loading: boolean; error: string };
  chartHeight: number;
}) {
  const row = detail?.summary ?? data.rows.find((r) => r.symbol === symbol) ?? null;
  const digits = row ? rowDigits(row) : 2;
  const view = detail?.available ? detail.view : null;
  const settings = data.meta.trend_settings;
  const zoneBand = settings?.continuation_zone ?? [0.382, 0.618];
  const strongMin = settings?.strong_min ?? 75;

  return (
    <>
      <Kpis counts={data.counts} />
      <div className={`mtr-row2 ${data.meta.stale ? 'is-stale' : ''}`}>
        <Matrix data={data} selected={symbol} onSelect={onSelect} />
        <TrendChart symbol={symbol} view={view} detail={detail} digits={digits} tf={tf} onTf={onTf} candles={candles} height={chartHeight} />
      </div>
      {view && detail?.available ? (
        <div className="mtr-row3">
          <DetailPanel view={view} digits={digits} />
          <div className="mtr-stack">
            <MtfPanel rows={detail.mtf} />
            <HealthPanel view={view} />
          </div>
          <EventsPanel events={detail.events} digits={digits} />
          <AnalysisPanel view={view} digits={digits} zoneBand={zoneBand} strongMin={strongMin} />
        </div>
      ) : (
        <section className={`mst-card mst-blocking ${detailError ? 'is-error' : ''}`}>
          {detail && !detail.available ? (
            <>
              <strong>{symbol} — trend structure unavailable</strong>
              <span>{detail.summary.reason ?? 'Insufficient closed history'}</span>
            </>
          ) : detailError ? (
            <>
              <strong>Trend analysis unavailable</strong>
              <span>{detailError}</span>
            </>
          ) : (
            <>
              <span className="mst-spinner" aria-hidden />
              Loading {symbol} trend structure…
            </>
          )}
        </section>
      )}
    </>
  );
}

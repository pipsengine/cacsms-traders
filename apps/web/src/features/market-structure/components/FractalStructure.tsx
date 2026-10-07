import { useMemo, useState } from 'react';
import {
  ArrowDownToLine,
  ArrowUpToLine,
  Ban,
  BadgeCheck,
  ClipboardList,
  Grid3x3,
  Layers,
  ListChecks,
  Loader,
  Network,
  Search,
  Sparkles,
  Triangle,
  Workflow,
} from 'lucide-react';
import { InstrumentIcon } from '../../market-scanner/components/InstrumentIcon';
import { fmtPrice } from '../../market-scanner/format';
import type { FractalCluster, FractalDetail, FractalPayload, FractalPoint, FractalRow, FractalTf, FractalView, VCandle } from '../types';
import { StructureChart, type ChartOverlay } from './StructureChart';
import { Blocking, EvidenceList, Kpi, Kv, Lifecycle, Panel, Pill, TfSwitch, regimeTone, rowDigits, stamp, statusTone } from './StructureUi';

export const FRACTAL_TFS: FractalTf[] = ['W', 'D1', 'H8', 'H1'];
const TF_NAMES: Record<FractalTf, string> = { W: 'Weekly (W)', D1: 'Daily (D1)', H8: 'H8', H1: 'H1' };

const FILTERS: { key: string; label: string; test: (r: FractalRow) => boolean }[] = [
  { key: 'ALL', label: 'All Status', test: () => true },
  { key: 'CONFIRMED', label: 'Confirmed', test: (r) => r.latest?.status.key === 'CONFIRMED' },
  { key: 'DEVELOPING', label: 'Developing', test: (r) => ['CANDIDATE', 'DEVELOPING', 'PROVISIONAL'].includes(r.latest?.status.key ?? '') },
  { key: 'INVALID', label: 'Invalid', test: (r) => r.latest?.status.key === 'INVALID' },
];

const pct = (n: number, d: number) => (d ? Math.round((n / d) * 100) : 0);

function Kpis({ counts }: { counts: FractalPayload['counts'] }) {
  return (
    <div className="mtr-kpis">
      <Kpi tone="is-blue" icon={<Triangle size={20} />} label="Total Fractal Candidates" value={counts.total} sub={`Across ${counts.analysed} symbols · W / D1 / H8 / H1`} />
      <Kpi
        tone="is-green"
        icon={<BadgeCheck size={21} />}
        label="Confirmed Fractals"
        value={
          <>
            {counts.confirmed}
            <small> ({pct(counts.confirmed, counts.total)}%)</small>
          </>
        }
        bar={pct(counts.confirmed, counts.total)}
      />
      <Kpi
        tone="is-amber"
        icon={<Loader size={21} />}
        label="Developing Fractals"
        value={
          <>
            {counts.developing}
            <small> ({pct(counts.developing, counts.total)}%)</small>
          </>
        }
        bar={pct(counts.developing, counts.total)}
      />
      <Kpi
        tone="is-red"
        icon={<Ban size={20} />}
        label="Invalid / Rejected"
        value={
          <>
            {counts.invalid}
            <small> ({pct(counts.invalid, counts.total)}%)</small>
          </>
        }
        bar={pct(counts.invalid, counts.total)}
      />
      <Kpi tone="is-purple" icon={<Network size={20} />} label="Weekly Fractal Clusters" value={counts.clusters} sub="Clusters near current price" />
      <Kpi
        tone="is-rose"
        icon={<Sparkles size={20} />}
        label="Active Fractal Symbols"
        value={
          <>
            {counts.symbols_active}
            <small> / {counts.analysed}</small>
          </>
        }
        bar={pct(counts.symbols_active, counts.analysed)}
      />
    </div>
  );
}

function FractalCell({ f }: { f: FractalPoint | null | undefined }) {
  if (!f) return <span className="mtr-muted">—</span>;
  return (
    <span className={`mfr-cell ${f.side === 'HIGH' ? 'is-high' : 'is-low'} ${statusTone(f.status.key)}`} title={`${f.kind} · ${f.status.label}`}>
      {f.kind}
    </span>
  );
}

function FractalMap({ data, selected, onSelect }: { data: FractalPayload; selected: string; onSelect: (s: string) => void }) {
  const [query, setQuery] = useState('');
  const [asset, setAsset] = useState('ALL');
  const [filter, setFilter] = useState('ALL');
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
          <Grid3x3 size={14} /> Fractal Map <small>({data.counts.analysed} Symbols)</small>
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
          <select value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Fractal status">
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
              <th>Symbol</th>
              {FRACTAL_TFS.map((tf) => (
                <th key={tf} className="center">
                  {tf}
                </th>
              ))}
              <th>Latest Fractal</th>
              <th className="center">Status</th>
            </tr>
          </thead>
          <tbody>
            {list.map((r) => (
              <tr
                key={r.symbol}
                className={selected === r.symbol ? 'is-selected' : ''}
                onClick={() => onSelect(r.symbol)}
                tabIndex={0}
                onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && onSelect(r.symbol)}
                aria-selected={selected === r.symbol}
              >
                <td>
                  <span className="mtr-symcell">
                    <InstrumentIcon base={r.base} quote={r.quote} size="sm" />
                    <b>{r.symbol}</b>
                  </span>
                </td>
                {r.available && r.cells ? (
                  <>
                    {FRACTAL_TFS.map((tf) => (
                      <td key={tf} className="center">
                        <FractalCell f={r.cells![tf]} />
                      </td>
                    ))}
                    <td>
                      {r.latest ? (
                        <span className={r.latest.side === 'HIGH' ? 'down' : 'up'}>
                          {r.latest.kind} <span className="mtr-muted">@</span> {fmtPrice(r.latest.price, rowDigits(r))}
                        </span>
                      ) : (
                        <span className="mtr-muted">—</span>
                      )}
                    </td>
                    <td className="center">{r.latest ? <Pill tone={statusTone(r.latest.status.key)}>{r.latest.status.label}</Pill> : <span className="mtr-muted">—</span>}</td>
                  </>
                ) : (
                  <td colSpan={6} className="mtr-muted">
                    {r.reason ?? 'Insufficient closed history'}
                  </td>
                )}
              </tr>
            ))}
            {!list.length ? (
              <tr>
                <td colSpan={7} className="mtr-empty">
                  No symbols match the selected filters
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
      <footer className="mfr-key">
        <span>
          <i className="mfr-cell is-high is-green">WFH</i> Weekly Fractal High
        </span>
        <span>
          <i className="mfr-cell is-low is-green">WFL</i> Weekly Fractal Low
        </span>
        <span>
          <i className="mfr-cell is-high is-green">FH</i>/<i className="mfr-cell is-low is-green">FL</i> Fractal High / Low
        </span>
        <span>
          <i className="mfr-dot is-green" /> Confirmed <i className="mfr-dot is-blue" /> Developing <i className="mfr-dot is-amber" /> Candidate{' '}
          <i className="mfr-dot is-red" /> Invalid
        </span>
      </footer>
    </section>
  );
}

function clusterOverlay(view: FractalView | null, digits: number, tf: FractalTf): ChartOverlay['zones'] {
  if (!view || tf === 'W') return [];
  const out: NonNullable<ChartOverlay['zones']> = [];
  const r = view.clusters.resistance[0];
  const s = view.clusters.support[0];
  if (r) out.push({ lo: r.lo, hi: r.hi, tone: 'res', label: `Weekly Resistance Cluster ${fmtPrice(r.lo, digits)} – ${fmtPrice(r.hi, digits)}` });
  if (s) out.push({ lo: s.lo, hi: s.hi, tone: 'sup', label: `Weekly Support Cluster ${fmtPrice(s.lo, digits)} – ${fmtPrice(s.hi, digits)}` });
  return out;
}

function FractalChart({
  symbol,
  detail,
  digits,
  tf,
  onTf,
  candles,
  height,
}: {
  symbol: string;
  detail: FractalDetail | null;
  digits: number;
  tf: FractalTf;
  onTf: (tf: FractalTf) => void;
  candles: { candles: VCandle[]; loading: boolean; error: string };
  height: number;
}) {
  const ok = detail?.available && detail.tf === tf ? detail : null;
  const view = detail?.available ? detail.view : null;
  const overlay = useMemo<ChartOverlay | null>(() => {
    if (!ok) return null;
    const lastHigh = [...ok.marks].reverse().find((m) => m.side === 'HIGH' && m.status === 'CONFIRMED');
    const lastLow = [...ok.marks].reverse().find((m) => m.side === 'LOW' && m.status === 'CONFIRMED');
    return {
      zones: clusterOverlay(view, digits, tf),
      markers: ok.marks.map((m) => ({
        at: m.at,
        price: m.price,
        shape: m.side === 'HIGH' ? ('down' as const) : ('up' as const),
        tone: m.status === 'PENDING' ? ('amber' as const) : m.status === 'INVALID' ? ('gray' as const) : m.side === 'HIGH' ? ('red' as const) : ('green' as const),
        muted: m.status === 'INVALID',
        label: m.status === 'PENDING' ? `${m.kind}?` : m === lastHigh || m === lastLow ? m.kind : undefined,
      })),
    };
  }, [ok, view, digits, tf]);
  const range = ok && tf === 'W' && ok.range ? { ...ok.range, fractals: [] } : null;
  return (
    <div className="mtr-chart">
      <StructureChart
        symbol={symbol}
        title="Fractal Analysis"
        tf={tf}
        candles={candles.candles}
        loading={candles.loading}
        error={candles.error}
        digits={digits}
        lastPrice={view?.price ?? detail?.summary.price}
        range={range}
        overlay={overlay}
        height={height}
        heading={
          <strong className="mtr-chart-title">
            <InstrumentIcon base={symbol.slice(0, 3)} quote={symbol.slice(3, 6)} size="sm" /> {symbol} – Selected Symbol Fractal Analysis
          </strong>
        }
        actions={<TfSwitch tfs={FRACTAL_TFS} value={tf} onChange={onTf} label="Fractal chart timeframe" />}
        legend={[
          { label: 'Fractal High', swatch: 'is-fh' },
          { label: 'Fractal Low', swatch: 'is-fl' },
          { label: 'Developing', swatch: 'is-fdev' },
          { label: 'Invalid', swatch: 'is-finv' },
          ...(tf === 'W' ? [{ label: 'Weekly Range', swatch: 'is-range' }] : [{ label: 'Weekly Cluster', swatch: 'is-cluster' }]),
        ]}
      />
    </div>
  );
}

function HierarchyPanel({ view, digits }: { view: FractalView; digits: number }) {
  return (
    <Panel title="Fractal Hierarchy" icon={<Layers size={14} />} className="mfr-hier">
      <ol className="mfr-ladder">
        {view.hierarchy.map((h, i) => (
          <li key={`${h.kind}-${h.tf}-${i}`} className={h.kind === 'PRICE' ? 'is-price' : h.side === 'HIGH' ? 'is-high' : 'is-low'}>
            <span className="mfr-rail" aria-hidden />
            <div>
              <b>{h.title}</b>
              <small>{h.note}</small>
            </div>
            <span className="mfr-ladder-price">{fmtPrice(h.price, digits)}</span>
            {h.status ? <Pill tone={statusTone(h.status.key)}>{h.status.label}</Pill> : <span className="mfr-now">Now</span>}
          </li>
        ))}
      </ol>
    </Panel>
  );
}

function DetailsPanel({ view, digits }: { view: FractalView; digits: number }) {
  const d = view.details;
  return (
    <Panel title="Fractal Details" icon={<ClipboardList size={14} />}>
      {d ? (
        <dl className="mtr-kv">
          <Kv label="Fractal" tone={d.side === 'HIGH' ? 'down' : 'up'}>
            {d.label}
          </Kv>
          <Kv label="Price Level">{fmtPrice(d.price, digits)}</Kv>
          <Kv label="Timeframe">{TF_NAMES[d.tf as FractalTf] ?? d.tf}</Kv>
          <Kv label="Status">
            <Pill tone={statusTone(d.status.key)}>{d.status.label}</Pill>
          </Kv>
          <Kv label="Cluster Zone">{d.cluster_zone ? `${fmtPrice(d.cluster_zone[0], digits)} – ${fmtPrice(d.cluster_zone[1], digits)}` : '—'}</Kv>
          <Kv label="Touches">{d.touches}</Kv>
          <Kv label="Last Touch">{stamp(d.last_touch, false)}</Kv>
          <Kv label="Range Position">
            {d.range_position != null ? (
              <>
                {Math.round(d.range_position)}% <small>({d.range_band})</small>
              </>
            ) : (
              '—'
            )}
          </Kv>
          <Kv label="Weekly ATR">{fmtPrice(d.atr, digits)}</Kv>
          <Kv label="Validation">{d.validation}</Kv>
        </dl>
      ) : (
        <p className="mtr-muted">No weekly fractal is active for this symbol.</p>
      )}
    </Panel>
  );
}

function LifecyclePanel({ view }: { view: FractalView }) {
  return (
    <Panel title="Fractal Lifecycle" icon={<Workflow size={14} />} extra={view.details ? <Pill tone={statusTone(view.details.status.key)}>{view.details.kind}</Pill> : null}>
      <Lifecycle steps={view.lifecycle} />
    </Panel>
  );
}

function EvidencePanel({ view }: { view: FractalView }) {
  const met = view.evidence.filter((e) => e.met).length;
  return (
    <Panel
      title="Evidence for Current Fractal"
      icon={<ListChecks size={14} />}
      extra={
        view.evidence.length ? (
          <span className="msx-score">
            {view.evidence_score ?? Math.round((met / view.evidence.length) * 100)}
            <small>/100</small>
          </span>
        ) : null
      }
    >
      {view.evidence.length ? <EvidenceList items={view.evidence} /> : <p className="mtr-muted">No developing weekly fractal — evidence is evaluated while a WFH / WFL forms.</p>}
    </Panel>
  );
}

function LtfPanel({ view }: { view: FractalView }) {
  return (
    <Panel title="Lower Timeframe Confirmation" icon={<Layers size={14} />}>
      <table className="mtr-table is-compact">
        <thead>
          <tr>
            <th>TF</th>
            <th>Structure</th>
            <th>Fractal</th>
            <th>Evidence</th>
          </tr>
        </thead>
        <tbody>
          {view.ltf.map((r) => (
            <tr key={r.tf}>
              <td>
                <b>{r.tf}</b>
              </td>
              <td>
                <span className={`mtr-regime ${regimeTone(r.structure.key)}`}>{r.structure.label}</span>
              </td>
              <td>
                <span className={`mfr-text ${statusTone(r.fractal_status)}`}>{r.fractal}</span>
              </td>
              <td className="mfr-wrap">{r.evidence}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}

function ClusterList({ title, items, digits, tone }: { title: string; items: FractalCluster[]; digits: number; tone: 'is-res' | 'is-sup' }) {
  return (
    <div className={`mfr-clusters ${tone}`}>
      <h4>
        {tone === 'is-res' ? <ArrowUpToLine size={13} /> : <ArrowDownToLine size={13} />} {title}
      </h4>
      {items.length ? (
        <table className="mtr-table is-compact">
          <thead>
            <tr>
              <th>Zone</th>
              <th className="center">Touches</th>
              <th className="center">Age</th>
              <th className="num">Distance</th>
            </tr>
          </thead>
          <tbody>
            {items.slice(0, 3).map((c) => (
              <tr key={`${c.lo}-${c.hi}`}>
                <td>
                  {fmtPrice(c.lo, digits)} – {fmtPrice(c.hi, digits)}
                  {c.near ? <span className="mfr-near">Near</span> : null}
                </td>
                <td className="center">{c.touches}</td>
                <td className="center mtr-muted">{c.age_weeks}w</td>
                <td className="num">{c.distance_atr != null ? `${c.distance_atr.toFixed(1)} ATR` : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="mtr-muted">No clustered weekly fractals</p>
      )}
    </div>
  );
}

function ClustersPanel({ view, digits }: { view: FractalView; digits: number }) {
  return (
    <Panel title="Fractal Clusters" icon={<Network size={14} />}>
      <ClusterList title="Resistance Clusters" items={view.clusters.resistance} digits={digits} tone="is-res" />
      <ClusterList title="Support Clusters" items={view.clusters.support} digits={digits} tone="is-sup" />
    </Panel>
  );
}

export function FractalStructure({
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
  data: FractalPayload;
  detail: FractalDetail | null;
  detailError: string;
  symbol: string;
  onSelect: (s: string) => void;
  tf: FractalTf;
  onTf: (tf: FractalTf) => void;
  candles: { candles: VCandle[]; loading: boolean; error: string };
  chartHeight: number;
}) {
  const row = detail?.summary ?? data.rows.find((r) => r.symbol === symbol) ?? null;
  const digits = row ? rowDigits(row) : 2;
  const view = detail?.available ? detail.view : null;
  return (
    <>
      <Kpis counts={data.counts} />
      <div className={`mtr-row2 ${data.meta.stale ? 'is-stale' : ''}`}>
        <FractalMap data={data} selected={symbol} onSelect={onSelect} />
        <FractalChart symbol={symbol} detail={detail} digits={digits} tf={tf} onTf={onTf} candles={candles} height={chartHeight} />
      </div>
      {view ? (
        <>
          <div className="mfr-row3">
            <HierarchyPanel view={view} digits={digits} />
            <DetailsPanel view={view} digits={digits} />
            <LifecyclePanel view={view} />
            <EvidencePanel view={view} />
          </div>
          <div className="mfr-row4">
            <LtfPanel view={view} />
            <ClustersPanel view={view} digits={digits} />
          </div>
        </>
      ) : detail && !detail.available ? (
        <Blocking title={`${symbol} — fractal analysis unavailable`} reason={detail.summary.reason ?? 'Insufficient closed history'} />
      ) : detailError ? (
        <Blocking title="Fractal analysis unavailable" error={detailError} />
      ) : (
        <Blocking loading={`Loading ${symbol} fractal analysis…`} />
      )}
    </>
  );
}

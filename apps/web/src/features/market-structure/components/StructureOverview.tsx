import { useMemo, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  ArrowLeftRight,
  ArrowRight,
  ArrowUpRight,
  BarChart3,
  Grid3x3,
  Layers,
  Lightbulb,
  PieChart,
  RefreshCw,
  Repeat,
  Trophy,
  TrendingDown,
} from 'lucide-react';
import { InstrumentIcon } from '../../market-scanner/components/InstrumentIcon';
import { fmtPrice, priceDigits } from '../../market-scanner/format';
import type {
  AlignmentEntry,
  KeyLabel,
  OverviewPayload,
  OverviewRow,
  OverviewTf,
  RegimeCounts,
  StructuralEvent,
} from '../types';

const TFS: OverviewTf[] = ['W', 'D1', 'H8', 'H1'];
const REGIME_ORDER: { key: keyof RegimeCounts; label: string; cls: string }[] = [
  { key: 'bullish', label: 'Bullish', cls: 'is-bull' },
  { key: 'bearish', label: 'Bearish', cls: 'is-bear' },
  { key: 'ranging', label: 'Ranging', cls: 'is-range' },
  { key: 'transition', label: 'Transition', cls: 'is-trans' },
];
const REGIME_COLORS: Record<keyof RegimeCounts, string> = {
  bullish: '#12a150',
  bearish: '#e5383b',
  ranging: '#f59e0b',
  transition: '#8a94a6',
};

const pct = (n: number, d: number) => (d ? Math.round((n / d) * 100) : 0);

function timeLabel(iso: string, asOf: string | null) {
  const d = new Date(iso);
  const hm = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false }).format(d);
  const ref = asOf ? new Date(asOf) : new Date();
  if (ref.getTime() - d.getTime() < 24 * 3600 * 1000) return hm;
  return `${new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short' }).format(d)} ${hm}`;
}

const cellTone = (k?: string) =>
  k === 'BULL' ? 'is-bull' : k === 'BEAR' ? 'is-bear' : k === 'RANGE' ? 'is-range' : k === 'PULLBACK' ? 'is-pull' : 'is-neutral';
const stateTone = (k?: string) =>
  k === 'TRENDING' || k === 'CONTINUATION' ? 'is-green' : k === 'REVERSAL' ? 'is-red' : k === 'REACTION' || k === 'BREAKOUT' ? 'is-ink' : 'is-muted';
const statusTone = (k?: string) =>
  k === 'CONFIRMED' ? 'is-green' : k === 'RETESTING' || k === 'DEVELOPING' ? 'is-blue' : k === 'WATCHING' ? 'is-amber' : k === 'ALERT' || k === 'FAILED' ? 'is-red' : 'is-gray';
const regimePill = (k?: string) => (k === 'BULLISH' ? 'is-bull' : k === 'BEARISH' ? 'is-bear' : k === 'RANGING' ? 'is-range' : 'is-neutral');

function Kpis({ data }: { data: OverviewPayload }) {
  const c = data.counts;
  const live = !data.meta.stale && data.meta.mt5_connected;
  const cards = [
    { key: 'bullish' as const, label: 'Bullish Markets', icon: <ArrowUpRight size={22} />, cls: 'is-bull' },
    { key: 'bearish' as const, label: 'Bearish Markets', icon: <ArrowDownRight size={22} />, cls: 'is-bear' },
    { key: 'ranging' as const, label: 'Ranging Markets', icon: <ArrowLeftRight size={22} />, cls: 'is-range' },
    { key: 'transition' as const, label: 'Transition Markets', icon: <RefreshCw size={20} />, cls: 'is-trans' },
  ];
  return (
    <div className="mso-kpis">
      <section className="mst-card mso-kpi is-total">
        <span className="mso-kpi-icon">
          <Layers size={22} />
        </span>
        <div>
          <strong>{c.analysed} Symbols Analysed</strong>
          <small>Across FX and XAUUSD{c.total > c.analysed ? ` · ${c.total - c.analysed} awaiting history` : ''}</small>
        </div>
        <span className={`mso-live ${live ? 'is-on' : 'is-off'}`}>{live ? 'LIVE' : data.meta.mt5_connected ? 'STALE' : 'OFFLINE'}</span>
      </section>
      {cards.map((k) => (
        <section key={k.key} className={`mst-card mso-kpi ${k.cls}`}>
          <span className="mso-kpi-icon">{k.icon}</span>
          <div>
            <span className="mso-kpi-label">{k.label}</span>
            <strong>
              {c[k.key]} <small>/ {c.analysed} ({pct(c[k.key], c.analysed)}%)</small>
            </strong>
            <span className="mso-bar">
              <i style={{ width: `${pct(c[k.key], c.analysed)}%` }} />
            </span>
          </div>
        </section>
      ))}
    </div>
  );
}

function Donut({ counts, total }: { counts: RegimeCounts; total: number }) {
  const r = 52;
  const C = 2 * Math.PI * r;
  let acc = 0;
  return (
    <section className="mst-card mst-panel mso-dist">
      <h3>
        <PieChart size={14} /> Market Structure Distribution
      </h3>
      <div className="mso-dist-body">
        <svg viewBox="0 0 140 140" width="132" height="132" role="img" aria-label="Weekly regime distribution">
          <circle cx="70" cy="70" r={r} fill="none" stroke="#eef1f5" strokeWidth="20" />
          {REGIME_ORDER.map(({ key }) => {
            const len = total ? (counts[key] / total) * C : 0;
            const seg = (
              <circle
                key={key}
                cx="70"
                cy="70"
                r={r}
                fill="none"
                stroke={REGIME_COLORS[key]}
                strokeWidth="20"
                strokeDasharray={`${len} ${C - len}`}
                strokeDashoffset={-acc}
                transform="rotate(-90 70 70)"
              />
            );
            acc += len;
            return seg;
          })}
          <text x="70" y="68" textAnchor="middle" className="mso-donut-n">
            {total}
          </text>
          <text x="70" y="86" textAnchor="middle" className="mso-donut-t">
            Symbols
          </text>
        </svg>
        <ul className="mso-legend">
          {REGIME_ORDER.map(({ key, label }) => (
            <li key={key}>
              <i style={{ background: REGIME_COLORS[key] }} />
              <span>{label}</span>
              <b>
                {counts[key]} ({pct(counts[key], total)}%)
              </b>
            </li>
          ))}
        </ul>
      </div>
      <p className="mso-foot">Weekly regime · closed bars</p>
    </section>
  );
}

function MtfBars({ mtf }: { mtf: OverviewPayload['mtf'] }) {
  return (
    <section className="mst-card mst-panel mso-mtf">
      <h3>
        <BarChart3 size={14} /> Multi-Timeframe Alignment
      </h3>
      <div className="mso-mtf-rows">
        {TFS.map((tf) => {
          const row = mtf[tf];
          const total = REGIME_ORDER.reduce((s, r) => s + row[r.key], 0) || 1;
          return (
            <div key={tf} className="mso-mtf-row">
              <span>{tf}</span>
              <div className="mso-stack">
                {REGIME_ORDER.map(({ key }) =>
                  row[key] ? (
                    <i key={key} style={{ width: `${(row[key] / total) * 100}%`, background: REGIME_COLORS[key] }}>
                      {row[key]}
                    </i>
                  ) : null,
                )}
              </div>
            </div>
          );
        })}
      </div>
      <ul className="mso-legend is-row">
        {REGIME_ORDER.map(({ key, label }) => (
          <li key={key}>
            <i style={{ background: REGIME_COLORS[key] }} />
            <span>{label}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function TopList({ title, icon, items, tone }: { title: string; icon: React.ReactNode; items: AlignmentEntry[]; tone: 'up' | 'down' }) {
  return (
    <section className="mst-card mst-panel mso-top">
      <h3 className={tone === 'down' ? 'is-down' : ''}>
        {icon} {title}
      </h3>
      <table className="mso-top-table">
        <tbody>
          {items.map((r, i) => (
            <tr key={r.symbol}>
              <td className="mso-rank">{i + 1}</td>
              <td className="mso-sym">{r.symbol}</td>
              <td>
                <span className={`mso-score ${r.strength.key === 'BULLISH' ? 'is-bull' : r.strength.key === 'BEARISH' ? 'is-bear' : 'is-neutral'}`}>
                  {r.strength.score}
                </span>
              </td>
              <td>
                <span className={`mso-tag ${r.strength.key === 'BULLISH' ? 'is-bull' : r.strength.key === 'BEARISH' ? 'is-bear' : 'is-neutral'}`}>
                  {r.strength.label}
                </span>
              </td>
            </tr>
          ))}
          {!items.length ? (
            <tr>
              <td className="mso-empty">No analysed symbols yet</td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </section>
  );
}

function Matrix({ rows, onSelect, selected }: { rows: OverviewRow[]; onSelect: (s: string) => void; selected: string }) {
  const [asset, setAsset] = useState('ALL');
  const [regime, setRegime] = useState('ALL');
  const list = useMemo(
    () => rows.filter((r) => (asset === 'ALL' || r.asset === asset) && (regime === 'ALL' || r.regime?.key === regime)),
    [rows, asset, regime],
  );
  const analysed = rows.filter((r) => r.available).length;
  return (
    <section className="mst-card mst-panel mso-matrix">
      <header className="mso-panel-head">
        <h3>
          <Grid3x3 size={14} /> Market Structure Matrix ({analysed} Symbols)
        </h3>
        <div className="mso-selects">
          <select value={asset} onChange={(e) => setAsset(e.target.value)} aria-label="Asset class">
            <option value="ALL">All Assets</option>
            <option value="Forex">Forex</option>
            <option value="Commodity">Commodity</option>
          </select>
          <select value={regime} onChange={(e) => setRegime(e.target.value)} aria-label="Weekly regime">
            <option value="ALL">All Regimes</option>
            <option value="BULLISH">Bullish</option>
            <option value="BEARISH">Bearish</option>
            <option value="RANGING">Ranging</option>
            <option value="TRANSITION">Transition</option>
          </select>
        </div>
      </header>
      <div className="mso-scroll">
        <table className="mso-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Symbol</th>
              <th>Asset</th>
              {TFS.map((tf) => (
                <th key={tf} className="center">
                  {tf}
                </th>
              ))}
              <th>Current State</th>
              <th className="center">Strength</th>
              <th className="center">Range Age</th>
            </tr>
          </thead>
          <tbody>
            {list.map((r, i) => (
              <tr key={r.symbol} className={selected === r.symbol ? 'is-selected' : ''} onClick={() => onSelect(r.symbol)}>
                <td className="mso-muted">{i + 1}</td>
                <td>
                  <span className="mso-symcell">
                    <InstrumentIcon base={r.base} quote={r.quote} size="sm" />
                    <b>{r.symbol}</b>
                  </span>
                </td>
                <td className="mso-muted">{r.asset}</td>
                {r.available && r.cells ? (
                  <>
                    {TFS.map((tf) => (
                      <td key={tf} className="center">
                        {r.cells![tf] ? <span className={`mso-cell ${cellTone(r.cells![tf]!.key)}`}>{r.cells![tf]!.key}</span> : <span className="mso-muted">—</span>}
                      </td>
                    ))}
                    <td className={`mso-state ${stateTone(r.state?.key)}`}>{r.state?.label}</td>
                    <td className="center">
                      <span className={`mso-score ${r.strength!.key === 'BULLISH' ? 'is-bull' : r.strength!.key === 'BEARISH' ? 'is-bear' : 'is-neutral'}`}>
                        {r.strength!.score}
                      </span>
                    </td>
                    <td className="center mso-muted">{r.range_age_weeks ? `${r.range_age_weeks} wks` : '-'}</td>
                  </>
                ) : (
                  <td colSpan={7} className="mso-muted">
                    {r.reason ?? 'Insufficient closed history'}
                  </td>
                )}
              </tr>
            ))}
            {!list.length ? (
              <tr>
                <td colSpan={10} className="mso-empty">
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

function Events({ events, asOf }: { events: StructuralEvent[]; asOf: string | null }) {
  const [all, setAll] = useState(false);
  const list = all ? events : events.slice(0, 5);
  return (
    <section className="mst-card mst-panel mso-events">
      <header className="mso-panel-head">
        <h3>
          <Activity size={14} /> Recent Structural Events
        </h3>
        {events.length > 5 ? (
          <button className="mso-link" onClick={() => setAll((v) => !v)}>
            {all ? 'Show Less' : `View All (${events.length})`}
          </button>
        ) : null}
      </header>
      <div className={`mso-scroll ${all ? 'is-all' : ''}`}>
        <table className="mso-table is-compact">
          <thead>
            <tr>
              <th>Time</th>
              <th>Symbol</th>
              <th>TF</th>
              <th>Event</th>
              <th className="num">Level</th>
              <th className="center">Status</th>
            </tr>
          </thead>
          <tbody>
            {list.map((e, i) => (
              <tr key={`${e.symbol}-${e.tf}-${e.at}-${e.direction}-${i}`}>
                <td className="mso-muted" title={new Date(e.at).toUTCString()}>
                  {timeLabel(e.at, asOf)}
                </td>
                <td>
                  <b>{e.symbol}</b>
                </td>
                <td className="mso-muted">{e.tf}</td>
                <td className={e.direction === 'UP' ? 'mso-up' : 'mso-down'}>{e.label}</td>
                <td className="num">{fmtPrice(e.level, priceDigits({ digits: e.digits ?? undefined, symbol: e.symbol, quote: e.symbol.slice(3, 6) }))}</td>
                <td className="center">
                  <span className={`mso-status ${statusTone(e.status.key)}`}>{e.status.label}</span>
                </td>
              </tr>
            ))}
            {!events.length ? (
              <tr>
                <td colSpan={6} className="mso-empty">
                  No BOS / CHoCH events in the lookback window
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Attention({ items }: { items: OverviewPayload['attention'] }) {
  return (
    <section className="mst-card mst-panel mso-bottom">
      <h3 className="is-amber">
        <AlertTriangle size={14} /> Symbols Requiring Attention {items.length ? <small>({items.length})</small> : null}
      </h3>
      <div className="mso-scroll">
        <table className="mso-table is-compact">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Reason</th>
              <th>TF</th>
              <th>Detail</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {items.map((a) => (
              <tr key={a.symbol}>
                <td>
                  <b>{a.symbol}</b>
                </td>
                <td>{a.reason}</td>
                <td className="mso-muted">{a.tf}</td>
                <td className="mso-muted">{a.detail}</td>
                <td>
                  <span className={`mso-dot ${statusTone(a.status.key)}`}>
                    <i /> {a.status.label}
                  </span>
                </td>
              </tr>
            ))}
            {!items.length ? (
              <tr>
                <td colSpan={5} className="mso-empty">
                  No symbols need attention right now
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function RegimePill({ v }: { v: KeyLabel }) {
  return <span className={`mso-cell ${regimePill(v.key)}`}>{v.key === 'TRANSITION' ? 'TRANS' : v.key === 'RANGING' ? 'RANGE' : v.key === 'BULLISH' ? 'BULL' : 'BEAR'}</span>;
}

function RegimeChanges({ items, hours, asOf }: { items: OverviewPayload['regime_changes']; hours: number; asOf: string | null }) {
  return (
    <section className="mst-card mst-panel mso-bottom">
      <h3>
        <Repeat size={14} /> Regime Changes (Last {hours} Hours)
      </h3>
      <div className="mso-scroll">
        <table className="mso-table is-compact">
          <thead>
            <tr>
              <th>Symbol</th>
              <th className="center">From</th>
              <th />
              <th className="center">To</th>
              <th>TF</th>
              <th>Time</th>
            </tr>
          </thead>
          <tbody>
            {items.map((c, i) => (
              <tr key={`${c.symbol}-${c.tf}-${c.at}-${i}`}>
                <td>
                  <b>{c.symbol}</b>
                </td>
                <td className="center">
                  <RegimePill v={c.from} />
                </td>
                <td className="mso-arrow">
                  <ArrowRight size={13} />
                </td>
                <td className="center">
                  <RegimePill v={c.to} />
                </td>
                <td className="mso-muted">{c.tf}</td>
                <td className="mso-muted">{timeLabel(c.at, asOf)}</td>
              </tr>
            ))}
            {!items.length ? (
              <tr>
                <td colSpan={6} className="mso-empty">
                  No regime changes on closed bars in this window
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Opportunities({ groups }: { groups: OverviewPayload['opportunities'] }) {
  return (
    <section className="mst-card mst-panel mso-bottom">
      <h3 className="is-violet">
        <Lightbulb size={14} /> Opportunity Summary
      </h3>
      <table className="mso-table is-compact">
        <thead>
          <tr>
            <th>Type</th>
            <th className="center">Count</th>
            <th>Examples</th>
          </tr>
        </thead>
        <tbody>
          {groups.map((g) => (
            <tr key={g.key}>
              <td>{g.label}</td>
              <td className="center">
                <b>{g.count}</b>
              </td>
              <td className="mso-muted">{g.examples.length ? g.examples.join(', ') : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mso-foot">Structural context for downstream engines · not trade instructions</p>
    </section>
  );
}

export function StructureOverview({ data, selected, onSelect }: { data: OverviewPayload; selected: string; onSelect: (s: string) => void }) {
  const asOf = data.meta.data_as_of;
  const hours = Number(data.meta.overview_settings?.regime_change_hours ?? 24);
  return (
    <>
      <Kpis data={data} />
      <div className="mso-row2">
        <Donut counts={data.counts} total={data.counts.analysed} />
        <MtfBars mtf={data.mtf} />
        <TopList title="Top 5 Strongest Alignments" icon={<Trophy size={14} />} items={data.strongest} tone="up" />
        <TopList title="Top 5 Weakest Alignments" icon={<TrendingDown size={14} />} items={data.weakest} tone="down" />
      </div>
      <div className="mso-row3">
        <Matrix rows={data.rows} selected={selected} onSelect={onSelect} />
        <Events events={data.events} asOf={asOf} />
      </div>
      <div className="mso-row4">
        <Attention items={data.attention} />
        <RegimeChanges items={data.regime_changes} hours={hours} asOf={asOf} />
        <Opportunities groups={data.opportunities} />
      </div>
    </>
  );
}

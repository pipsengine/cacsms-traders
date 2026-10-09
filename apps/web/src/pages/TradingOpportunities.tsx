import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  CheckCircle2,
  Clock3,
  History,
  Search,
  Shield,
  ShieldAlert,
  Sparkles,
  Star,
  Target,
  XCircle,
} from 'lucide-react';
import { StructureChart, type ChartOverlay } from '../features/market-structure/components/StructureChart';
import { useLive, useLiveCandles } from '../features/market-structure/live';
import { InstrumentIcon } from '../features/market-scanner/components/InstrumentIcon';
import { usePollingAsync } from '../features/market-intelligence/hooks/useMarketIntelligence';
import { autonomousApi } from '../features/autonomous/api';
import { useNow } from '../features/autonomous/components/DetailParts';
import { price, pretty, until } from '../features/autonomous/format';
import type { ChannelLines, Opportunity, OpportunitySummary, Transition } from '../features/autonomous/types';
import { writeHashRoute, type Page } from '../lib/routes';

const PAGE_SIZE = 12;
const CHART_TFS = ['M5', 'M15', 'H1', 'H4', 'D1'] as const;
const LIVE_MS = 5000;

type SortKey = 'symbol' | 'direction' | 'type' | 'tit' | 'stage' | 'state' | 'score' | 'updated';
type InspTab = 'overview' | 'evidence' | 'history';

const STATE_TONE: Record<string, { bg: string; fg: string }> = {
  AWAITING_REACTION: { bg: '#ecfdf3', fg: '#16865a' },
  REACTION_CONFIRMED: { bg: '#ecfdf3', fg: '#16865a' },
  WAITING_FOR_ZONE: { bg: '#fff7ed', fg: '#c2410c' },
  RISK_REVIEW: { bg: '#eff6ff', fg: '#1d4ed8' },
  RISK_DEFERRED: { bg: '#fff7ed', fg: '#c2410c' },
  RISK_APPROVED: { bg: '#f5f3ff', fg: '#7c3aed' },
  EXECUTION_BLOCKED_ANALYSIS_ONLY: { bg: '#f5f3ff', fg: '#7c3aed' },
  INVALIDATED: { bg: '#fff1f1', fg: '#dc2626' },
  EXPIRED: { bg: '#f2f4f7', fg: '#667085' },
  COMPLETED: { bg: '#ecfdf3', fg: '#16865a' },
  RISK_REJECTED: { bg: '#fff1f1', fg: '#dc2626' },
};

function pairOf(symbol: string) {
  if (symbol.startsWith('XAU')) return { base: 'XAU', quote: symbol.slice(3) || 'USD' };
  return { base: symbol.slice(0, 3), quote: symbol.slice(3, 6) };
}

function stamp(iso: string | null | undefined) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false }).format(d);
}

function scoreTone(score: number | null) {
  if (score == null) return 'low';
  if (score >= 80) return 'good';
  if (score >= 60) return 'mid';
  return 'low';
}

function rrText(v: number | null) {
  if (v == null) return '—';
  return `1 : ${v.toFixed(1)}`;
}

function overlayFor(opp: Opportunity, lines: ChannelLines | null, channelDirection: string | null): ChartOverlay {
  const overlay: ChartOverlay = { lines: [], bands: [], levels: [], zones: [] };
  if (lines) {
    const bear = channelDirection === 'DESCENDING' || opp.direction === 'BEARISH';
    overlay.bands!.push({ upper: [lines.upper[0], lines.upper[1]], lower: [lines.lower[0], lines.lower[1]], tone: bear ? 'red' : 'green' });
    overlay.lines!.push(
      { from: lines.upper[0], to: lines.upper[1], tone: 'res', width: 1.5 },
      { from: lines.lower[0], to: lines.lower[1], tone: 'sup', width: 1.5 },
      { from: lines.mid[0], to: lines.mid[1], tone: 'mid', dashed: true },
    );
  }
  const from = opp.origin_at ?? undefined;
  if (opp.entry_lo != null && opp.entry_hi != null) {
    overlay.zones!.push({ lo: Math.min(opp.entry_lo, opp.entry_hi), hi: Math.max(opp.entry_lo, opp.entry_hi), tone: 'blue', from, label: 'Entry / ERZ' });
  }
  if (opp.invalidation != null) overlay.levels!.push({ price: opp.invalidation, tone: 'red', dashed: true, from, label: 'Invalidation' });
  if (opp.target_1 != null) overlay.levels!.push({ price: opp.target_1, tone: 'green', dashed: true, from, label: 'Target 1' });
  if (opp.target_2 != null) overlay.levels!.push({ price: opp.target_2, tone: 'green', dashed: true, from, label: 'Target 2' });
  return overlay;
}

type Finding = { module: string; title: string; detail: string; page: Page };

function evidenceText(v: unknown): string {
  if (v == null || v === '') return '';
  if (typeof v === 'object') {
    if (Array.isArray(v)) return v.map(evidenceText).filter(Boolean).join(', ');
    return Object.entries(v as Record<string, unknown>)
      .map(([key, val]) => `${pretty(key)}: ${evidenceText(val)}`)
      .filter((line) => !line.endsWith(': '))
      .join(' · ');
  }
  return String(v);
}

function findings(evidence: Record<string, unknown>, opp: Opportunity): Finding[] {
  const text = evidenceText;
  const rows: Finding[] = [];
  const push = (module: string, title: string, detail: string, page: Page) => {
    if (detail) rows.push({ module, title, detail, page });
  };
  push('Opportunity Engine', opp.type_label, text(evidence.source) || opp.next_condition || '', 'autonomous-engine');
  push('Strength Intelligence', 'Currency strength', text(evidence.strength), 'strength-intelligence');
  push('Market Structure', 'Trend structure', [text(evidence.trend_state), text(evidence.pullback), evidence.depth_pct != null ? `Depth ${evidence.depth_pct}%` : ''].filter(Boolean).join(' · '), 'market-structure');
  push('Channel Intelligence', 'Channel', [text(evidence.channel_tf), evidence.position != null ? `Position ${evidence.position}` : '', evidence.touches != null ? `${evidence.touches} touches` : '', text(evidence.break_level) ? `Break ${evidence.break_level}` : ''].filter(Boolean).join(' · '), 'channel-intelligence');
  push('Channel Intelligence', opp.tit_level ? `TiT ${opp.tit_level}` : 'Trend-in-Trend', [text(evidence.countertrend_tf), text(evidence.maturity), text(evidence.layer)].filter(Boolean).join(' · '), 'channel-intelligence');
  push('Confirmation', 'Confirmation', text(evidence.confirmation) || text(evidence.reaction), 'autonomous-engine');
  push('Risk & Portfolio', 'Risk', text(evidence.risk), 'risk-portfolio');
  if (!rows.length && opp.next_condition) {
    rows.push({ module: 'Opportunity Engine', title: 'Next condition', detail: opp.next_condition, page: 'autonomous-engine' });
  }
  return rows;
}

export function TradingOpportunities() {
  const now = useNow();
  const [symbol, setSymbol] = useState('');
  const [type, setType] = useState('');
  const [direction, setDirection] = useState('');
  const [timeframe, setTimeframe] = useState('');
  const [stage, setStage] = useState('');
  const [state, setState] = useState('');
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState<{ key: SortKey; dir: 'asc' | 'desc' }>({ key: 'score', dir: 'desc' });
  const [page, setPage] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [tab, setTab] = useState<InspTab>('overview');
  const [tf, setTf] = useState<(typeof CHART_TFS)[number]>('H1');

  const overview = usePollingAsync(useCallback(() => autonomousApi.overview(), []), [], { intervalMs: LIVE_MS });
  const opps = usePollingAsync(useCallback(() => autonomousApi.opportunities('ALL', 400), []), [], { intervalMs: LIVE_MS });

  useEffect(() => {
    let stop = false;
    const tick = () => autonomousApi.catchUp().catch(() => undefined);
    tick();
    const id = window.setInterval(() => { if (!stop && document.visibilityState === 'visible') tick(); }, 15000);
    return () => { stop = true; window.clearInterval(id); };
  }, []);

  const rows = opps.data?.rows ?? [];
  const summary: OpportunitySummary | undefined = opps.data?.summary;
  const symbols = useMemo(() => [...new Set(rows.map((r) => r.symbol))].sort(), [rows]);
  const types = opps.data?.types ?? {};
  const stages = useMemo(() => [...new Set(rows.map((r) => r.stage))], [rows]);
  const states = useMemo(() => [...new Set(rows.map((r) => r.state))].sort(), [rows]);
  const timeframes = useMemo(() => [...new Set(rows.flatMap((r) => [r.trigger_tf, r.parent_tf].filter(Boolean) as string[]))].sort(), [rows]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = rows.filter((r) => {
      if (symbol && r.symbol !== symbol) return false;
      if (type && r.type !== type) return false;
      if (direction && r.direction !== direction) return false;
      if (timeframe && r.trigger_tf !== timeframe && r.parent_tf !== timeframe) return false;
      if (stage && r.stage !== stage) return false;
      if (state && r.state !== state) return false;
      if (!q) return true;
      return [r.symbol, r.type_label, r.stage_label, r.state, r.next_condition, r.tit_level].join(' ').toLowerCase().includes(q);
    });
    const dir = sort.dir === 'asc' ? 1 : -1;
    const value = (r: Opportunity) => {
      switch (sort.key) {
        case 'symbol': return r.symbol;
        case 'direction': return r.direction;
        case 'type': return r.type_label;
        case 'tit': return r.tit_level ?? '';
        case 'stage': return r.stage_number ?? 0;
        case 'state': return r.state;
        case 'score': return r.confidence ?? -1;
        default: return r.updated_at;
      }
    };
    return [...list].sort((a, b) => {
      const av = value(a);
      const bv = value(b);
      if (av < bv) return -1 * dir;
      if (av > bv) return 1 * dir;
      return a.symbol.localeCompare(b.symbol);
    });
  }, [rows, symbol, type, direction, timeframe, stage, state, query, sort]);

  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, pages - 1);
  const shown = filtered.slice(safePage * PAGE_SIZE, safePage * PAGE_SIZE + PAGE_SIZE);
  const selected = filtered.find((r) => r.id === selectedId) ?? shown[0] ?? filtered[0] ?? null;

  useEffect(() => { setPage(0); }, [symbol, type, direction, timeframe, stage, state, query, sort]);
  useEffect(() => {
    if (selected && selected.trigger_tf && (CHART_TFS as readonly string[]).includes(selected.trigger_tf)) {
      setTf(selected.trigger_tf as (typeof CHART_TFS)[number]);
    }
  }, [selected?.id]);

  const history = usePollingAsync(
    useCallback(() => (selected ? autonomousApi.history(selected.id) : Promise.resolve(null)), [selected?.id]),
    [selected?.id],
    { enabled: !!selected, intervalMs: LIVE_MS },
  );
  const activity = usePollingAsync(
    useCallback(() => (selected ? autonomousApi.transitions('OPPORTUNITY', 8, selected.symbol) : Promise.resolve({ rows: [] as Transition[] })), [selected?.symbol]),
    [selected?.symbol],
    { enabled: !!selected, intervalMs: LIVE_MS },
  );
  const chart = usePollingAsync(
    useCallback(() => (selected ? autonomousApi.symbolChart(selected.symbol, tf, 140) : Promise.resolve(null)), [selected?.symbol, tf]),
    [selected?.symbol, tf],
    { enabled: !!selected && tab === 'overview', intervalMs: LIVE_MS },
  );

  const ribbon = overview.data?.ribbon;
  const live = useLive(selected?.symbol ?? null, [tf], !!selected && tab === 'overview');
  const fresh = chart.data && selected && chart.data.symbol === selected.symbol && chart.data.timeframe === tf ? chart.data : null;
  const closed = (fresh?.candles ?? []).map((c) => ({ ...c, v: c.v ?? 0 }));
  const bars = useLiveCandles(`${selected?.symbol}|${tf}`, closed, live.data?.forming?.[tf]);
  const chartOverlay = useMemo(
    () => (selected ? overlayFor(selected, fresh?.channel?.lines ?? null, fresh?.channel?.direction ?? null) : null),
    [selected, fresh],
  );
  const evidence = history.data?.opportunity.evidence ?? {};
  const evidenceRows = selected ? findings(evidence, selected) : [];
  const transitions = history.data?.transitions ?? [];
  const disconnected = ribbon && ['DISCONNECTED', 'OFFLINE'].includes(ribbon.provider_connection);
  const minScore = summary?.high_potential_min_confidence ?? 80;

  function toggleSort(key: SortKey) {
    setSort((cur) => (cur.key === key ? { key, dir: cur.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: key === 'symbol' ? 'asc' : 'desc' }));
  }

  const head = (key: SortKey, label: string) => (
    <th>
      <button type="button" onClick={() => toggleSort(key)}>
        {label}{sort.key === key ? (sort.dir === 'asc' ? ' ↑' : ' ↓') : ''}
      </button>
    </th>
  );

  return (
    <div className="topp">
      <header className="topp-head">
        <div className="topp-title">
          <div className="topp-mark" aria-hidden><Target size={22} /></div>
          <div>
            <h1>Trading Opportunities</h1>
            <p>Autonomous discovery, evaluation and lifecycle monitoring of high-probability market opportunities.</p>
          </div>
        </div>
        <div className="topp-meta">
          <Chip label="Engine Status" value={pretty(ribbon?.system_status)} tone={ribbon?.system_status === 'RUNNING' ? 'ok' : ribbon?.system_status === 'HALTED' || ribbon?.system_status === 'ERROR' ? 'bad' : 'warn'} />
          <Chip label="Market Data" value={pretty(ribbon?.provider_connection)} tone={ribbon?.provider_connection === 'CONNECTED' ? 'ok' : 'warn'} />
          <Chip label="Provider" value={(ribbon?.provider_label || ribbon?.provider || '—').toUpperCase()} />
          <Chip label="Last Update" value={stamp(ribbon?.data_as_of || ribbon?.last_successful_cycle)} />
          <Chip label="Next Analysis" value={until(ribbon?.next_cycle_at, now)} />
          <button type="button" className="topp-history" onClick={() => setTab('history')}><History size={15} /> View History</button>
        </div>
      </header>

      {disconnected ? (
        <div className="topp-banner">
          <AlertTriangle size={16} /> Market data is {pretty(ribbon?.provider_connection).toLowerCase()}. Historical opportunities stay visible. Freshness-dependent progression and authorization are suspended. No orders are sent from this page.
        </div>
      ) : null}
      {opps.error ? <div className="topp-err">{opps.error}</div> : null}

      <section className="topp-kpis" aria-label="Opportunity summary">
        <Kpi className="blue" icon={<Target size={18} />} value={summary?.total} label="Total Opportunities" hint={summary ? `+${summary.created_today} today` : '—'} />
        <Kpi className="green" icon={<Star size={18} />} value={summary?.high_potential} label="High Potential" hint={`≥ ${minScore}% confidence`} />
        <Kpi className="amber" icon={<Clock3 size={18} />} value={summary?.awaiting_conditions} label="Awaiting Conditions" hint="Valid setups still open" />
        <Kpi className="sky" icon={<Shield size={18} />} value={summary?.ready_for_risk} label="Ready for Risk" hint="Risk rules in review" />
        <Kpi className="purple" icon={<Sparkles size={18} />} value={summary?.authorised} label="Authorised" hint="Shadow — execution blocked" />
        <Kpi className="red" icon={<ShieldAlert size={18} />} value={summary?.invalidated} label="Invalidated" hint="Conditions no longer valid" />
      </section>

      <div className="topp-grid">
        <section className="topp-card">
          <div className="topp-filters">
            <Select value={symbol} onChange={setSymbol} label="All Symbols" options={symbols.map((s) => [s, s])} />
            <Select value={type} onChange={setType} label="All Opportunity Types" options={Object.entries(types)} />
            <Select value={direction} onChange={setDirection} label="All Directions" options={[['BULLISH', 'Bullish'], ['BEARISH', 'Bearish']]} />
            <Select value={timeframe} onChange={setTimeframe} label="All Timeframes" options={timeframes.map((s) => [s, s])} />
            <Select value={stage} onChange={setStage} label="All Stages" options={stages.map((s) => [s, pretty(s)])} />
            <Select value={state} onChange={setState} label="All States" options={states.map((s) => [s, pretty(s)])} />
            <label className="topp-search">
              <Search size={14} />
              <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search opportunities…" aria-label="Search opportunities" />
            </label>
          </div>
          <div className="topp-table-wrap">
            <table className="topp-table">
              <thead>
                <tr>
                  <th>#</th>
                  {head('symbol', 'Symbol')}
                  {head('direction', 'Direction')}
                  {head('type', 'Opportunity Type')}
                  {head('tit', 'TiT Level')}
                  {head('stage', 'Stage')}
                  {head('state', 'Current State')}
                  {head('score', 'Score')}
                  <th>Next Condition</th>
                  {head('updated', 'Updated At')}
                </tr>
              </thead>
              <tbody>
                {shown.map((row, i) => {
                  const tone = STATE_TONE[row.state] ?? { bg: '#f2f4f7', fg: '#475467' };
                  const bull = row.direction === 'BULLISH';
                  const score = row.confidence;
                  return (
                    <tr key={row.id} className={selected?.id === row.id ? 'is-on' : ''} onClick={() => setSelectedId(row.id)}>
                      <td>{safePage * PAGE_SIZE + i + 1}</td>
                      <td>
                        <span className="topp-sym">
                          <InstrumentIcon {...pairOf(row.symbol)} size="sm" />
                          {row.symbol}
                        </span>
                      </td>
                      <td><span className={`topp-dir ${bull ? 'up' : 'down'}`}>{bull ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}{bull ? 'Bullish' : 'Bearish'}</span></td>
                      <td>{row.type_label}</td>
                      <td>{row.tit_level ? <span className="topp-pill">{row.tit_level}</span> : '—'}</td>
                      <td><span className="topp-pill" style={{ background: `${row.stage_color ?? '#64748b'}18`, color: row.stage_color ?? '#475467' }}>{row.stage_label ?? pretty(row.stage)}</span></td>
                      <td><span className="topp-pill" style={{ background: tone.bg, color: tone.fg }}>{pretty(row.state)}</span></td>
                      <td>
                        <span className={`topp-score ${scoreTone(score)}`}>
                          <i><b style={{ width: `${Math.max(0, Math.min(100, score ?? 0))}%` }} /></i>
                          {score == null ? '—' : `${Math.round(score)}%`}
                        </span>
                      </td>
                      <td>{row.next_condition || '—'}</td>
                      <td>{stamp(row.updated_at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {!shown.length ? <div className="topp-empty">{opps.loading ? 'Loading opportunities…' : 'No opportunities match these filters. The engine creates them from closed-bar evidence. Waiting is a valid state.'}</div> : null}
          </div>
          <div className="topp-page">
            <span>Showing {shown.length ? safePage * PAGE_SIZE + 1 : 0}–{safePage * PAGE_SIZE + shown.length} of {filtered.length}</span>
            <div>
              {Array.from({ length: pages }, (_, n) => (
                <button type="button" key={n} className={n === safePage ? 'is-on' : ''} onClick={() => setPage(n)}>{n + 1}</button>
              ))}
            </div>
          </div>
          {summary ? <p className="topp-note">{summary.ranking_note}</p> : null}
        </section>

        <aside className="topp-card topp-insp">
          {selected ? (
            <>
              <div className="topp-insp-head">
                <div>
                  <h2>
                    <InstrumentIcon {...pairOf(selected.symbol)} size="sm" />
                    {selected.symbol}
                    {(selected.confidence ?? 0) >= minScore ? <span className="topp-pill" style={{ background: '#ecfdf3', color: '#16865a' }}>High Potential</span> : null}
                    {selected.status === 'CLOSED' ? <span className="topp-pill">Historical</span> : null}
                  </h2>
                  <p>{selected.tit_level ? `TiT ${pretty(selected.type)} (${selected.tit_level})` : selected.type_label} · {selected.direction === 'BULLISH' ? 'Bullish' : 'Bearish'}</p>
                </div>
                <div className="topp-score-lg">
                  <span>Opportunity Score</span>
                  <b style={{ color: scoreTone(selected.confidence) === 'good' ? '#16865a' : scoreTone(selected.confidence) === 'mid' ? '#d97706' : '#64748b' }}>
                    {selected.confidence == null ? '—' : `${Math.round(selected.confidence)}%`}
                  </b>
                </div>
              </div>
              <div className="topp-tabs" role="tablist">
                {([['overview', 'Overview'], ['evidence', 'Decision Evidence'], ['history', 'Lifecycle History']] as const).map(([id, label]) => (
                  <button type="button" key={id} role="tab" aria-selected={tab === id} className={tab === id ? 'is-on' : ''} onClick={() => setTab(id)}>{label}</button>
                ))}
              </div>
              <div className="topp-body">
                {tab === 'overview' ? (
                  <>
                    <div className="topp-chart">
                      <div className="topp-tf" role="tablist" aria-label="Chart timeframe">
                        {CHART_TFS.map((name) => (
                          <button type="button" key={name} className={tf === name ? 'is-on' : ''} onClick={() => setTf(name)}>{name}</button>
                        ))}
                      </div>
                      <StructureChart
                        symbol={selected.symbol}
                        title={selected.symbol}
                        tf={tf}
                        candles={bars}
                        digits={selected.digits}
                        lastPrice={live.data?.quote && !live.data.quote.stale ? live.data.quote.price : selected.current_price}
                        height={230}
                        loading={chart.loading && !bars.length}
                        error={chart.error}
                        heading={<></>}
                        overlay={chartOverlay}
                        showVolume={false}
                        compact
                        zoomable
                      />
                    </div>
                    <div className="topp-facts">
                      <Fact label="Direction" value={selected.direction === 'BULLISH' ? 'Bullish' : 'Bearish'} />
                      <Fact label="Current Stage" value={selected.stage_label ?? pretty(selected.stage)} />
                      <Fact label="Current State" value={pretty(selected.state)} />
                      <Fact label="Opportunity Type" value={selected.type_label} />
                      <Fact label="TiT Level" value={selected.tit_level ?? '—'} />
                      <Fact label="Timeframe" value={`${selected.trigger_tf ?? '—'} (Parent: ${selected.parent_tf ?? '—'})`} />
                      <Fact label="Entry Zone" value={selected.entry_lo != null && selected.entry_hi != null ? `${price(selected.entry_lo, selected.digits)} – ${price(selected.entry_hi, selected.digits)}` : '—'} />
                      <Fact label="Current Price" value={price(selected.current_price, selected.digits)} />
                      <Fact label="Invalidation" value={price(selected.invalidation, selected.digits)} />
                      <Fact label="Confidence" value={selected.confidence == null ? '—' : `${Math.round(selected.confidence)}%`} />
                      <Fact label="Risk : Reward (est.)" value={rrText(selected.reward_risk)} />
                      <Fact label="Next Condition" value={selected.next_condition || '—'} />
                    </div>
                  </>
                ) : null}
                {tab === 'evidence' ? (
                  <div className="topp-ev">
                    {evidenceRows.map((row) => (
                      <article key={`${row.module}-${row.title}`}>
                        <header>
                          <h3>{row.title}</h3>
                          <button type="button" className="topp-link" onClick={() => writeHashRoute(row.page)}>{row.module}</button>
                        </header>
                        <p>{row.detail}</p>
                      </article>
                    ))}
                    {!evidenceRows.length ? <div className="topp-empty">No persisted evidence for this opportunity yet.</div> : null}
                  </div>
                ) : null}
                {tab === 'history' ? (
                  <div className="topp-life">
                    {transitions.map((t) => (
                      <article key={t.id}>
                        <time>{stamp(t.created_at)}</time>
                        <div>
                          <b>{pretty(t.to_stage)} · {pretty(t.to_state)}</b>
                          <p>{t.detail || pretty(t.reason_code)}</p>
                        </div>
                      </article>
                    ))}
                    {!transitions.length ? <div className="topp-empty">{history.loading ? 'Loading history…' : 'No transitions recorded yet.'}</div> : null}
                  </div>
                ) : null}
              </div>
            </>
          ) : (
            <div className="topp-empty">Select an opportunity to inspect its chart, evidence and history.</div>
          )}
        </aside>
      </div>

      <section className="topp-lower">
        <div className="topp-card">
          <h3>Recent Activity{selected ? ` (${selected.symbol})` : ''} <button type="button" onClick={() => setTab('history')}>View All</button></h3>
          <ul>
            {(activity.data?.rows ?? []).slice(0, 4).map((t) => (
              <li key={t.id}>
                <time>{stamp(t.created_at).split(' ').slice(-1)[0]}</time>
                <div><b>{pretty(t.to_stage)}</b><div>{t.detail || pretty(t.reason_code)}</div></div>
                <span className="topp-pill">{t.to_state === selected?.state ? 'Pending' : 'Completed'}</span>
              </li>
            ))}
            {!activity.data?.rows.length ? <li><span /><span>No recorded activity for this symbol yet.</span><span /></li> : null}
          </ul>
        </div>
        <div className="topp-card">
          <h3>Key Evidence</h3>
          <div style={{ padding: '4px 14px 12px' }}>
            {evidenceRows.slice(0, 5).map((row) => (
              <div className="topp-check ok" key={`${row.title}-k`}><CheckCircle2 size={15} /> <span><b>{row.title}.</b> {row.detail}</span></div>
            ))}
            {!evidenceRows.length ? <div className="topp-empty">Evidence appears after the engine records a hypothesis.</div> : null}
          </div>
        </div>
        <div className="topp-card">
          <h3>Next Expected Events</h3>
          <div style={{ padding: '4px 14px 12px' }}>
            {selected?.next_condition ? <div className="topp-check wait"><Clock3 size={15} /> <span>{selected.next_condition}</span></div> : null}
            {selected?.invalidation != null ? <div className="topp-check" style={{ color: '#dc2626' }}><XCircle size={15} /> <span>Invalidation {selected.direction === 'BEARISH' ? 'above' : 'below'} {price(selected.invalidation, selected.digits)}</span></div> : null}
            {selected?.target_1 != null ? <div className="topp-check wait"><Clock3 size={15} /> <span>Target zone 1: {price(selected.target_1, selected.digits)}</span></div> : null}
            {selected?.target_2 != null ? <div className="topp-check wait"><Clock3 size={15} /> <span>Target zone 2: {price(selected.target_2, selected.digits)}</span></div> : null}
            {(selected?.blockers ?? []).map((b) => <div className="topp-check" key={b} style={{ color: '#b45309' }}><AlertTriangle size={15} /> <span>{b}</span></div>)}
            {!selected ? <div className="topp-empty">No open opportunity selected.</div> : null}
          </div>
        </div>
      </section>
    </div>
  );
}

function Chip({ label, value, tone }: { label: string; value: string; tone?: 'ok' | 'warn' | 'bad' }) {
  return (
    <div className="topp-chip">
      <span>{label}</span>
      <b>{tone ? <i className={`topp-dot ${tone}`} /> : null}{value}</b>
    </div>
  );
}

function Kpi({ className, icon, value, label, hint }: { className: string; icon: ReactNode; value: number | undefined; label: string; hint: string }) {
  return (
    <article className={`topp-kpi ${className}`}>
      <i>{icon}</i>
      <div>
        <b>{value == null ? '—' : value}</b>
        <span>{label}</span>
        <small>{hint}</small>
      </div>
    </article>
  );
}

function Select({ value, onChange, label, options }: { value: string; onChange: (v: string) => void; label: string; options: [string, string][] }) {
  return (
    <select aria-label={label} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">{label}</option>
      {options.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
    </select>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return <div><span>{label}</span><b>{value}</b></div>;
}

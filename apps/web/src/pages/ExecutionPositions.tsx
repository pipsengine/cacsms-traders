import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Activity, CheckCircle2, Clock3, Crosshair, History, Inbox, Rocket, Shield, ShieldCheck, Timer, XCircle, Zap } from 'lucide-react';
import { usePollingAsync } from '../features/market-intelligence/hooks/useMarketIntelligence';
import { autonomousApi } from '../features/autonomous/api';
import { pretty } from '../features/autonomous/format';
import type { ExecutionBook, ExecutionEvent, PortfolioView, ShadowPlan } from '../features/autonomous/types';

const TABS = [
  { id: 'monitor', label: 'Execution Monitor', icon: Activity },
  { id: 'positions', label: 'Position Management', icon: Inbox },
  { id: 'history', label: 'Execution History', icon: History },
] as const;
type TabId = (typeof TABS)[number]['id'];
const COLORS = ['#22c55e', '#3b82f6', '#a855f7', '#f59e0b', '#ef4444', '#14b8a6'];

function when(iso: string | null | undefined, seconds = false) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return new Intl.DateTimeFormat('en-GB', {
    day: '2-digit', month: 'short', year: seconds ? 'numeric' : undefined,
    hour: '2-digit', minute: '2-digit', second: seconds ? '2-digit' : undefined, hour12: false,
  }).format(d);
}

function clock(iso: string | null | undefined) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(d);
}

function px(symbol: string | null | undefined, value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return '—';
  const digits = !symbol ? 5 : symbol.startsWith('XAU') ? 2 : symbol.endsWith('JPY') ? 3 : 5;
  return value.toFixed(digits);
}

function money(value: number | null | undefined, currency = 'USD') {
  if (value == null || !Number.isFinite(value)) return '—';
  return new Intl.NumberFormat('en-US', { style: 'currency', currency, maximumFractionDigits: 2 }).format(value);
}

function side(direction: string | null) {
  if (direction === 'BULLISH') return { label: 'Buy', tone: 'buy' };
  if (direction === 'BEARISH') return { label: 'Sell', tone: 'sell' };
  return { label: '—', tone: 'muted' };
}

export function ExecutionPositions() {
  const [tab, setTab] = useState<TabId>('monitor');
  const [query, setQuery] = useState('');
  const [symbol, setSymbol] = useState<string | null>(null);
  const overview = usePollingAsync(useCallback(() => autonomousApi.overview(), []), [], { intervalMs: 5000 });
  const book = usePollingAsync(useCallback(() => autonomousApi.execution(), []), [], { intervalMs: 5000 });
  const portfolio = usePollingAsync(useCallback(() => autonomousApi.portfolio(), []), [], { intervalMs: 5000 });
  useEffect(() => {
    const id = window.setInterval(() => { if (document.visibilityState === 'visible') autonomousApi.catchUp().catch(() => undefined); }, 15000);
    autonomousApi.catchUp().catch(() => undefined);
    return () => window.clearInterval(id);
  }, []);

  const view = book.data;
  const ribbon = overview.data?.ribbon;
  const safety = overview.data?.safety;
  const account = portfolio.data?.account;
  const needle = query.trim().toUpperCase();
  const plans = useMemo(() => (view?.plans || []).filter((row) => !needle || (row.symbol || '').includes(needle)), [view, needle]);
  const focus = symbol || plans[0]?.symbol || view?.events[0]?.symbol || null;

  return (
    <div className="exm">
      <header className="exm-head">
        <div className="exm-title">
          <div className="exm-mark" aria-hidden><Rocket size={20} /></div>
          <div>
            <h1>Execution & Positions</h1>
            <p>Execute authorized opportunities, manage open positions and track trading performance — autonomous and risk controlled.</p>
          </div>
        </div>
        <div className="exm-status">
          <Chip k="Execution Engine" v={ribbon?.system_status === 'RUNNING' ? 'RUNNING' : pretty(ribbon?.system_status)} s={ribbon?.engine_version || 'Stage 9'} ok={ribbon?.system_status === 'RUNNING'} />
          <Chip k="Safety Supervisor" v={safety?.status === 'NORMAL' ? 'OPERATIONAL' : pretty(safety?.status)} s={safety?.status === 'NORMAL' ? 'All limits enforced' : 'Check supervisor'} ok={safety?.status === 'NORMAL'} />
          <Chip k="Operating Mode" v={(ribbon?.operating_mode || 'SHADOW').replaceAll('_', ' ')} s="Analysis only" shield />
          <Chip k="Active Broker" v={ribbon?.provider_label === 'MT5' ? 'MetaTrader 5' : (ribbon?.provider_label || '—')} s={account?.environment ? `${account.environment} account` : 'Market data'} />
          <Chip k="Connection" v={ribbon?.provider_connection === 'CONNECTED' ? 'CONNECTED' : pretty(ribbon?.provider_connection)} s="Latency not measured" ok={ribbon?.provider_connection === 'CONNECTED'} />
          <Chip k="Last Reconciliation" v={when(view?.last_cycle_at, true)} s="Engine cycle" clock />
        </div>
      </header>

      <div className="exm-tabs" role="tablist">
        {TABS.map((item) => {
          const Icon = item.icon;
          return <button type="button" key={item.id} className={tab === item.id ? 'is-on' : ''} onClick={() => setTab(item.id)}><Icon size={15} />{item.label}</button>;
        })}
      </div>

      {(safety?.status === 'CRITICAL' || safety?.status === 'HALTED') ? <div className="exm-banner"><ShieldCheck size={16} /> The safety supervisor is {pretty(safety?.status)}. No broker order is submitted.</div> : null}
      {book.error ? <div className="exm-banner">{book.error}</div> : null}

      {tab === 'monitor' && view ? <Monitor view={view} plans={plans} query={query} onQuery={setQuery} focus={focus} onFocus={setSymbol} /> : null}
      {tab === 'positions' && view ? <Positions view={view} plans={plans} portfolio={portfolio.data} query={query} onQuery={setQuery} /> : null}
      {tab === 'history' && view ? <HistoryPanel view={view} query={query} onQuery={setQuery} /> : null}
      {!view && book.loading ? <div className="exm-empty">Loading the execution book…</div> : null}
    </div>
  );
}

function Monitor({ view, plans, query, onQuery, focus, onFocus }: { view: ExecutionBook; plans: ShadowPlan[]; query: string; onQuery: (v: string) => void; focus: string | null; onFocus: (s: string) => void }) {
  const attempts = view.shadow.blocked_30d;
  const rate = attempts ? (100 * view.shadow.target_1) / attempts : null;
  const flow = view.events.filter((row) => row.symbol === focus).slice().reverse();
  return (
    <>
      <section className="exm-kpis">
        <Kpi icon={<CheckCircle2 size={16} />} tone="green" label="Authorized for Execution" value={String(view.shadow.open_plans)} hint="Ready (Stage 8)" />
        <Kpi icon={<Clock3 size={16} />} tone="blue" label="Pending Orders" value={String(view.broker.pending_orders)} hint="Awaiting broker response" />
        <Kpi icon={<Zap size={16} />} tone="green" label="Orders Executed (Today)" value={String(view.broker.fills)} hint="No broker fills" />
        <Kpi icon={<XCircle size={16} />} tone="red" label="Rejected / Failed" value={String(view.shadow.stopped)} hint={view.shadow.stopped ? 'Shadow stops' : 'No rejections'} />
        <Kpi icon={<Crosshair size={16} />} tone="violet" label="Execution Success Rate" value={rate == null ? '—' : `${rate.toFixed(0)}%`} hint="Shadow targets / attempts" />
        <Kpi icon={<Timer size={16} />} tone="blue" label="Avg. Execution Time" value="—" hint="Not recorded" />
      </section>

      <section className="exm-row queue">
        <article className="exm-card">
          <h2>Authorized Campaigns Queue (Stage 8 → 9)
            <span className="exm-tools">
              <input value={query} onChange={(e) => onQuery(e.target.value)} placeholder="Search symbol or campaign…" aria-label="Search campaigns" />
            </span>
          </h2>
          <p className="exm-sub">Opportunities held after authorization. Orders are not submitted while the mode is SHADOW.</p>
          <div className="exm-table-wrap">
            <table className="exm-table">
              <thead>
                <tr><th>#</th><th>Symbol</th><th>Direction</th><th>Type</th><th>Volume</th><th>Entry Price</th><th>SL</th><th>TP</th><th>Status</th><th>Next Action</th><th>ETA</th></tr>
              </thead>
              <tbody>
                {plans.map((row, i) => (
                  <tr key={row.id} className={row.symbol === focus ? 'is-on' : ''} onClick={() => row.symbol && onFocus(row.symbol)}>
                    <td>{i + 1}</td>
                    <td className="exm-sym">{row.symbol}</td>
                    <td><span className={`exm-pill ${side(row.direction).tone}`}>{side(row.direction).label}</span></td>
                    <td>{row.type_label || '—'}</td>
                    <td>—</td>
                    <td>{px(row.symbol, row.entry_reference)}</td>
                    <td>{px(row.symbol, row.invalidation)}</td>
                    <td>{px(row.symbol, row.target_1)}</td>
                    <td><span className="exm-pill held">HELD</span></td>
                    <td>No broker submit</td>
                    <td>—</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!plans.length ? <div className="exm-empty">No authorized shadow plans.</div> : null}
          </div>
        </article>
        <article className="exm-card">
          <h2>Order Execution Flow ({focus || '—'}) <span className="exm-live">SHADOW</span></h2>
          <div className="exm-flow">
            {flow.length ? flow.map((step, index) => <Step key={step.id} step={step} last={index === flow.length - 1} />) : <div className="exm-empty">No recorded step for this symbol.</div>}
          </div>
        </article>
      </section>

      <section className="exm-row mid">
        <article className="exm-card">
          <h2>Execution Performance <span className="exm-legend-inline"><span><i style={{ background: '#60a5fa' }} />Held</span><span><i style={{ background: '#4ade80' }} />Resolved</span></span></h2>
          <Bars days={view.daily} />
          <p className="exm-note">Seven recorded days. There is no intraday fill series.</p>
        </article>
        <article className="exm-card">
          <h2>Execution Quality</h2>
          <div className="exm-metrics">
            <div><span>Avg. Slippage</span><b>—</b></div>
            <div><span>Avg. Fill Time</span><b>—</b></div>
            <div><span>Success Rate</span><b>{rate == null ? '—' : `${rate.toFixed(0)}%`}</b></div>
            <div><span>Rejection Rate</span><b>{attempts ? `${((100 * view.shadow.stopped) / attempts).toFixed(0)}%` : '—'}</b></div>
          </div>
          <Quality plans={view.plans} />
        </article>
        <article className="exm-card">
          <h2>Order Status Distribution</h2>
          <Donut parts={[
            { label: 'Filled', value: view.broker.fills, color: '#22c55e' },
            { label: 'Pending', value: view.shadow.open_plans, color: '#f59e0b' },
            { label: 'Rejected', value: view.shadow.stopped, color: '#ef4444' },
            { label: 'Cancelled', value: 0, color: '#94a3b8' },
          ]} center={String(view.shadow.open_plans + view.broker.fills + view.shadow.stopped)} caption="Plans" />
        </article>
      </section>

      <section className="exm-row low">
        <article className="exm-card">
          <h2>Recent Execution Events</h2>
          <Events events={view.events.slice(0, 6)} />
        </article>
        <article className="exm-card">
          <h2>Pending Orders Queue</h2>
          <div className="exm-empty center">No broker orders are working. SHADOW does not leave an order at the broker.</div>
        </article>
      </section>
    </>
  );
}

function Positions({ view, plans, portfolio, query, onQuery }: { view: ExecutionBook; plans: ShadowPlan[]; portfolio: PortfolioView | null; query: string; onQuery: (v: string) => void }) {
  const currency = portfolio?.account?.currency || 'USD';
  const limits = portfolio?.limits;
  const bySymbol = new Map<string, number>();
  for (const plan of view.plans) bySymbol.set(plan.symbol || '—', (bySymbol.get(plan.symbol || '—') || 0) + 1);
  const slices = [...bySymbol.entries()].map(([label, value], i) => ({ label, value, color: COLORS[i % COLORS.length] }));
  return (
    <>
      <section className="exm-kpis">
        <Kpi icon={<Activity size={16} />} tone="amber" label="Shadow Positions" value={String(view.shadow.open_plans)} hint="Simulated" />
        <Kpi icon={<Inbox size={16} />} tone="blue" label="Broker Positions" value={String(view.broker.open_positions)} hint="Live / Demo / Prop" />
        <Kpi icon={<Crosshair size={16} />} tone="blue" label="Total Exposure" value="—" hint="Not sized in currency" />
        <Kpi icon={<Zap size={16} />} tone="green" label="Floating P&L (Shadow)" value="—" hint="No lot value" />
        <Kpi icon={<CheckCircle2 size={16} />} tone="green" label="Floating P&L (Broker)" value={money(portfolio?.account?.floating_pnl, currency)} hint="Equity − balance" />
        <Kpi icon={<Timer size={16} />} tone="red" label="Open Risk (R)" value="—" hint="Not sized" />
      </section>
      <section className="exm-row pos">
        <article className="exm-card">
          <h2>Shadow Positions ({plans.length}) <span className="exm-live">SIMULATED</span></h2>
          <p className="exm-sub">These plans are tracked in SHADOW. Stage 10 does not send a modify or close.</p>
          <span className="exm-tools"><input value={query} onChange={(e) => onQuery(e.target.value)} placeholder="Search symbol…" aria-label="Search positions" /></span>
          <div className="exm-table-wrap">
            <table className="exm-table">
              <thead>
                <tr><th>#</th><th>Symbol</th><th>Direction</th><th>Volume</th><th>Entry Price</th><th>Current Price</th><th>SL</th><th>TP</th><th>P&L (USD)</th><th>R-Multiple</th><th>Status</th><th>Next Action</th></tr>
              </thead>
              <tbody>
                {plans.map((row, i) => (
                  <tr key={row.id}>
                    <td>{i + 1}</td>
                    <td className="exm-sym">{row.symbol}</td>
                    <td><span className={`exm-pill ${side(row.direction).tone}`}>{side(row.direction).label}</span></td>
                    <td>—</td>
                    <td>{px(row.symbol, row.entry_reference)}</td>
                    <td>{px(row.symbol, row.current_price)}</td>
                    <td>{px(row.symbol, row.invalidation)}</td>
                    <td>{px(row.symbol, row.target_1)}</td>
                    <td>—</td>
                    <td>{row.unrealized_r == null ? '—' : `${row.unrealized_r.toFixed(2)} R`}</td>
                    <td><span className={`exm-pill ${row.price_status === 'STALE' ? 'held' : 'sim'}`}>{row.price_status === 'STALE' ? 'STALE' : 'SIMULATED'}</span></td>
                    <td>No broker action</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!plans.length ? <div className="exm-empty">No simulated positions.</div> : null}
          </div>
        </article>
        <article className="exm-card">
          <h2>Broker Positions (0) <span className="exm-pill muted">SHADOW</span></h2>
          <div className="exm-empty center">No broker positions.<br />All trade execution is disabled in SHADOW mode.<br />Stage 10 will manage broker positions only when execution is enabled.</div>
        </article>
      </section>
      <section className="exm-row mid">
        <article className="exm-card">
          <h2>Position Performance</h2>
          <div className="exm-empty">No shadow P&L time series is stored. Dollar curves are not estimated.</div>
        </article>
        <article className="exm-card">
          <h2>Position Distribution</h2>
          <Donut parts={slices.length ? slices : [{ label: 'None', value: 0, color: '#e8eef6' }]} center={String(view.shadow.open_plans)} caption="Plans" />
        </article>
        <article className="exm-card">
          <h2>Position Risk & Limits</h2>
          <Limit label="Shadow plans" current={view.shadow.open_plans} limit={limits?.max_concurrent ?? null} />
          <Limit label="Currency exposure" current={portfolio?.exposure.plans ?? null} limit={limits?.max_currency_exposure ?? null} />
          <Limit label="Broker positions" current={0} limit={limits?.max_open_positions ?? null} />
          <div className="exm-limit"><span>Max trade risk</span><b>{limits?.max_trade_risk_pct == null ? '—' : `${limits.max_trade_risk_pct}%`}</b></div>
          <div className="exm-limit"><span>Max total risk</span><b>{limits?.max_total_risk_pct == null ? '—' : `${limits.max_total_risk_pct}%`}</b></div>
          <p className="exm-note">Dollar exposure and margin-at-risk are not sized.</p>
        </article>
      </section>
      <section className="exm-row low">
        <article className="exm-card">
          <h2>Recent Position Actions</h2>
          <Events events={view.events.slice(0, 6)} />
        </article>
        <article className="exm-card">
          <h2>Autonomous Position Management <span className="exm-pill held">INACTIVE</span></h2>
          <Rule name="Break-even" detail="Not applied" />
          <Rule name="Trailing stop" detail="Not applied" />
          <Rule name="Partial close" detail="Not applied" />
          <Rule name="Time exit" detail="Not applied" />
          <Rule name="Structure invalidation" detail="Closed-bar tracking only" />
          <p className="exm-note">These rules do not modify a broker position while submission is blocked.</p>
        </article>
      </section>
    </>
  );
}

function eventName(result: string) {
  if (result === 'NOT_SUBMITTED') return 'Authorization held';
  if (result === 'SHADOW_TARGET') return 'Shadow target';
  if (result === 'SHADOW_STOP') return 'Shadow stop';
  return pretty(result);
}

function HistoryPanel({ view, query, onQuery }: { view: ExecutionBook; query: string; onQuery: (v: string) => void }) {
  const [symbol, setSymbol] = useState('ALL');
  const [kind, setKind] = useState('ALL');
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const symbols = [...new Set(view.events.map((row) => row.symbol).filter(Boolean))] as string[];
  const needle = query.trim().toUpperCase();
  const filtered = view.events.filter((row) => {
    if (symbol !== 'ALL' && row.symbol !== symbol) return false;
    if (kind !== 'ALL' && row.result !== kind) return false;
    if (needle && !(row.symbol || '').includes(needle) && !(row.detail || '').toUpperCase().includes(needle)) return false;
    return true;
  });
  const pageSize = 10;
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const safePage = Math.min(page, pages - 1);
  const slice = filtered.slice(safePage * pageSize, safePage * pageSize + pageSize);
  const current = filtered.find((row) => row.id === selected) || slice[0] || null;
  const held = view.events.filter((row) => row.result === 'NOT_SUBMITTED').length;
  const filled = view.events.filter((row) => row.result === 'SHADOW_TARGET').length;
  const rejected = view.events.filter((row) => row.result === 'SHADOW_STOP').length;
  const total = view.events.length;
  const exportRows = () => {
    const header = ['time', 'symbol', 'event', 'detail', 'result'];
    const lines = [header.join(',')].concat(filtered.map((row) => [row.at, row.symbol, eventName(row.result), row.detail, row.result].map((cell) => `"${String(cell ?? '').replaceAll('"', '""')}"`).join(',')));
    const blob = new Blob([lines.join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'execution-history.csv';
    link.click();
    URL.revokeObjectURL(url);
  };
  return (
    <>
      <section className="exm-kpis">
        <Kpi icon={<History size={16} />} tone="blue" label="Total Events" value={String(total)} hint="Recorded shadow steps" />
        <Kpi icon={<Zap size={16} />} tone="blue" label="Orders Submitted" value="0" hint="None sent to the broker" />
        <Kpi icon={<CheckCircle2 size={16} />} tone="green" label="Orders Filled" value={String(filled)} hint={total ? `${((100 * filled) / total).toFixed(1)}% shadow targets` : 'No fills'} />
        <Kpi icon={<XCircle size={16} />} tone="red" label="Orders Rejected" value={String(rejected)} hint={total ? `${((100 * rejected) / total).toFixed(1)}% shadow stops` : 'No rejections'} />
        <Kpi icon={<Activity size={16} />} tone="amber" label="Avg. Slippage" value="—" hint="Not recorded" />
        <Kpi icon={<Timer size={16} />} tone="blue" label="Avg. Execution Time" value="—" hint="Not recorded" />
      </section>
      <section className="exm-row queue">
        <article className="exm-card">
          <h2>Execution History</h2>
          <p className="exm-sub">Recorded authorization holds, shadow targets and shadow stops. Broker order ids, volumes and fills are not on this ledger. Held in this set: {held}.</p>
          <div className="exm-tools" style={{ marginBottom: 10 }}>
            <select value={symbol} onChange={(e) => { setSymbol(e.target.value); setPage(0); }} aria-label="Symbol">
              <option value="ALL">All Symbols</option>
              {symbols.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
            <select value={kind} onChange={(e) => { setKind(e.target.value); setPage(0); }} aria-label="Event type">
              <option value="ALL">All Event Types</option>
              <option value="NOT_SUBMITTED">Authorization held</option>
              <option value="SHADOW_TARGET">Shadow target</option>
              <option value="SHADOW_STOP">Shadow stop</option>
            </select>
            <input value={query} onChange={(e) => { onQuery(e.target.value); setPage(0); }} placeholder="Search symbol or detail…" aria-label="Search history" />
            <button type="button" className="exm-link" onClick={exportRows}>Export</button>
          </div>
          <div className="exm-table-wrap">
            <table className="exm-table">
              <thead>
                <tr><th>#</th><th>Time</th><th>Symbol</th><th>Event</th><th>Order ID</th><th>Details</th><th>Volume</th><th>Price</th><th>Status</th><th>Source</th></tr>
              </thead>
              <tbody>
                {slice.map((row, index) => (
                  <tr key={row.id} className={current?.id === row.id ? 'is-on' : ''} onClick={() => setSelected(row.id)}>
                    <td>{safePage * pageSize + index + 1}</td>
                    <td>{clock(row.at)}</td>
                    <td className="exm-sym">{row.symbol || '—'}</td>
                    <td>{eventName(row.result)}</td>
                    <td>—</td>
                    <td>{row.detail || pretty(row.reason_code)}</td>
                    <td>—</td>
                    <td>{px(row.symbol, row.reference_price)}</td>
                    <td><span className={`exm-pill ${row.result === 'SHADOW_TARGET' ? 'ok' : row.result === 'SHADOW_STOP' ? 'bad' : 'sim'}`}>{row.result === 'SHADOW_TARGET' ? 'Target' : row.result === 'SHADOW_STOP' ? 'Stop' : 'Simulated'}</span></td>
                    <td><span className="exm-pill sim">Simulated</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!slice.length ? <div className="exm-empty">No events match these filters.</div> : null}
          </div>
          <div className="exm-pager">
            <span>Showing {filtered.length ? safePage * pageSize + 1 : 0} to {Math.min(filtered.length, safePage * pageSize + pageSize)} of {filtered.length}</span>
            <span>
              <button type="button" disabled={safePage === 0} onClick={() => setPage(safePage - 1)}>‹</button>
              <b>{safePage + 1}</b>
              <button type="button" disabled={safePage >= pages - 1} onClick={() => setPage(safePage + 1)}>›</button>
            </span>
          </div>
        </article>
        <article className="exm-card">
          <h2>Event Details {current ? <button type="button" className="exm-link" onClick={() => setSelected(null)}>Clear</button> : null}</h2>
          {current ? <Detail event={current} plan={view.plans.find((row) => row.symbol === current.symbol) || null} /> : <div className="exm-empty">Select an event.</div>}
        </article>
      </section>
      <section className="exm-row mid">
        <article className="exm-card">
          <h2>Execution Events by Type</h2>
          <Donut parts={[
            { label: 'Held', value: held, color: '#7c3aed' },
            { label: 'Target', value: filled, color: '#22c55e' },
            { label: 'Stop', value: rejected, color: '#ef4444' },
          ]} center={String(total)} caption="Events" />
        </article>
        <article className="exm-card">
          <h2>Execution Timeline <span className="exm-legend-inline"><span><i style={{ background: '#60a5fa' }} />Held</span></span></h2>
          <HourBars events={view.events} />
          <p className="exm-note">Hours with a recorded event. Empty hours are omitted.</p>
        </article>
        <article className="exm-card">
          <h2>Execution Quality</h2>
          <div className="exm-metrics">
            <div><span>Avg. Slippage</span><b>—</b></div>
            <div><span>Avg. Fill Time</span><b>—</b></div>
            <div><span>Success Rate</span><b>{total ? `${((100 * filled) / total).toFixed(0)}%` : '—'}</b></div>
            <div><span>Rejection Rate</span><b>{total ? `${((100 * rejected) / total).toFixed(0)}%` : '—'}</b></div>
          </div>
          <TopSymbols events={view.events} />
        </article>
      </section>
    </>
  );
}

function Detail({ event, plan }: { event: ExecutionEvent; plan: ShadowPlan | null }) {
  const rows: [string, string][] = [
    ['Time', when(event.at, true)],
    ['Order ID', '—'],
    ['Symbol', event.symbol || '—'],
    ['Side', side(event.direction).label],
    ['Volume', '—'],
    ['Reference', px(event.symbol, event.reference_price)],
    ['Current', px(event.symbol, plan?.current_price)],
    ['Stop', px(event.symbol, plan?.invalidation)],
    ['Target', px(event.symbol, plan?.target_1)],
    ['R', plan?.unrealized_r == null ? '—' : plan.unrealized_r.toFixed(2)],
    ['Status', eventName(event.result)],
    ['Source', 'Simulated'],
    ['Execution time', '—'],
    ['Reason', event.detail || pretty(event.reason_code)],
  ];
  return (
    <div className="exm-detail-list">
      {rows.map(([label, value]) => <div key={label}><span>{label}</span><b>{value}</b></div>)}
    </div>
  );
}

function HourBars({ events }: { events: ExecutionEvent[] }) {
  const buckets = new Map<string, number>();
  for (const event of events) {
    if (!event.at) continue;
    const d = new Date(event.at);
    if (Number.isNaN(d.getTime())) continue;
    const key = `${String(d.getHours()).padStart(2, '0')}:00`;
    buckets.set(key, (buckets.get(key) || 0) + 1);
  }
  const rows = [...buckets.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  if (!rows.length) return <div className="exm-empty">No timed events.</div>;
  const max = Math.max(1, ...rows.map(([, n]) => n));
  return (
    <div className="exm-chart">
      <div className="exm-yaxis"><span>{max}</span><span>{Math.round(max / 2)}</span><span>0</span></div>
      <div className="exm-plot">
        {rows.map(([hour, count]) => (
          <div className="exm-bar" key={hour}>
            <i style={{ height: `${(count / max) * 100}%` }} />
            <span>{hour.slice(0, 2)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function TopSymbols({ events }: { events: ExecutionEvent[] }) {
  const counts = new Map<string, number>();
  for (const event of events) counts.set(event.symbol || '—', (counts.get(event.symbol || '—') || 0) + 1);
  const rows = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5);
  return (
    <table className="exm-table">
      <thead><tr><th>Symbol</th><th>Events</th><th>Slippage</th><th>Fill</th></tr></thead>
      <tbody>
        {rows.map(([sym, n]) => <tr key={sym}><td className="exm-sym">{sym}</td><td>{n}</td><td>—</td><td>—</td></tr>)}
      </tbody>
    </table>
  );
}

function Events({ events }: { events: ExecutionEvent[] }) {
  return (
    <div className="exm-table-wrap">
      <table className="exm-table">
        <thead><tr><th>Time</th><th>Symbol</th><th>Event</th><th>Details</th><th>Status</th></tr></thead>
        <tbody>
          {events.map((row) => (
            <tr key={row.id}>
              <td>{clock(row.at)}</td>
              <td className="exm-sym">{row.symbol || '—'}</td>
              <td>{row.result === 'NOT_SUBMITTED' ? 'Authorization held' : row.result === 'SHADOW_TARGET' ? 'Shadow target' : row.result === 'SHADOW_STOP' ? 'Shadow stop' : pretty(row.result)}</td>
              <td>{row.detail || pretty(row.reason_code)}</td>
              <td><span className={`exm-pill ${row.result === 'SHADOW_TARGET' ? 'ok' : row.result === 'SHADOW_STOP' ? 'bad' : 'sim'}`}>SIMULATED</span></td>
            </tr>
          ))}
        </tbody>
      </table>
      {!events.length ? <div className="exm-empty">No events recorded.</div> : null}
    </div>
  );
}

function Step({ step, last }: { step: ExecutionEvent; last: boolean }) {
  const title = step.result === 'NOT_SUBMITTED' ? 'Authorization held' : step.result === 'SHADOW_TARGET' ? 'Shadow target reached' : step.result === 'SHADOW_STOP' ? 'Shadow stop reached' : pretty(step.result);
  return (
    <div className="exm-step">
      <time>{clock(step.at)}</time>
      <div className="exm-rail"><i />{last ? null : <b />}</div>
      <div>
        <strong>{title}</strong>
        <p>{step.detail || 'No broker order was sent.'}</p>
      </div>
    </div>
  );
}

function Quality({ plans }: { plans: ShadowPlan[] }) {
  const rows = new Map<string, number>();
  for (const plan of plans) rows.set(plan.symbol || '—', (rows.get(plan.symbol || '—') || 0) + 1);
  return (
    <table className="exm-table">
      <thead><tr><th>Symbol</th><th>Plans</th><th>Slippage</th><th>Fill Time</th></tr></thead>
      <tbody>
        {[...rows.entries()].map(([sym, n]) => <tr key={sym}><td className="exm-sym">{sym}</td><td>{n}</td><td>—</td><td>—</td></tr>)}
      </tbody>
    </table>
  );
}

function Bars({ days }: { days: ExecutionBook['daily'] }) {
  const max = Math.max(1, ...days.map((day) => day.blocked + day.resolved));
  return (
    <div className="exm-chart">
      <div className="exm-yaxis"><span>{max}</span><span>{Math.round(max / 2)}</span><span>0</span></div>
      <div className="exm-plot">
        {days.map((day) => (
          <div className="exm-bar" key={day.day} title={`${day.day}: ${day.blocked} held, ${day.resolved} resolved`}>
            <i className={day.resolved > day.blocked ? 'g' : ''} style={{ height: `${((day.blocked + day.resolved) / max) * 100}%` }} />
            <span>{day.day.slice(8)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Donut({ parts, center, caption }: { parts: { label: string; value: number; color: string }[]; center: string; caption: string }) {
  const shown = parts.filter((part) => part.value > 0);
  const total = shown.reduce((sum, part) => sum + part.value, 0) || 1;
  const c = 2 * Math.PI * 46;
  let offset = 0;
  const slices = (shown.length ? shown : [{ label: 'None', value: 1, color: '#e8eef6' }]).map((part) => {
    const len = shown.length ? (part.value / total) * c : c;
    const slice = { ...part, dash: `${len} ${c - len}`, offset };
    offset -= len;
    return slice;
  });
  const legendTotal = parts.reduce((sum, part) => sum + part.value, 0) || 1;
  return (
    <div className="exm-donut-wrap">
      <svg className="exm-donut" viewBox="0 0 132 132" aria-label={caption}>
        <circle cx="66" cy="66" r="46" fill="none" stroke="#eef2f6" strokeWidth="16" />
        {slices.map((slice) => <circle key={slice.label} cx="66" cy="66" r="46" fill="none" stroke={slice.color} strokeWidth="16" strokeDasharray={slice.dash} strokeDashoffset={slice.offset} transform="rotate(-90 66 66)" />)}
        <text x="66" y="64" textAnchor="middle" fontSize="18" fontWeight="700" fill="#172033">{center}</text>
        <text x="66" y="80" textAnchor="middle" fontSize="9" fill="#98a2b3">{caption}</text>
      </svg>
      <div className="exm-legend">
        {parts.filter((part) => part.label !== 'None').map((part) => (
          <div key={part.label}><span><i className="exm-swatch" style={{ background: part.color }} />{part.label}</span><b>{part.value} ({Math.round((100 * part.value) / legendTotal) || 0}%)</b></div>
        ))}
      </div>
    </div>
  );
}

function Limit({ label, current, limit }: { label: string; current: number | null; limit: number | null }) {
  const width = limit && current != null ? Math.max(0, Math.min(100, (current / limit) * 100)) : 0;
  return (
    <div className="exm-limit">
      <div style={{ flex: 1 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}><span>{label}</span><b>{current ?? '—'} / {limit ?? '—'}</b></div>
        {limit && current != null ? <div className="exm-meter"><i style={{ width: `${width}%` }} /></div> : null}
      </div>
    </div>
  );
}

function Rule({ name, detail }: { name: string; detail: string }) {
  return <div className="exm-rule"><span>{name}</span><b>{detail}</b></div>;
}

function Chip({ k, v, s, ok, shield, clock: showClock }: { k: string; v: string; s?: string; ok?: boolean; shield?: boolean; clock?: boolean }) {
  return (
    <div className="exm-chip">
      <span className="k">{k}</span>
      <span className={`v${ok ? ' ok' : ''}`}>{shield ? <Shield size={13} color="#2563eb" /> : showClock ? <Clock3 size={13} color="#667085" /> : ok ? <i className="exm-dot ok" /> : null}{v}</span>
      {s ? <span className="s">{s}</span> : null}
    </div>
  );
}

function Kpi({ icon, tone, label, value, hint }: { icon: ReactNode; tone: 'green' | 'blue' | 'red' | 'violet' | 'amber'; label: string; value: string; hint: string }) {
  return (
    <article className="exm-kpi">
      <div className="exm-kpi-top"><span className={`exm-ico ${tone}`}>{icon}</span>{label}</div>
      <strong>{value}</strong>
      <em>{hint}</em>
    </article>
  );
}

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  CalendarClock,
  Layers,
  RefreshCw,
  ShieldCheck,
  Target,
  Wallet,
} from 'lucide-react';
import { InstrumentIcon } from '../features/market-scanner/components/InstrumentIcon';
import { CurrencyFlag } from '../features/market-intelligence/components/CurrencyFlag';
import { usePollingAsync } from '../features/market-intelligence/hooks/useMarketIntelligence';
import { get } from '../lib/api';
import { accountMoney } from '../lib/money';
import { marketStatus, nextChangeLabel, type MarketStatus } from '../lib/marketClock';
import { writeHashRoute, type Page } from '../lib/routes';
import type { Health, Summary, Tenant } from '../types';

type OutlookSymbol = { symbol: string | null; direction: string | null; confidence: number | null };
type OutlookBook = {
  analysis_date: string | null;
  published_at: string | null;
  state: string | null;
  qualified: number;
  published: number | null;
  bias: string | null;
  confidence: number | null;
  confidence_basis: string;
  narrative: string | null;
  symbols: OutlookSymbol[];
};
type BrokerPosition = {
  ticket: string | null;
  symbol: string | null;
  direction: string | null;
  volume: number | null;
  profit: number | null;
  r_multiple: number | null;
};
type LiveAccount = {
  ok?: boolean;
  currency?: string | null;
  balance?: number | null;
  equity?: number | null;
  floating_pnl?: number | null;
  positions?: { ticket: string | null; profit: number | null; r_multiple: number | null }[];
};
type CommandCentre = {
  as_of: string;
  mode: string;
  market_open: boolean | null;
  safety_status: string;
  system_status: string | null;
  execution: string;
  execution_note: string;
  provider: string | null;
  provider_connection: string | null;
  data_as_of: string | null;
  workers_online: number | null;
  workers_total: number | null;
  warnings: string[];
  limits: { max_open_positions: number | null; max_concurrent: number | null; max_trade_risk_pct: number | null; max_total_risk_pct: number | null; source: string };
  positions: { broker_open: number; shadow_open: number; orders_submitted: number };
  broker_positions?: BrokerPosition[] | null;
  account: { currency: string | null; environment: string | null; balance: number | null; equity: number | null; floating_pnl: number | null; floating_pnl_basis: string | null; margin_used_pct: number | null; stale: boolean | null; connection_status: string | null };
  outlook: OutlookBook;
  outlooks?: Record<string, OutlookBook>;
  strength: { currency: string; score: number; label: string; tone: string }[];
  scanner: { total: number; actionable: number; watchlist: number; no_setup: number; excluded: number; groups: Record<string, Record<string, number>>; excluded_reasons: { symbol: string; reason: string }[] };
  tit: { count: number; levels: Record<string, number> };
  modes?: { strategy: number; outlook: number; strategy_types: Record<string, number> };
  opportunities: { id: string; symbol: string | null; direction: string | null; type_label: string | null; tit_level: string | null; timeframe: string | null; stage: string | null; state: string | null; confidence: number | null; next_condition: string | null }[];
  workflow: { steps: { key: string; label: string; state: string; errors: number }[]; current_label: string; step_of: number; step_count: number; position_pct: number; position_basis: string; operation: string | null; next_action: string | null; focus_symbol: string | null; errors: number; blockers: string[] };
  shadow_plans: { symbol: string | null; direction: string | null; type_label: string | null; unrealized_r: number | null; entry_reference: number | null; price_status: string | null; order_status: string | null }[];
  performance: { basis: string | null; closed_30d: number | null; hit_rate: number | null; avg_r: number | null; profit_factor: number | null; max_drawdown_pct: number | null; daily: { day: string; blocked: number; resolved: number }[] };
  alerts: { at: string | null; symbol: string | null; timeframe: string | null; label: string | null; direction: string | null; level: string | null; source: string }[];
};

const HORIZONS = [
  { id: 'DAILY', label: 'Daily', tab: 'daily' },
  { id: 'WEEKLY', label: 'Weekly', tab: 'weekly' },
  { id: 'MONTHLY', label: 'Monthly', tab: 'monthly' },
  { id: 'QUARTERLY', label: 'Quarterly', tab: 'quarterly' },
  { id: 'H8', label: 'Gold H8', tab: 'gold' },
] as const;

const GROUPS: { key: string; label: string }[] = [
  { key: 'majors', label: 'FX Majors' },
  { key: 'minors', label: 'FX Minors' },
  { key: 'jpy', label: 'JPY Pairs' },
  { key: 'commodities', label: 'Commodities' },
  { key: 'indices', label: 'Indices' },
];
const STACK = [
  { key: 'HIGH_INSPECTION', color: '#22c55e', label: 'Actionable' },
  { key: 'WATCHING', color: '#f59e0b', label: 'Watchlist' },
  { key: 'NEUTRAL', color: '#94a3b8', label: 'No Setup' },
  { key: 'EXCLUDED', color: '#fecaca', label: 'Excluded' },
];
const STEP_LABEL: Record<string, string> = {
  scan: 'Scan',
  analyze: 'Analyse',
  setups: 'Identify',
  validate: 'Validate',
  execute: 'Execute',
  manage: 'Manage',
};

function go(page: Page, tab?: string) {
  writeHashRoute(page, tab);
  window.dispatchEvent(new HashChangeEvent('hashchange'));
}

function pairOf(symbol: string) {
  const clean = symbol.replace(/[^A-Za-z]/g, '').toUpperCase();
  if (clean.startsWith('XAU')) return { base: 'XAU', quote: clean.slice(3) || 'USD' };
  return { base: clean.slice(0, 3), quote: clean.slice(3, 6) };
}

function words(value: string | null | undefined) {
  if (!value) return '—';
  return value.replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());
}

function when(iso: string | null | undefined) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'UTC' }).format(d) + ' UTC';
}

function cash(value: number | null | undefined, currency: string | null, signed = false) {
  return accountMoney(value, currency, signed);
}

function useNow() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(id);
  }, []);
  return now;
}

function sessionTitle(status: MarketStatus) {
  if (status.tone === 'closed') return 'Market Closed';
  const name = status.detail.replace(/ session$/, '');
  return `${name} (Active)`;
}

function healthy(value: string | null | undefined) {
  const text = (value || '').toUpperCase();
  return text === 'HEALTHY' || text === 'CONNECTED' || text === 'RUNNING' || text === 'OK' || text === 'READY';
}

function alertBucket(alert: CommandCentre['alerts'][number]) {
  const text = `${alert.label ?? ''} ${alert.level ?? ''} ${alert.source}`.toLowerCase();
  if (text.includes('risk') || text.includes('exposure')) return 'risk';
  if (alert.source === 'notification' || /channel|break|outlook|touch/.test(text)) return 'market';
  if (/execut|order|fill|submit/.test(text)) return 'execution';
  return 'system';
}

function applyLive(board: CommandCentre, live: LiveAccount): CommandCentre {
  if (!live.ok) return board;
  const byTicket = new Map((live.positions ?? []).filter((row) => row.ticket).map((row) => [row.ticket, row]));
  const positions = board.broker_positions?.map((row) => {
    const hit = row.ticket ? byTicket.get(row.ticket) : undefined;
    return hit ? { ...row, profit: hit.profit, r_multiple: hit.r_multiple ?? row.r_multiple } : row;
  });
  return {
    ...board,
    account: {
      ...board.account,
      currency: live.currency || board.account.currency,
      balance: live.balance ?? board.account.balance,
      equity: live.equity ?? board.account.equity,
      floating_pnl: live.floating_pnl ?? board.account.floating_pnl,
      floating_pnl_basis: live.equity != null ? 'Live equity minus balance from the MT5 terminal.' : board.account.floating_pnl_basis,
      stale: false,
    },
    broker_positions: positions ?? board.broker_positions,
  };
}

function signalColor(tone: string, score: number) {
  if (tone === 'positive' && score >= 60) return '#22c55e';
  if (tone === 'positive') return '#84cc16';
  if (tone === 'negative' && score < 40) return '#ef4444';
  if (tone === 'negative') return '#f97316';
  return '#eab308';
}

export function Overview({ health, summary }: { health: Health | null; summary: Summary | null; tenant?: Tenant; tenantId: string; instrumentCount?: number }) {
  const loader = useCallback(() => get<CommandCentre>('/autonomous/command-centre'), []);
  const [pageVisible, setPageVisible] = useState(() => document.visibilityState !== 'hidden');
  useEffect(() => {
    const onVis = () => setPageVisible(document.visibilityState !== 'hidden');
    document.addEventListener('visibilitychange', onVis);
    return () => document.removeEventListener('visibilitychange', onVis);
  }, []);
  const board = usePollingAsync(loader, [loader], { intervalMs: 5000, enabled: pageVisible });
  const liveRef = useRef<LiveAccount | null>(null);
  useEffect(() => {
    if (!pageVisible) return;
    let alive = true;
    const pull = async () => {
      try {
        const live = await get<LiveAccount>('/autonomous/live-account');
        if (!alive || !live?.ok) return;
        liveRef.current = live;
        board.setData((prev) => (prev ? applyLive(prev, live) : prev));
      } catch {
        /* keep the last figures when a tick cannot be read */
      }
    };
    void pull();
    const id = window.setInterval(() => void pull(), 1000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, [pageVisible, board.setData]);
  useEffect(() => {
    const live = liveRef.current;
    if (!board.data || !live?.ok) return;
    board.setData((prev) => (prev ? applyLive(prev, live) : prev));
  }, [board.data?.as_of, board.setData]);
  const [period, setPeriod] = useState<'today' | 'week' | 'month' | 'all'>('today');
  const [horizon, setHorizon] = useState<(typeof HORIZONS)[number]['id']>('DAILY');
  const [book, setBook] = useState<'currencies' | 'commodities' | 'indices'>('currencies');
  const [alertFilter, setAlertFilter] = useState<'all' | 'execution' | 'risk' | 'market' | 'system'>('all');
  const now = useNow();
  const data = board.data;
  const status = useMemo(() => marketStatus(now), [Math.floor(now.getTime() / 3_600_000)]);
  const countdown = nextChangeLabel(status, now);
  const outlook = data?.outlooks?.[horizon] ?? (horizon === 'DAILY' ? data?.outlook : undefined);
  const mode = data?.mode ?? summary?.mode ?? '';
  const executionOn = data?.execution === 'DEMO' || data?.execution === 'LIVE';
  const shadowOn = data?.execution === 'SHADOW' || /SHADOW|ANALYSIS_ONLY/.test(mode);

  return (
    <div className="ovx">
      {board.error ? <p className="ovx-error">{board.error}</p> : null}
      {board.loading && !data ? <p className="ovx-empty">Loading the trading overview…</p> : null}
      {data ? (
        <>
          <KpiStrip data={data} health={health} status={status} countdown={countdown} executionOn={executionOn} shadowOn={shadowOn} />
          <section className="ovx-grid">
            <OutlookCard outlook={outlook} horizon={horizon} onHorizon={setHorizon} />
            <StrengthCard rows={data.strength} book={book} onBook={setBook} />
            <OpportunitiesCard data={data} />
          </section>
          <section className="ovx-grid">
            <EngineCard data={data} />
            <ScannerCard data={data} />
            <PositionsCard data={data} />
          </section>
          <section className="ovx-grid">
            <AlertsCard data={data} filter={alertFilter} onFilter={setAlertFilter} />
            <HealthCard data={data} health={health} />
            <Performance data={data} period={period} onPeriod={setPeriod} />
          </section>
        </>
      ) : null}
    </div>
  );
}

function KpiStrip({
  data, health, status, countdown, executionOn, shadowOn,
}: {
  data: CommandCentre;
  health: Health | null;
  status: MarketStatus;
  countdown: string;
  executionOn: boolean;
  shadowOn: boolean;
}) {
  const services = [
    healthy(health?.api),
    healthy(health?.database),
    healthy(health?.mt5?.status),
    healthy(health?.market_data?.provider_status),
    data.workers_total != null && data.workers_online === data.workers_total,
  ];
  const up = services.filter(Boolean).length;
  const positions = data.broker_positions;
  const fx = positions?.filter((p) => p.symbol && !p.symbol.toUpperCase().includes('XAU')).length ?? 0;
  const gold = positions?.filter((p) => p.symbol?.toUpperCase().includes('XAU')).length ?? 0;
  const open = positions != null ? positions.length : data.positions.broker_open;
  const strategy = data.modes?.strategy ?? data.opportunities.length;
  const outlook = data.modes?.outlook ?? data.outlook.qualified;
  const equity = data.account.equity;
  const balance = data.account.balance;
  const floatPnl = data.account.floating_pnl;
  const pct = floatPnl != null && balance ? (floatPnl / balance) * 100 : null;
  const upTone = floatPnl != null && floatPnl >= 0;

  return (
    <section className="ovx-kpis" aria-label="Account snapshot">
      <article className="ovx-kpi">
        <span className="ovx-kpi-icon is-green"><ShieldCheck size={18} /></span>
        <div>
          <small>Status</small>
          <b title={up === services.length ? 'All systems operational' : `${up} of ${services.length} services running`}>{up === services.length ? 'Operational' : `${up}/${services.length} up`}</b>
          <em>{up}/{services.length} services running</em>
        </div>
      </article>
      <article className="ovx-kpi">
        <span className="ovx-kpi-icon is-blue"><CalendarClock size={18} /></span>
        <div>
          <small>Session</small>
          <b title={sessionTitle(status)}>{sessionTitle(status).replace(' (Active)', '')}</b>
          <em>{countdown || status.label}</em>
        </div>
      </article>
      <article className="ovx-kpi">
        <span className="ovx-kpi-icon is-rose"><Target size={18} /></span>
        <div>
          <small>Opportunities</small>
          <b className="ovx-num">{strategy + outlook}</b>
          <em title={`${strategy} strategy · ${outlook} outlook`}>{strategy} strat · {outlook} outlook</em>
        </div>
      </article>
      <article className="ovx-kpi">
        <span className="ovx-kpi-icon is-green"><Layers size={18} /></span>
        <div>
          <small>Positions</small>
          <b className="ovx-num">{open}</b>
          <em>{positions != null ? `${fx} FX · ${gold} gold` : `${data.positions.shadow_open} shadow`}</em>
        </div>
      </article>
      <article className="ovx-kpi">
        <span className="ovx-kpi-icon is-green"><Wallet size={18} /></span>
        <div>
          <small>Equity</small>
          <b className="ovx-num">{cash(equity, data.account.currency)}</b>
          <em className={floatPnl == null ? '' : upTone ? 'is-up' : 'is-down'} title={data.account.floating_pnl_basis ?? undefined}>
            {pct != null ? `${pct > 0 ? '+' : pct < 0 ? '−' : ''}${Math.abs(pct).toFixed(2)}% ` : ''}
            ({cash(floatPnl, data.account.currency, true)})
          </em>
        </div>
      </article>
      <article className="ovx-control">
        <small>Execution</small>
        <div className="ovx-control-row">
          <span className="ovx-switch" data-on={executionOn ? '1' : '0'} role="switch" aria-checked={executionOn} aria-disabled="true" title={data.execution_note} />
          <b>{executionOn ? 'Enabled' : 'Off'}</b>
        </div>
      </article>
      <article className="ovx-control">
        <small>Risk Mode</small>
        <div className="ovx-select" title="Account safety status">{words(data.safety_status)}</div>
      </article>
      <article className="ovx-control">
        <small>Shadow</small>
        <div className="ovx-control-row">
          <span className="ovx-switch" data-on={shadowOn ? '1' : '0'} role="switch" aria-checked={shadowOn} aria-disabled="true" title={data.execution_note} />
        </div>
      </article>
    </section>
  );
}

function CardHead({ title, action, onAction }: { title: string; action: string; onAction: () => void }) {
  return (
    <div className="ovx-head">
      <h2>{title}</h2>
      <button type="button" className="ovx-link" onClick={onAction}>{action}</button>
    </div>
  );
}

function OutlookCard({ outlook, horizon, onHorizon }: { outlook: OutlookBook | undefined; horizon: string; onHorizon: (id: (typeof HORIZONS)[number]['id']) => void }) {
  const bear = outlook?.bias === 'BEARISH';
  const bull = outlook?.bias === 'BULLISH';
  const tab = HORIZONS.find((item) => item.id === horizon)?.tab ?? 'daily';
  return (
    <article className="ovx-card ovx-outlook">
      <CardHead title="AI Market Outlook" action="Full analysis" onAction={() => go('ai-market-outlook', tab)} />
      <div className="ovx-pills" role="tablist">
        {HORIZONS.map((item) => (
          <button key={item.id} type="button" role="tab" aria-selected={horizon === item.id} className={horizon === item.id ? 'is-on' : ''} onClick={() => onHorizon(item.id)}>{item.label}</button>
        ))}
      </div>
      <div className="ovx-bias">
        <div className={`ovx-bias-name ${bear ? 'is-bear' : bull ? 'is-bull' : ''}`}>
          <span className="ovx-bias-mark" aria-hidden><RefreshCw size={14} /></span>
          <b>{outlook?.bias ? words(outlook.bias) : 'No bias'}</b>
        </div>
        <div className={`ovx-score ${bear ? 'is-bear' : bull ? 'is-bull' : ''}`}>
          <b>{outlook?.confidence != null ? `${Math.round(outlook.confidence)}%` : '—'}</b>
          <span>Evidence</span>
        </div>
      </div>
      <p className="ovx-copy" title={outlook?.narrative ?? 'No narrative is stored for this horizon.'}>{outlook?.narrative ?? 'No narrative is stored for this horizon.'}</p>
      <div className="ovx-chips">
        {(outlook?.symbols ?? []).filter((s) => s.symbol).map((s) => (
          <button key={s.symbol} type="button" className="ovx-chip" onClick={() => go('ai-market-outlook', tab)}>
            <b>{s.symbol}</b>
            <em className={s.direction === 'BULLISH' ? 'is-up' : s.direction === 'BEARISH' ? 'is-down' : ''}>{s.confidence != null ? `${Math.round(s.confidence)}%` : '—'}</em>
          </button>
        ))}
        {(outlook?.symbols.length ?? 0) === 0 ? <span className="ovx-quiet">No qualified symbols on this horizon.</span> : null}
      </div>
    </article>
  );
}

function StrengthCard({ rows, book, onBook }: { rows: CommandCentre['strength']; book: 'currencies' | 'commodities' | 'indices'; onBook: (book: 'currencies' | 'commodities' | 'indices') => void }) {
  const metal = rows.filter((row) => row.currency === 'XAU');
  const shown = book === 'commodities' ? metal : book === 'indices' ? [] : rows.filter((row) => row.currency !== 'XAU').slice(0, 8);
  return (
    <article className="ovx-card">
      <CardHead title="Key Market Summary" action="View All" onAction={() => go('strength-intelligence')} />
      <div className="ovx-pills">
        {(['currencies', 'commodities', 'indices'] as const).map((id) => (
          <button key={id} type="button" className={book === id ? 'is-on' : ''} onClick={() => onBook(id)}>{id[0].toUpperCase() + id.slice(1)}</button>
        ))}
      </div>
      {shown.length === 0 ? (
        <p className="ovx-quiet">{book === 'currencies' ? 'The strength engine has not published scores.' : 'This book is not on the currency strength feed.'}</p>
      ) : (
        <div className="ovx-fill">
        <table className="ovx-table">
          <thead>
            <tr><th>Symbol</th><th>Strength</th><th>Signal</th><th>Trend</th></tr>
          </thead>
          <tbody>
            {shown.map((row) => {
              const trend = row.tone === 'positive' ? 'Bull' : row.tone === 'negative' ? 'Bearish' : 'Neutral';
              return (
                <tr key={row.currency}>
                  <td><span className="ovx-sym"><CurrencyFlag code={row.currency} size={14} /><b>{row.currency}</b></span></td>
                  <td><b>{Math.round(row.score)}</b> <span className="ovx-quiet">{row.label}</span></td>
                  <td><span className="ovx-signal"><i style={{ width: `${Math.max(8, Math.min(100, row.score))}%`, background: signalColor(row.tone, row.score) }} /></span></td>
                  <td><span className={`ovx-trend is-${row.tone}`}>{trend}</span></td>
                </tr>
              );
            })}
          </tbody>
        </table>
        </div>
      )}
    </article>
  );
}

function OpportunitiesCard({ data }: { data: CommandCentre }) {
  return (
    <article className="ovx-card">
      <CardHead title="Active Opportunities" action="View All" onAction={() => go('trading-opportunities')} />
      {data.opportunities.length === 0 ? <p className="ovx-quiet">No active opportunity is in the engine.</p> : (
        <ul className="ovx-opps">
          {data.opportunities.map((row) => {
            const score = row.confidence ?? 0;
            const low = row.confidence != null && row.confidence < 50;
            const tone = low ? 'mid' : row.direction === 'BULLISH' ? 'up' : 'down';
            return (
              <li key={row.id}>
                <button type="button" onClick={() => go('trading-opportunities')}>
                  {row.symbol ? <InstrumentIcon {...pairOf(row.symbol)} size="sm" /> : <span />}
                  <span className="ovx-opp-copy">
                    <b>{row.symbol} <em className={row.direction === 'BULLISH' ? 'is-up' : 'is-down'}>{words(row.direction)}</em></b>
                    <small>{row.type_label}{row.tit_level ? ` · ${row.tit_level}` : ''} · {row.timeframe ?? '—'} · {words(row.state)}</small>
                  </span>
                  <span className="ovx-conf">
                    <i><b className={`is-${tone}`} style={{ width: `${Math.max(6, Math.min(100, score))}%` }} /></i>
                    <strong>{row.confidence != null ? `${Math.round(row.confidence)}%` : '—'}</strong>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </article>
  );
}

function EngineCard({ data }: { data: CommandCentre }) {
  return (
    <article className="ovx-card">
      <CardHead title="Autonomous Engine Status" action="View Details" onAction={() => go('autonomous-engine')} />
      <ol className="ovx-steps">
        {data.workflow.steps.map((step, index) => (
          <li key={step.key} className={`is-${step.state}`}>
            <span>{index + 1}</span>
            <small>{STEP_LABEL[step.key] ?? step.label}</small>
          </li>
        ))}
      </ol>
      <div className="ovx-activity">
        <span className="ovx-spin" aria-hidden><RefreshCw size={16} /></span>
        <div>
          <small>Current Activity</small>
          <b>{data.workflow.operation ?? data.workflow.current_label}</b>
        </div>
        <div className="ovx-activity-pct">
          <b>{data.workflow.position_pct}%</b>
          <small>Stage {data.workflow.step_of} of {data.workflow.step_count}</small>
        </div>
      </div>
      {data.workflow.focus_symbol ? <p className="ovx-quiet">Focus {data.workflow.focus_symbol}</p> : null}
      {data.workflow.blockers.length ? <p className="ovx-quiet">{data.workflow.blockers.join(' · ')}</p> : null}
    </article>
  );
}

function ScannerCard({ data }: { data: CommandCentre }) {
  const tiles = [
    { n: data.scanner.actionable, label: 'Actionable', tone: 'up' },
    { n: data.scanner.watchlist, label: 'Watchlist', tone: 'mid' },
    { n: data.scanner.no_setup, label: 'No Setup', tone: 'flat' },
    { n: data.scanner.excluded, label: 'Excluded', tone: 'down' },
  ];
  return (
    <article className="ovx-card">
      <CardHead title={`Market Scanner (${data.scanner.total})`} action="Open Scanner" onAction={() => go('market-scanner')} />
      <div className="ovx-scan-kpis">
        {tiles.map((tile) => (
          <div key={tile.label} className={`is-${tile.tone}`}><b>{tile.n}</b><span>{tile.label}</span></div>
        ))}
      </div>
      <div className="ovx-bars">
        {GROUPS.map((group) => {
          const counts = data.scanner.groups[group.key] ?? {};
          const total = STACK.reduce((sum, item) => sum + (counts[item.key] ?? 0), 0) || 1;
          return (
            <div key={group.key}>
              <span>{group.label}</span>
              <span className="ovx-bar">{STACK.map((item) => <i key={item.key} style={{ width: `${((counts[item.key] ?? 0) / total) * 100}%`, background: item.color }} />)}</span>
              <b>{STACK.reduce((sum, item) => sum + (counts[item.key] ?? 0), 0)}</b>
            </div>
          );
        })}
      </div>
      <div className="ovx-legend">{STACK.map((item) => <span key={item.key}><i style={{ background: item.color }} />{item.label}</span>)}</div>
    </article>
  );
}

function PositionsCard({ data }: { data: CommandCentre }) {
  const rows = data.broker_positions;
  const currency = data.account.currency;
  return (
    <article className="ovx-card">
      <CardHead title={`Open Positions (${rows != null ? rows.length : data.positions.broker_open})`} action="View All" onAction={() => go('execution-positions')} />
      {rows == null ? <p className="ovx-quiet">The terminal could not be read. Open positions stay hidden until it is connected.</p> : rows.length === 0 ? <p className="ovx-quiet">No open positions on the terminal.</p> : (
        <div className="ovx-pos-scroll">
          <table className="ovx-table ovx-pos">
            <thead>
              <tr><th>Symbol</th><th>Side</th><th>Size</th><th>P/L</th><th>R</th></tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.ticket ?? row.symbol}>
                  <td><span className="ovx-sym"><b>{row.symbol}</b></span></td>
                  <td><span className={`ovx-side is-${row.direction === 'BUY' ? 'buy' : 'sell'}`}>{row.direction === 'BUY' ? 'Buy' : 'Sell'}</span></td>
                  <td>{row.volume != null ? row.volume.toFixed(2) : '—'}</td>
                  <td className={row.profit != null && row.profit < 0 ? 'is-down' : 'is-up'}>{cash(row.profit, currency, true)}</td>
                  <td className={row.r_multiple != null && row.r_multiple < 0 ? 'is-down' : 'is-up'}>{row.r_multiple != null ? `${row.r_multiple > 0 ? '+' : ''}${row.r_multiple.toFixed(2)}` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="ovx-pos-foot">
        <div><span>Floating P/L</span><b className={data.account.floating_pnl != null && data.account.floating_pnl < 0 ? 'is-down' : 'is-up'}>{cash(data.account.floating_pnl, currency, true)}</b></div>
        <div><span>Win Rate</span><b>{data.performance.hit_rate != null ? `${data.performance.hit_rate}%` : '—'}</b></div>
        <div><span>Closed 30d</span><b>{data.performance.closed_30d ?? '—'}</b></div>
      </div>
    </article>
  );
}

function AlertsCard({ data, filter, onFilter }: { data: CommandCentre; filter: 'all' | 'execution' | 'risk' | 'market' | 'system'; onFilter: (id: 'all' | 'execution' | 'risk' | 'market' | 'system') => void }) {
  const counts = { execution: 0, risk: 0, market: 0, system: 0 };
  for (const alert of data.alerts) counts[alertBucket(alert)] += 1;
  const shown = data.alerts.filter((alert) => filter === 'all' || alertBucket(alert) === filter);
  const chips = [
    ['all', `All ${data.alerts.length}`],
    ['execution', `Exec ${counts.execution}`],
    ['risk', `Risk ${counts.risk}`],
    ['market', `Mkt ${counts.market}`],
    ['system', `Sys ${counts.system}`],
  ] as const;
  return (
    <article className="ovx-card">
      <CardHead title="Recent Alerts" action="View All" onAction={() => go('h8-bos-btl')} />
      <div className="ovx-pills">
        {chips.map(([id, label]) => (
          <button key={id} type="button" className={filter === id ? 'is-on' : ''} onClick={() => onFilter(id)}>{label}</button>
        ))}
      </div>
      {shown.length === 0 ? <p className="ovx-quiet">No alerts in this view.</p> : (
        <ul className="ovx-alerts">
          {shown.map((alert, index) => {
            const bucket = alertBucket(alert);
            return (
              <li key={`${alert.source}-${alert.at}-${index}`}>
                <i className={`is-${bucket}`} />
                <span>
                  <b>{alert.symbol ? `${alert.symbol} · ` : ''}{alert.label}</b>
                  <small>{alert.timeframe ?? '—'}{alert.direction ? ` · ${words(alert.direction)}` : ''}</small>
                </span>
                <time>{when(alert.at)}</time>
              </li>
            );
          })}
        </ul>
      )}
    </article>
  );
}

function HealthCard({ data, health }: { data: CommandCentre; health: Health | null }) {
  const rows = [
    { name: 'API', status: health?.api ?? '—', detail: health?.api ?? '—' },
    { name: 'MT5', status: health?.mt5?.status ?? '—', detail: health?.mt5?.status ?? '—' },
    { name: 'Market data', status: data.provider_connection ?? health?.market_data?.provider_status ?? '—', detail: data.provider ?? '—' },
    { name: 'Analysis', status: data.system_status ?? '—', detail: data.system_status ?? '—' },
    { name: 'Trading', status: data.execution === 'BLOCKED' ? 'BLOCKED' : 'RUNNING', detail: data.execution },
    { name: 'Database', status: health?.database ?? '—', detail: health?.database ?? '—' },
    { name: 'Workers', status: data.workers_online != null && data.workers_total != null && data.workers_online === data.workers_total ? 'RUNNING' : 'DEGRADED', detail: `${data.workers_online ?? '—'}/${data.workers_total ?? '—'}` },
    { name: 'Execution', status: data.execution, detail: data.execution === 'DEMO' || data.execution === 'LIVE' ? 'enabled' : data.execution === 'SHADOW' ? 'shadow' : 'halted' },
  ];
  return (
    <article className="ovx-card">
      <CardHead title="System Health" action="View Details" onAction={() => go('system-control')} />
      <div className="ovx-fill">
      <table className="ovx-table ovx-health">
        <thead>
          <tr><th>Service</th><th>Status</th></tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const good = healthy(row.status) || row.status === 'DEMO' || row.status === 'LIVE' || row.status === 'RUNNING';
            const bad = /BLOCK|ERROR|FAIL|UNAVAILABLE|HALT/i.test(row.status);
            return (
              <tr key={row.name}>
                <td>{row.name}</td>
                <td><span className={`ovx-pill ${bad ? 'is-bad' : good ? 'is-good' : 'is-wait'}`} title={words(String(row.detail))}>{words(row.status)}</span></td>
              </tr>
            );
          })}
        </tbody>
      </table>
      </div>
    </article>
  );
}

function Performance({ data, period, onPeriod }: { data: CommandCentre; period: 'today' | 'week' | 'month' | 'all'; onPeriod: (p: 'today' | 'week' | 'month' | 'all') => void }) {
  const daily = data.performance.daily;
  const today = daily.at(-1)?.day;
  const sliced = period === 'today' ? daily.filter((d) => d.day === today) : period === 'week' ? daily.slice(-7) : daily;
  const points = (sliced.length ? sliced : daily).map((d) => d.resolved);
  const max = Math.max(1, ...points);
  const width = 280;
  const height = 72;
  const path = points.length
    ? points.map((value, index) => {
        const x = points.length === 1 ? width / 2 : (index / (points.length - 1)) * width;
        const y = height - (value / max) * (height - 8) - 4;
        return `${index === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
      }).join(' ')
    : '';
  const currency = data.account.currency;
  return (
    <article className="ovx-card">
      <div className="ovx-head">
        <h2>Trading Performance</h2>
        <div className="ovx-pills ovx-pills-tight">
          {(['today', 'week', 'month', 'all'] as const).map((id) => (
            <button key={id} type="button" className={period === id ? 'is-on' : ''} onClick={() => onPeriod(id)}>{id === 'today' ? 'Today' : id === 'week' ? 'Week' : id === 'month' ? 'Month' : 'All'}</button>
          ))}
        </div>
      </div>
      <div className="ovx-metrics">
        <div className="is-green"><span>Floating P/L</span><b className={data.account.floating_pnl != null && data.account.floating_pnl < 0 ? 'is-down' : 'is-up'}>{cash(data.account.floating_pnl, currency, true)}</b></div>
        <div><span>Win Rate</span><b>{data.performance.hit_rate != null ? `${data.performance.hit_rate}%` : '—'}</b></div>
        <div><span>Profit Factor</span><b>{data.performance.profit_factor != null ? data.performance.profit_factor : '—'}</b></div>
        <div><span>Max Drawdown</span><b>{data.performance.max_drawdown_pct != null ? `${data.performance.max_drawdown_pct}%` : '—'}</b></div>
        <div><span>Average R</span><b>{data.performance.avg_r != null ? data.performance.avg_r.toFixed(2) : '—'}</b></div>
        <div><span>Closed 30d</span><b>{data.performance.closed_30d ?? 0}</b></div>
      </div>
      <div className="ovx-chart" aria-hidden>
        {path ? (
          <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
            <path d={path} fill="none" stroke="#2563eb" strokeWidth="2" />
          </svg>
        ) : <span>No closed-plan series is stored for this window.</span>}
      </div>
      <p className="ovx-quiet">{data.performance.basis ?? 'Shadow outcomes only. The line is resolved plans, not account equity.'}</p>
    </article>
  );
}

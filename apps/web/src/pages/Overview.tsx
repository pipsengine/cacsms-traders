import { useCallback, useState } from 'react';
import { LayoutGrid } from 'lucide-react';
import { InstrumentIcon } from '../features/market-scanner/components/InstrumentIcon';
import { CurrencyFlag } from '../features/market-intelligence/components/CurrencyFlag';
import { usePollingAsync } from '../features/market-intelligence/hooks/useMarketIntelligence';
import { get } from '../lib/api';
import { writeHashRoute, type Page } from '../lib/routes';
import type { Health, Summary, Tenant } from '../types';

type OutlookSymbol = { symbol: string | null; direction: string | null; confidence: number | null };
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
  account: { currency: string | null; environment: string | null; balance: number | null; equity: number | null; floating_pnl: number | null; floating_pnl_basis: string | null; margin_used_pct: number | null; stale: boolean | null; connection_status: string | null };
  outlook: { analysis_date: string | null; published_at: string | null; state: string | null; qualified: number; published: number | null; bias: string | null; confidence: number | null; confidence_basis: string; narrative: string | null; symbols: OutlookSymbol[] };
  strength: { currency: string; score: number; label: string; tone: string }[];
  scanner: { total: number; actionable: number; watchlist: number; no_setup: number; excluded: number; groups: Record<string, Record<string, number>>; excluded_reasons: { symbol: string; reason: string }[] };
  tit: { count: number; levels: Record<string, number> };
  opportunities: { id: string; symbol: string | null; direction: string | null; type_label: string | null; tit_level: string | null; timeframe: string | null; stage: string | null; state: string | null; confidence: number | null; next_condition: string | null }[];
  workflow: { steps: { key: string; label: string; state: string; errors: number }[]; current_label: string; step_of: number; step_count: number; position_pct: number; position_basis: string; operation: string | null; next_action: string | null; focus_symbol: string | null; errors: number; blockers: string[] };
  shadow_plans: { symbol: string | null; direction: string | null; type_label: string | null; unrealized_r: number | null; entry_reference: number | null; price_status: string | null; order_status: string | null }[];
  performance: { basis: string | null; closed_30d: number | null; hit_rate: number | null; avg_r: number | null; profit_factor: number | null; max_drawdown_pct: number | null; daily: { day: string; blocked: number; resolved: number }[] };
  alerts: { at: string | null; symbol: string | null; timeframe: string | null; label: string | null; direction: string | null; level: string | null; source: string }[];
};

const GROUPS: { key: string; label: string }[] = [
  { key: 'majors', label: 'FX Majors' },
  { key: 'minors', label: 'FX Minors' },
  { key: 'jpy', label: 'JPY Pairs' },
  { key: 'commodities', label: 'Commodities' },
];
const STACK = [
  { key: 'HIGH_INSPECTION', color: '#16a34a', label: 'Actionable' },
  { key: 'WATCHING', color: '#f59e0b', label: 'Watchlist' },
  { key: 'NEUTRAL', color: '#94a3b8', label: 'No setup' },
  { key: 'EXCLUDED', color: '#e2e8f0', label: 'Excluded' },
];

function go(page: Page, tab?: string) {
  writeHashRoute(page, tab);
  window.dispatchEvent(new HashChangeEvent('hashchange'));
}

function pairOf(symbol: string) {
  if (symbol.startsWith('XAU')) return { base: 'XAU', quote: symbol.slice(3) || 'USD' };
  return { base: symbol.slice(0, 3), quote: symbol.slice(3, 6) };
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

function money(value: number | null | undefined, currency: string | null) {
  if (value == null || !Number.isFinite(value)) return '—';
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(2)} ${currency ?? ''}`.trim();
}

export function Overview({ health, summary }: { health: Health | null; summary: Summary | null; tenant?: Tenant; tenantId: string; instrumentCount?: number }) {
  const loader = useCallback(() => get<CommandCentre>('/autonomous/command-centre'), []);
  const board = usePollingAsync(loader, [loader], { intervalMs: 15000 });
  const [period, setPeriod] = useState<'today' | 'week' | 'month' | 'all'>('today');
  const data = board.data;
  const mode = data?.mode ?? summary?.mode ?? '—';
  const env = data?.account.environment;

  return (
    <div className="ov-dashboard">
      <header className="cc-head">
        <div className="cc-title">
          <div className="cc-mark" aria-hidden><LayoutGrid size={18} /></div>
          <div>
            <h1>Trading Overview</h1>
            <p>Live outlook, engine stage, scanner and account state from the running platform.</p>
            <div className="cc-strip" style={{ marginTop: 8 }}>
              <span className={data?.market_open === false ? 'is-closed' : 'is-live'}>{data?.market_open === false ? 'Market closed' : data?.market_open ? 'Market open' : 'Market session unknown'}</span>
              <span className={mode === 'SHADOW' ? 'is-shadow' : ''}>{words(mode)}</span>
              <span className="is-block">Execution disabled</span>
              {env ? <span>{words(env)}</span> : null}
              {data?.safety_status ? <span>{words(data.safety_status)} safety</span> : null}
            </div>
          </div>
        </div>
        <div className="cc-facts">
          <div className="cc-fact"><small>Trading mode</small><b>{words(mode)}</b></div>
          <div className="cc-fact"><small>Risk limit</small><b>{data?.limits.max_trade_risk_pct != null ? `${data.limits.max_trade_risk_pct}% / trade` : 'Profile not set'}</b></div>
          <div className="cc-fact"><small>Max positions</small><b>{data?.limits.max_open_positions ?? data?.limits.max_concurrent ?? '—'}</b><em>{data?.limits.source === 'account_risk_profiles' ? 'Risk profile' : 'Concurrent plan limit'}</em></div>
          <div className="cc-fact"><small>Current positions</small><b>{data ? data.positions.broker_open : '—'}</b><em>{data ? `${data.positions.shadow_open} shadow plans` : ''}</em></div>
        </div>
      </header>

      {board.error ? <p className="cc-error">{board.error}</p> : null}
      {board.loading && !data ? <p className="cc-muted">Loading the command centre…</p> : null}

      {data ? (
        <>
          <section className="cc-grid">
            <article className="cc-card">
              <div className="cc-card-head">
                <h2>AI Market Outlook</h2>
                <button className="cc-link" type="button" onClick={() => go('ai-market-outlook', 'daily')}>View full analysis</button>
              </div>
              <p className="cc-muted">{data.outlook.published_at ? `Published ${when(data.outlook.published_at)} · ${data.outlook.qualified} qualified` : 'No published daily outlook yet'}</p>
              <div className={`cc-bias ${data.outlook.bias === 'BULLISH' ? 'is-bull' : data.outlook.bias === 'BEARISH' ? 'is-bear' : ''}`}>
                <b>{data.outlook.bias ? words(data.outlook.bias) : 'No bias'}</b>
                <div className="cc-conf">
                  <b>{data.outlook.confidence != null ? `${data.outlook.confidence}%` : '—'}</b>
                  <span className="cc-muted">Evidence score</span>
                </div>
              </div>
              <p className="cc-narrative">{data.outlook.narrative ?? 'The published rows did not store a narrative. Open the daily outlook for the instrument evidence.'}</p>
              <p className="cc-muted">{data.outlook.confidence_basis}</p>
              <div className="cc-chips" style={{ marginTop: 8 }}>
                {data.outlook.symbols.map((s) => s.symbol ? (
                  <button key={s.symbol} className="cc-chip" type="button" onClick={() => go('ai-market-outlook', 'daily')}>
                    {s.symbol} {s.confidence != null ? `${s.confidence.toFixed(0)}%` : ''}
                  </button>
                ) : null)}
              </div>
            </article>

            <article className="cc-card">
              <div className="cc-card-head">
                <h2>Key Market Summary</h2>
                <button className="cc-link" type="button" onClick={() => go('strength-intelligence')}>View all</button>
              </div>
              {data.strength.length === 0 ? <p className="cc-muted">The strength engine has not published scores.</p> : (
                <div className="cc-rows">
                  {data.strength.slice(0, 8).map((c) => (
                    <div className="cc-row" key={c.currency}>
                      <CurrencyFlag code={c.currency} />
                      <b>{c.currency}</b>
                      <span className={c.tone === 'positive' ? 'cc-up' : c.tone === 'negative' ? 'cc-down' : 'cc-flat'}>{c.score.toFixed(0)} · {c.label}</span>
                    </div>
                  ))}
                </div>
              )}
            </article>

            <article className="cc-card">
              <div className="cc-card-head">
                <h2>Active Opportunities</h2>
                <button className="cc-link" type="button" onClick={() => go('trading-opportunities')}>View all</button>
              </div>
              {data.opportunities.length === 0 ? <p className="cc-muted">No active opportunity is in the engine.</p> : data.opportunities.map((o) => (
                <button className="cc-opp" key={o.id} type="button" onClick={() => go('trading-opportunities')} style={{ width: '100%', background: 'none', borderLeft: 0, borderRight: 0, textAlign: 'left', cursor: 'pointer' }}>
                  {o.symbol ? <InstrumentIcon {...pairOf(o.symbol)} size="sm" /> : <span />}
                  <span>
                    <b>{o.symbol}</b> <span className={o.direction === 'BULLISH' ? 'cc-up' : 'cc-down'}>{words(o.direction)}</span>
                    <small>{o.type_label}{o.tit_level ? ` · ${o.tit_level}` : ''} · {o.timeframe ?? '—'} · {words(o.state)}</small>
                  </span>
                  <b>{o.confidence != null ? `${o.confidence.toFixed(0)}%` : '—'}</b>
                </button>
              ))}
            </article>
          </section>

          <section className="cc-grid">
            <article className="cc-card">
              <div className="cc-card-head">
                <h2>Autonomous Engine</h2>
                <button className="cc-link" type="button" onClick={() => go('autonomous-engine')}>Open engine</button>
              </div>
              <p className="cc-muted">{words(data.system_status)} · step {data.workflow.step_of} of {data.workflow.step_count}</p>
              <div className="cc-steps">
                {data.workflow.steps.map((step) => (
                  <div key={step.key} className={`cc-step is-${step.state}`}><i />{step.label}</div>
                ))}
              </div>
              <div className="cc-bar" title={data.workflow.position_basis}><span style={{ width: `${data.workflow.position_pct}%` }} /></div>
              <p className="cc-task">{data.workflow.operation ?? 'No current operation recorded.'}{data.workflow.focus_symbol ? ` · ${data.workflow.focus_symbol}` : ''}</p>
              <p className="cc-muted">Next: {data.workflow.next_action ?? '—'}</p>
              {data.workflow.blockers.length ? <p className="cc-muted">Blockers: {data.workflow.blockers.join(' · ')}</p> : null}
              {data.workflow.errors ? <p className="cc-error">{data.workflow.errors} stage errors on this step</p> : null}
              <p className="cc-muted">{data.workflow.position_basis}</p>
            </article>

            <article className="cc-card">
              <div className="cc-card-head">
                <h2>Market Scanner ({data.scanner.total})</h2>
                <button className="cc-link" type="button" onClick={() => go('market-scanner')}>Open scanner</button>
              </div>
              <div className="cc-kpis">
                <div><b>{data.scanner.actionable}</b><span className="cc-muted">Actionable</span></div>
                <div><b>{data.scanner.watchlist}</b><span className="cc-muted">Watchlist</span></div>
                <div><b>{data.scanner.no_setup}</b><span className="cc-muted">No setup</span></div>
              </div>
              <div className="cc-stack">
                {GROUPS.map((g) => {
                  const counts = data.scanner.groups[g.key] ?? {};
                  const total = STACK.reduce((s, item) => s + (counts[item.key] ?? 0), 0) || 1;
                  return (
                    <span key={g.key} style={{ display: 'contents' }}>
                      <span>{g.label}</span>
                      <span className="cc-stack-bar">{STACK.map((item) => <i key={item.key} style={{ width: `${((counts[item.key] ?? 0) / total) * 100}%`, background: item.color }} />)}</span>
                    </span>
                  );
                })}
              </div>
              <div className="cc-legend">{STACK.map((item) => <span key={item.key}><i style={{ background: item.color }} />{item.label}</span>)}</div>
              <p className="cc-muted" style={{ marginTop: 8 }}>TIT {data.tit.count}{Object.entries(data.tit.levels).map(([k, v]) => ` · ${k} ${v}`).join('')}</p>
              {data.scanner.excluded_reasons.slice(0, 2).map((r) => <p key={r.symbol} className="cc-muted">{r.symbol}: {r.reason}</p>)}
            </article>

            <article className="cc-card">
              <div className="cc-card-head">
                <h2>Open Positions ({data.positions.broker_open})</h2>
                <button className="cc-link" type="button" onClick={() => go('execution-positions')}>View all</button>
              </div>
              <p className="cc-muted">{data.execution_note}</p>
              <p className="cc-muted">Broker orders submitted: {data.positions.orders_submitted}. Floating account P/L {money(data.account.floating_pnl, data.account.currency)}{data.account.stale ? ' · account snapshot stale' : ''}.</p>
              {data.shadow_plans.length === 0 ? <p className="cc-muted">No shadow plans are open.</p> : data.shadow_plans.map((p) => (
                <div className="cc-row" key={`${p.symbol}-${p.entry_reference}`} style={{ gridTemplateColumns: '1fr auto' }}>
                  <span><b>{p.symbol}</b> <span className="cc-muted">{words(p.direction)} · {p.type_label} · shadow</span></span>
                  <span>{p.unrealized_r != null ? `${p.unrealized_r.toFixed(2)} R` : '—'} · {words(p.order_status)}</span>
                </div>
              ))}
            </article>
          </section>

          <section className="cc-grid">
            <article className="cc-card">
              <div className="cc-card-head">
                <h2>Recent Alerts</h2>
                <button className="cc-link" type="button" onClick={() => go('h8-bos-btl')}>View H8</button>
              </div>
              {data.alerts.length === 0 ? <p className="cc-muted">No structural or notification alerts on the latest records.</p> : data.alerts.map((a, i) => (
                <div className="cc-alert" key={`${a.source}-${a.symbol}-${a.at}-${i}`}>
                  <i style={{ width: 8, height: 8, borderRadius: 99, background: a.source === 'h8' ? '#2563eb' : '#f59e0b', marginTop: 5 }} />
                  <span><b>{a.symbol} · {a.label}</b><span className="cc-muted">{a.timeframe ?? '—'}{a.direction ? ` · ${words(a.direction)}` : ''}</span></span>
                  <time className="cc-muted">{when(a.at)}</time>
                </div>
              ))}
              {data.warnings.map((w) => <p key={w} className="cc-muted">{w}</p>)}
            </article>

            <article className="cc-card">
              <div className="cc-card-head">
                <h2>System Health</h2>
                <button className="cc-link" type="button" onClick={() => go('system-control')}>System control</button>
              </div>
              <div className="cc-health">
                <div><span>API</span><b>{health?.api ?? '—'}</b></div>
                <div><span>Database</span><b>{health?.database ?? '—'}</b></div>
                <div><span>MT5</span><b>{health?.mt5?.status ?? '—'}</b></div>
                <div><span>Provider</span><b>{data.provider_connection ?? data.provider ?? '—'}</b></div>
                <div><span>Market data</span><b>{data.data_as_of ? when(data.data_as_of) : '—'}</b></div>
                <div><span>AI outlook</span><b>{words(data.outlook.state)}</b></div>
                <div><span>Workflow</span><b>{words(data.system_status)}</b></div>
                <div><span>Workers</span><b>{data.workers_online ?? '—'}/{data.workers_total ?? '—'}</b></div>
                <div><span>Execution</span><b>Blocked</b></div>
                <div><span>Safety</span><b>{words(data.safety_status)}</b></div>
              </div>
            </article>

            <Performance data={data} period={period} onPeriod={setPeriod} />
          </section>
        </>
      ) : null}
    </div>
  );
}

function Performance({ data, period, onPeriod }: { data: CommandCentre; period: 'today' | 'week' | 'month' | 'all'; onPeriod: (p: 'today' | 'week' | 'month' | 'all') => void }) {
  const daily = data.performance.daily;
  const today = daily.at(-1)?.day;
  const sliced = period === 'today' ? daily.filter((d) => d.day === today) : period === 'week' ? daily.slice(-7) : daily;
  const blocked = sliced.reduce((s, d) => s + (d.blocked || 0), 0);
  const resolved = sliced.reduce((s, d) => s + (d.resolved || 0), 0);
  return (
    <article className="cc-card">
      <div className="cc-card-head">
        <h2>Trading Performance</h2>
        <div className="cc-period">
          {(['today', 'week', 'month', 'all'] as const).map((p) => (
            <button key={p} type="button" className={period === p ? 'is-on' : ''} onClick={() => onPeriod(p)}>{p === 'today' ? 'Today' : p === 'week' ? 'Week' : p === 'month' ? 'Month' : 'All'}</button>
          ))}
        </div>
      </div>
      <p className="cc-muted">{data.performance.basis ?? 'Shadow outcomes only. Not broker-account performance.'}</p>
      <div className="cc-metrics">
        <div><span className="cc-muted">Floating P/L</span><b>{money(data.account.floating_pnl, data.account.currency)}</b></div>
        <div><span className="cc-muted">30-day hit rate</span><b>{data.performance.hit_rate != null ? `${data.performance.hit_rate}%` : '—'}</b></div>
        <div><span className="cc-muted">Average R</span><b>{data.performance.avg_r != null ? data.performance.avg_r.toFixed(2) : '—'}</b></div>
        <div><span className="cc-muted">Profit factor</span><b>{data.performance.profit_factor != null ? data.performance.profit_factor : '—'}</b></div>
        <div><span className="cc-muted">Max drawdown</span><b>{data.performance.max_drawdown_pct != null ? `${data.performance.max_drawdown_pct}%` : '—'}</b></div>
        <div><span className="cc-muted">Shadow in view</span><b>{blocked} blocked · {resolved} resolved</b></div>
      </div>
      <p className="cc-muted" style={{ marginTop: 8 }}>{data.performance.closed_30d ?? 0} closed shadow plans in 30 days. Margin used {data.account.margin_used_pct != null ? `${data.account.margin_used_pct}%` : '—'}.</p>
    </article>
  );
}

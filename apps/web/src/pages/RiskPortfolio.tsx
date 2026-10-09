import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Scale, Shield, ShieldCheck } from 'lucide-react';
import { usePollingAsync } from '../features/market-intelligence/hooks/useMarketIntelligence';
import { autonomousApi } from '../features/autonomous/api';
import { pretty, until } from '../features/autonomous/format';
import { useNow } from '../features/autonomous/components/DetailParts';
import type { PortfolioView } from '../features/autonomous/types';

const TABS = [
  ['overview', 'Portfolio Overview'],
  ['intelligence', 'Risk Intelligence'],
  ['decisions', 'Authorization Decisions'],
] as const;

type TabId = (typeof TABS)[number][0];
const COLORS = ['#2563eb', '#7c3aed', '#0d9488', '#d97706', '#dc2626', '#0891b2', '#4f46e5', '#64748b'];

function money(value: number | null | undefined, currency = 'USD') {
  if (value == null || !Number.isFinite(value)) return '—';
  return new Intl.NumberFormat('en-US', { style: 'currency', currency, maximumFractionDigits: 2 }).format(value);
}

function pct(value: number | null | undefined, digits = 1) {
  if (value == null || !Number.isFinite(value)) return '—';
  return `${value.toFixed(digits)}%`;
}

function signed(value: number | null | undefined, currency = 'USD') {
  if (value == null || !Number.isFinite(value)) return '—';
  const text = money(Math.abs(value), currency);
  return value > 0 ? `+${text}` : value < 0 ? `−${text}` : text;
}

function stamp(iso: string | null | undefined) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false }).format(d);
}

function outcomeNote(view: PortfolioView) {
  const counts = view.outcomes.counts || {};
  const mix = Object.entries(counts)
    .filter(([, n]) => n > 0)
    .map(([name, n]) => `${n} ${pretty(name).toLowerCase()}`)
    .join(', ');
  const pending = view.outcomes.closed_30d > 0 && view.outcomes.resolved === 0
    ? ' None of those plans reached a target or a stop, so hit rate and average R stay blank.'
    : '';
  return `${view.outcomes.basis}${mix ? ` ${mix}.` : ''}${pending}`;
}

function decisionTone(state: string) {
  if (state === 'RISK_APPROVED') return 'ok';
  if (state === 'RISK_DEFERRED') return 'warn';
  if (state === 'RISK_REJECTED') return 'bad';
  return 'muted';
}

export function RiskPortfolio() {
  const now = useNow();
  const [tab, setTab] = useState<TabId>('overview');
  const overview = usePollingAsync(useCallback(() => autonomousApi.overview(), []), [], { intervalMs: 5000 });
  const portfolio = usePollingAsync(useCallback(() => autonomousApi.portfolio(), []), [], { intervalMs: 5000 });
  useEffect(() => {
    const id = window.setInterval(() => { if (document.visibilityState === 'visible') autonomousApi.catchUp().catch(() => undefined); }, 15000);
    autonomousApi.catchUp().catch(() => undefined);
    return () => window.clearInterval(id);
  }, []);

  const view = portfolio.data;
  const ribbon = overview.data?.ribbon;
  const safety = overview.data?.safety;
  const account = view?.account;
  const currency = account?.currency || 'USD';
  const halted = safety?.status === 'CRITICAL' || safety?.status === 'HALTED';
  const engineTone = ribbon?.system_status === 'RUNNING' ? 'ok' : ribbon?.system_status === 'HALTED' || ribbon?.system_status === 'ERROR' ? 'bad' : 'warn';

  return (
    <div className="rsk">
      <header className="rsk-head">
        <div className="rsk-title">
          <div className="rsk-mark" aria-hidden><Shield size={22} /></div>
          <div>
            <h1>Risk & Portfolio</h1>
            <p>Autonomous risk management, portfolio control and opportunity authorization.</p>
          </div>
        </div>
        <div className="rsk-status">
          <Chip label="Risk Engine" value={pretty(ribbon?.system_status)} tone={engineTone} hint="Stage 8" />
          <Chip label="Safety Supervisor" value={pretty(safety?.status)} tone={safety?.status === 'NORMAL' ? 'ok' : safety?.status === 'DEGRADED' ? 'warn' : 'bad'} />
          <Chip label="Operating Mode" value={pretty(ribbon?.operating_mode)} hint="Analysis only" />
          <Chip label="Portfolio Risk" value={pct(view?.capacity.used_pct)} hint={`${view?.capacity.used ?? '—'} / ${view?.capacity.limit ?? '—'} plans`} />
          <Chip label="Available Capacity" value={view?.capacity.available == null ? '—' : String(view.capacity.available)} hint="Open plan slots" />
          <Chip label="Last Evaluation" value={stamp(ribbon?.last_successful_cycle)} hint={until(ribbon?.next_cycle_at, now)} />
        </div>
      </header>

      <div className="rsk-tabs" role="tablist">
        {TABS.map(([id, label]) => (
          <button type="button" key={id} role="tab" aria-selected={tab === id} className={tab === id ? 'is-on' : ''} onClick={() => setTab(id)}>{label}</button>
        ))}
      </div>

      {halted ? <div className="rsk-banner"><AlertTriangle size={16} /> The safety supervisor is {pretty(safety?.status)}. Authorization is overridden until the critical condition clears. No broker order is submitted.</div> : null}
      {account?.stale ? <div className="rsk-banner"><AlertTriangle size={16} /> Account figures were last synced {stamp(account.last_synced_at)}. The live terminal has not refreshed this row, so balance, equity and margin stay historical.</div> : null}
      {!account && !portfolio.loading ? <div className="rsk-banner"><AlertTriangle size={16} /> No synced trading account is available for this tenant. Balance, equity and margin stay blank.</div> : null}
      {portfolio.error ? <div className="rsk-banner">{portfolio.error}</div> : null}
      <div className="rsk-banner info"><ShieldCheck size={16} /> {view?.execution_note || 'Risk decisions are analysis-only and are not permission to send a broker order.'}</div>

      {tab === 'overview' && view ? <Overview view={view} currency={currency} /> : null}
      {tab === 'intelligence' && view ? <Intelligence view={view} currency={currency} /> : null}
      {tab === 'decisions' && view ? <Decisions view={view} /> : null}
      {!view && portfolio.loading ? <div className="rsk-empty">Loading the risk book…</div> : null}
    </div>
  );
}

function Overview({ view, currency }: { view: PortfolioView; currency: string }) {
  const account = view.account;
  const point = view.equity_history.points[0];
  return (
    <>
      <section className="rsk-kpis">
        <Kpi label="Account Balance" value={money(account?.balance, currency)} hint={account ? `Synced ${stamp(account.last_synced_at)}` : 'Not synced'} />
        <Kpi label="Equity" value={money(account?.equity, currency)} hint={account?.environment || '—'} />
        <Kpi label="Floating P&L" value={signed(account?.floating_pnl, currency)} hint="Equity − balance" tone={account?.floating_pnl == null ? undefined : account.floating_pnl >= 0 ? 'up' : 'down'} />
        <Kpi label="Used Margin" value={money(account?.margin, currency)} hint={pct(account?.margin_used_pct)} />
        <Kpi label="Free Margin" value={money(account?.free_margin, currency)} hint={pct(account?.free_margin_pct)} />
        <Kpi label="Daily Drawdown" value="—" hint="No equity history" />
      </section>
      <section className="rsk-grid">
        <article className="rsk-card">
          <h2>Equity <span className="rsk-note" style={{ margin: 0 }}>Latest sync</span></h2>
          <div className="rsk-equity">{money(point?.equity ?? account?.equity, currency)}</div>
          <p className="rsk-note">{view.equity_history.note}</p>
          <div className="rsk-stats">
            <Stat label="Shadow hit rate" value={view.outcomes.hit_rate == null ? (view.outcomes.closed_30d ? 'None yet' : '—') : pct(view.outcomes.hit_rate, 0)} />
            <Stat label="Closed plans" value={String(view.outcomes.closed_30d)} />
            <Stat label="Target or stop" value={String(view.outcomes.resolved)} />
            <Stat label="Average R" value={view.outcomes.avg_r == null ? (view.outcomes.closed_30d ? 'None yet' : '—') : view.outcomes.avg_r.toFixed(2)} />
            <Stat label="Profit factor" value="—" />
            <Stat label="Sharpe" value="—" />
          </div>
          <p className="rsk-note">{outcomeNote(view)}</p>
        </article>
        <article className="rsk-card">
          <h2>Currency Exposure <span className="rsk-note" style={{ margin: 0 }}>Shadow plans</span></h2>
          <ExposureBars rows={view.exposure.currencies} />
          <p className="rsk-note">{view.exposure.basis}</p>
          <div className="rsk-stats" style={{ gridTemplateColumns: '1fr 1fr 1fr' }}>
            <Stat label="Open plans" value={String(view.exposure.plans)} />
            <Stat label="Most exposed" value={view.exposure.most_exposed ? `${view.exposure.most_exposed}` : '—'} />
            <Stat label="Least exposed" value={view.exposure.least_exposed ?? '—'} />
          </div>
        </article>
        <article className="rsk-card">
          <h2>Risk Capacity</h2>
          <Capacity capacity={view.capacity} />
          <p className="rsk-note">{view.capacity.basis}</p>
        </article>
      </section>
      <section className="rsk-lower">
        <article className="rsk-card">
          <h2>Active Campaigns</h2>
          <table className="rsk-table">
            <thead>
              <tr><th>Opportunity type</th><th>Open hypotheses</th><th>Shadow plans</th><th>Slot share</th><th>Status</th></tr>
            </thead>
            <tbody>
              {view.campaigns.map((row) => (
                <tr key={row.type}>
                  <td>{row.label}</td>
                  <td>{row.active_plans}</td>
                  <td>{row.shadow_plans}</td>
                  <td>{pct(row.slot_share_pct)}</td>
                  <td><span className={`rsk-pill ${row.status === 'ACTIVE' ? 'ok' : 'muted'}`}>{pretty(row.status)}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="rsk-note">Dollar campaign allocation is not stored. Slot share is the shadow-plan count against the concurrent limit.</p>
        </article>
        <article className="rsk-card">
          <h2>Account Limits</h2>
          <Limit label="Max open positions" limit={view.limits.max_open_positions} current={null} />
          <Limit label="Concurrent shadow plans" limit={view.limits.max_concurrent} current={view.capacity.used} />
          <Limit label="Currency exposure (net plans)" limit={view.limits.max_currency_exposure} current={Math.max(0, ...view.exposure.currencies.map((c) => Math.abs(c.net_plans)), 0)} />
          <Limit label="Min reward : risk" limit={view.limits.min_reward_risk} current={null} text />
          <Limit label="Max trade risk" limit={view.limits.max_trade_risk_pct} suffix="%" current={null} />
          <Limit label="Max total risk" limit={view.limits.max_total_risk_pct} suffix="%" current={null} />
          <Limit label="Max daily loss" limit={view.limits.max_daily_loss_pct} suffix="%" current={null} />
          <p className="rsk-note">Max open positions is the broker-position cap. The live position book is not loaded, so that count stays blank. Dollar usage stays blank until a position is sized. A bar turns amber at the cap and red above it.</p>
        </article>
      </section>
      <section className="rsk-lower">
        <Decisions view={view} compact />
        <article className="rsk-card">
          <h2>Portfolio Distribution</h2>
          <Distribution rows={view.distribution} />
          <p className="rsk-note">Share of open analysis-only plans by opportunity type.</p>
        </article>
      </section>
    </>
  );
}

function Intelligence({ view, currency }: { view: PortfolioView; currency: string }) {
  const account = view.account;
  return (
    <div className="rsk-two">
      <article className="rsk-card">
        <h2>Currency Exposure</h2>
        <ExposureBars rows={view.exposure.currencies} />
        <p className="rsk-note">{view.exposure.basis}</p>
      </article>
      <article className="rsk-card">
        <h2>Margin</h2>
        <div className="rsk-stats" style={{ gridTemplateColumns: '1fr 1fr' }}>
          <Stat label="Used margin" value={money(account?.margin, currency)} />
          <Stat label="Free margin" value={money(account?.free_margin, currency)} />
          <Stat label="Used" value={pct(account?.margin_used_pct)} />
          <Stat label="Leverage" value={account?.leverage || '—'} />
        </div>
        <p className="rsk-note">From the last trading-account sync{account?.stale ? ' (stale)' : ''}.</p>
      </article>
      <article className="rsk-card">
        <h2>Concentration</h2>
        <table className="rsk-table">
          <thead><tr><th>Type</th><th>Hypotheses</th><th>Shadow plans</th></tr></thead>
          <tbody>
            {view.campaigns.map((row) => (
              <tr key={row.type}><td>{row.label}</td><td>{row.active_plans}</td><td>{row.shadow_plans}</td></tr>
            ))}
          </tbody>
        </table>
      </article>
      <article className="rsk-card">
        <h2>Account Restrictions</h2>
        <div className="rsk-limit"><span>Environment</span><b>{account?.environment || '—'}</b></div>
        <div className="rsk-limit"><span>Weekend holding</span><b>{view.limits.weekend_holding_allowed == null ? '—' : view.limits.weekend_holding_allowed ? 'Allowed' : 'Blocked'}</b></div>
        <div className="rsk-limit"><span>Max daily loss</span><b>{pct(view.limits.max_daily_loss_pct)}</b></div>
        <div className="rsk-limit"><span>Max total loss</span><b>{pct(view.limits.max_total_loss_pct)}</b></div>
        <div className="rsk-limit"><span>Profit target</span><b>{pct(view.limits.profit_target_pct)}</b></div>
        <div className="rsk-limit"><span>Min confidence</span><b>{view.limits.min_confidence == null ? '—' : view.limits.min_confidence}</b></div>
        <p className="rsk-note">Pair-correlation coefficients and stress scenarios are not calculated. Broker positions are not loaded while execution is blocked.</p>
      </article>
    </div>
  );
}

function Decisions({ view, compact = false }: { view: PortfolioView; compact?: boolean }) {
  const rows = compact ? view.decisions.slice(0, 6) : view.decisions;
  return (
    <article className="rsk-card">
      <h2>Recent Authorization Decisions <span className="rsk-note" style={{ margin: 0 }}>{view.decision_counts.RISK_APPROVED} authorised · {view.decision_counts.RISK_DEFERRED} deferred · {view.decision_counts.RISK_REJECTED} rejected</span></h2>
      <table className="rsk-table">
        <thead>
          <tr>
            <th>Time</th><th>Symbol</th><th>Direction</th><th>Type</th><th>R:R</th><th>Decision</th><th>Rule</th><th>Reason</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td>{stamp(row.at)}</td>
              <td>{row.symbol || '—'}</td>
              <td>{row.direction === 'BULLISH' ? 'Bullish' : row.direction === 'BEARISH' ? 'Bearish' : '—'}</td>
              <td>{row.type_label || '—'}</td>
              <td>{row.reward_risk == null ? '—' : Number(row.reward_risk).toFixed(2)}</td>
              <td><span className={`rsk-pill ${decisionTone(row.state)}`}>{pretty(row.state)}</span></td>
              <td>{row.rule || '—'}</td>
              <td>{row.detail || pretty(row.reason_code)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {!rows.length ? <div className="rsk-empty">No Stage 8 decisions have been recorded yet. Waiting is a valid state.</div> : null}
      <p className="rsk-note">{rows[0]?.position_size_note || view.execution_note} Position size and stop distance are left blank.</p>
    </article>
  );
}

function ExposureBars({ rows }: { rows: PortfolioView['exposure']['currencies'] }) {
  if (!rows.length) return <div className="rsk-empty">No analysis-only currency exposure.</div>;
  return (
    <div className="rsk-bars">
      {rows.map((row, i) => (
        <div className="rsk-bar" key={row.currency}>
          <b>{row.currency}</b>
          <i><b style={{ width: `${row.share_pct}%`, background: COLORS[i % COLORS.length] }} /></i>
          <span>{row.net_plans > 0 ? `+${row.net_plans}` : row.net_plans}</span>
        </div>
      ))}
    </div>
  );
}

function Capacity({ capacity }: { capacity: PortfolioView['capacity'] }) {
  const used = capacity.used_pct ?? 0;
  const r = 42;
  const c = 2 * Math.PI * r;
  const dash = (Math.max(0, Math.min(100, used)) / 100) * c;
  return (
    <div className="rsk-split">
      <svg className="rsk-donut" viewBox="0 0 108 108" aria-label="Shadow plan capacity">
        <circle cx="54" cy="54" r={r} fill="none" stroke="#e8eef6" strokeWidth="12" />
        <circle cx="54" cy="54" r={r} fill="none" stroke="#2563eb" strokeWidth="12" strokeDasharray={`${dash} ${c - dash}`} strokeLinecap="round" transform="rotate(-90 54 54)" />
        <text x="54" y="52" textAnchor="middle" fontSize="14" fontWeight="700">{capacity.used_pct == null ? '—' : `${capacity.used_pct.toFixed(1)}%`}</text>
        <text x="54" y="68" textAnchor="middle" fontSize="9" fill="#667085">plans</text>
      </svg>
      <div className="rsk-legend">
        <div><span><i className="rsk-swatch" style={{ background: '#2563eb' }} />Used</span><b>{capacity.used}</b></div>
        <div><span><i className="rsk-swatch" style={{ background: '#e8eef6' }} />Available</span><b>{capacity.available ?? '—'}</b></div>
        <div><span>Limit</span><b>{capacity.limit}</b></div>
      </div>
    </div>
  );
}

function Distribution({ rows }: { rows: PortfolioView['distribution'] }) {
  if (!rows.length) return <div className="rsk-empty">No open shadow plans to distribute.</div>;
  const c = 2 * Math.PI * 36;
  let offset = 0;
  const slices = rows.map((row, i) => {
    const len = (row.share_pct / 100) * c;
    const slice = { ...row, color: COLORS[i % COLORS.length], dash: `${len} ${c - len}`, offset };
    offset -= len;
    return slice;
  });
  return (
    <div className="rsk-split">
      <svg className="rsk-donut" viewBox="0 0 108 108" aria-label="Plan distribution">
        <circle cx="54" cy="54" r="36" fill="none" stroke="#eef2f6" strokeWidth="14" />
        {slices.map((slice) => (
          <circle key={slice.type} cx="54" cy="54" r="36" fill="none" stroke={slice.color} strokeWidth="14" strokeDasharray={slice.dash} strokeDashoffset={slice.offset} transform="rotate(-90 54 54)" />
        ))}
      </svg>
      <div className="rsk-legend">
        {slices.map((slice) => (
          <div key={slice.type}><span><i className="rsk-swatch" style={{ background: slice.color }} />{slice.label}</span><b>{pct(slice.share_pct, 0)}</b></div>
        ))}
      </div>
    </div>
  );
}

function Limit({ label, limit, current, suffix = '', text = false }: { label: string; limit: number | null; current: number | null; suffix?: string; text?: boolean }) {
  if (limit == null && current == null) {
    return (
      <div className="rsk-limit">
        <div style={{ flex: 1, display: 'flex', justifyContent: 'space-between' }}><span>{label}</span><b>Not set</b></div>
      </div>
    );
  }
  const over = current != null && limit != null && current > limit;
  const atCap = current != null && limit != null && current === limit;
  const width = limit && current != null ? Math.max(0, Math.min(100, (current / limit) * 100)) : 0;
  const tone = over ? 'is-over' : atCap ? 'is-cap' : '';
  return (
    <div className="rsk-limit">
      <div style={{ flex: 1 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span>{label}</span>
          <b style={{ color: over ? '#dc2626' : atCap ? '#b45309' : undefined }}>
            {current == null ? '—' : text ? current : `${current}${suffix}`} / {limit == null ? '—' : text ? limit : `${limit}${suffix}`}
            {over ? ' over' : ''}
          </b>
        </div>
        {current != null && limit ? <div className="rsk-meter"><i className={tone} style={{ width: `${width}%` }} /></div> : null}
      </div>
    </div>
  );
}

function Chip({ label, value, tone, hint }: { label: string; value: string; tone?: 'ok' | 'warn' | 'bad'; hint?: string }) {
  return (
    <div className="rsk-chip">
      <span>{label}</span>
      <b>{tone ? <i className={`rsk-dot ${tone}`} /> : null}{value}</b>
      {hint ? <small style={{ color: 'var(--muted)', fontSize: 10 }}>{hint}</small> : null}
    </div>
  );
}

function Kpi({ label, value, hint, tone }: { label: string; value: string; hint: string; tone?: 'up' | 'down' }) {
  return (
    <article className={`rsk-kpi ${tone || ''}`}>
      <span><Scale size={14} />{label}</span>
      <b>{value}</b>
      <small>{hint}</small>
    </article>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return <div><span>{label}</span><b>{value}</b></div>;
}

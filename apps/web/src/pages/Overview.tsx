import React from 'react';
import {
  Activity,
  BarChart3,
  Briefcase,
  Calendar,
  ChevronRight,
  LayoutGrid,
  LineChart,
  Link2,
  Radio,
  Target,
  User,
  Wallet,
} from 'lucide-react';
import type { ConnectionsPayload, Health, Summary, Tenant, TradingAccount, AuditEvent } from '../types';
import { marketIntelligenceApi } from '../features/market-intelligence/api';
import { get } from '../lib/api';
import { writeHashRoute, type Page } from '../lib/routes';

function fmtClock(d: Date) {
  return d.toLocaleString(undefined, {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    timeZoneName: 'shortOffset',
  });
}

function fmtShortTs(v?: string | null) {
  if (!v) return '—';
  try {
    return new Date(v).toLocaleString(undefined, {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return v;
  }
}

function auditLabel(action: string) {
  const map: Record<string, string> = {
    MT5_CONNECT: 'MT5 gateway connected',
    MT5_DISCONNECT: 'MT5 gateway disconnected',
    MT5_AUTO_LINK: 'Account linked from MT5 terminal',
    MT5_SETTINGS_UPDATED: 'MT5 connection settings updated',
    TRADING_ACCOUNT_CREATED: 'Trading account registered',
    CONNECTION_CONFIGURED: 'Trading connection configured',
  };
  return map[action] ?? action.replaceAll('_', ' ');
}

export function Overview({
  health,
  summary,
  tenant,
  tenantId,
  instrumentCount = 29,
}: {
  health: Health | null;
  summary: Summary | null;
  tenant?: Tenant;
  tenantId: string;
  instrumentCount?: number;
}) {
  const [miReady, setMiReady] = React.useState(false);
  const [accounts, setAccounts] = React.useState<TradingAccount[]>([]);
  const [recentAudit, setRecentAudit] = React.useState<AuditEvent[]>([]);
  const [connections, setConnections] = React.useState<ConnectionsPayload | null>(null);
  const [now, setNow] = React.useState(() => new Date());
  const [chartRange, setChartRange] = React.useState('1D');

  React.useEffect(() => {
    const t = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(t);
  }, []);

  React.useEffect(() => {
    marketIntelligenceApi.health().then((h) => setMiReady(h.status === 'ready')).catch(() => setMiReady(false));
  }, []);

  const loadTenantData = React.useCallback(() => {
    if (!tenantId) return;
    get<TradingAccount[]>(`/tenants/${tenantId}/accounts`)
      .then((acc) => {
        setAccounts(acc);
        return get<ConnectionsPayload>(`/tenants/${tenantId}/connections`);
      })
      .then((conn) => setConnections(conn))
      .catch(() => undefined);
    get<AuditEvent[]>(`/tenants/${tenantId}/audit?limit=8`).then(setRecentAudit).catch(() => setRecentAudit([]));
  }, [tenantId]);

  React.useEffect(() => {
    loadTenantData();
  }, [loadTenantData, health?.mt5?.status]);

  React.useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === 'visible') loadTenantData();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, [loadTenantData]);

  const go = (page: Page, tab?: string) => {
    writeHashRoute(page, tab);
    window.dispatchEvent(new HashChangeEvent('hashchange'));
  };

  const balance = accounts.reduce((s, a) => s + (a.balance ?? 0), 0);
  const equity = accounts.reduce((s, a) => s + (a.equity ?? 0), 0);
  const freeMargin = accounts.reduce((s, a) => s + (a.free_margin ?? 0), 0);
  const primary = accounts[0];
  const currency = primary?.account_currency ?? tenant?.reporting_currency ?? 'USD';
  const terminal = connections?.diagnostics?.terminal_account;
  const registryRow = connections?.connections?.[0];
  const mt5Server =
    primary?.server ?? registryRow?.account_server ?? registryRow?.server_name ?? terminal?.server ?? '—';
  const mt5Login = primary?.account_number ?? terminal?.login ?? '—';
  const nextBarSec = 60 - (now.getSeconds() % 60);
  const nextUpdateLabel = miReady ? `00:00:${String(nextBarSec).padStart(2, '0')}` : '—';

  const mt5Status = health?.mt5?.status ?? 'DISCONNECTED';
  const mt5Persisted = health?.mt5?.session_status === 'CONNECTED';
  const mt5Connected = mt5Status === 'CONNECTED' || mt5Persisted;
  const apiOk = health?.api === 'HEALTHY';
  const dbOk = health?.database === 'HEALTHY';
  const systemOk = apiOk && dbOk;

  const marginUsedPct =
    equity > 0 && freeMargin >= 0 ? Math.min(100, Math.max(0, ((equity - freeMargin) / equity) * 100)) : 0;

  return (
    <div className="ov-dashboard">
      <header className="ov-hero">
        <div className="ov-hero-title">
          <div className="ov-hero-icon" aria-hidden>
            <LayoutGrid />
          </div>
          <div>
            <h1>Overview</h1>
            <p>Operational command surface — live platform context, health and autonomous posture.</p>
          </div>
        </div>
        <div className="ov-hero-meta">
          <div className="ov-datetime">
            <Calendar aria-hidden />
            {fmtClock(now)}
          </div>
          <div className={systemOk ? 'ov-system-ok' : 'ov-system-ok degraded'}>
            <strong>{systemOk ? 'SYSTEM OPERATIONAL' : 'SYSTEM DEGRADED'}</strong>
            <span>{systemOk ? 'All core services healthy' : 'One or more core services need attention'}</span>
          </div>
        </div>
      </header>

      <div className="ov-kpi-row">
        <article className="ov-kpi">
          <div className="ov-kpi-icon blue">
            <User aria-hidden />
          </div>
          <div className="ov-kpi-body">
            <span className="ov-kpi-label">Tenant &amp; account</span>
            <span className="ov-kpi-value">
              {tenant?.name ?? '—'} · {currency}
            </span>
            <span className="ov-kpi-sub">
              {accounts.length || summary?.accounts || 0} registered account
              {(accounts.length || summary?.accounts || 0) === 1 ? '' : 's'}
            </span>
          </div>
        </article>
        <article className="ov-kpi">
          <div className="ov-kpi-icon green">
            <Wallet aria-hidden />
          </div>
          <div className="ov-kpi-body">
            <span className="ov-kpi-label">Total balance</span>
            <span className="ov-kpi-value">
              {accounts.length ? `${balance.toFixed(2)} ${currency}` : `— ${currency}`}
            </span>
            <span className="ov-kpi-sub">
              Equity {equity.toFixed(2)} · Free margin {freeMargin.toFixed(2)}
            </span>
          </div>
        </article>
        <article className="ov-kpi">
          <div className="ov-kpi-icon purple">
            <BarChart3 aria-hidden />
          </div>
          <div className="ov-kpi-body">
            <span className="ov-kpi-label">Instruments monitored</span>
            <span className="ov-kpi-value">{instrumentCount}</span>
            <span className="ov-kpi-sub">Reference universe</span>
          </div>
        </article>
        <article className="ov-kpi">
          <div className="ov-kpi-icon orange">
            <Target aria-hidden />
          </div>
          <div className="ov-kpi-body">
            <span className="ov-kpi-label">Active opportunities</span>
            <span className="ov-kpi-value">0</span>
            <span className="ov-kpi-sub">Opportunity engine not connected</span>
          </div>
        </article>
        <article className="ov-kpi">
          <div className="ov-kpi-icon red">
            <Briefcase aria-hidden />
          </div>
          <div className="ov-kpi-body">
            <span className="ov-kpi-label">Open positions</span>
            <span className="ov-kpi-value">0</span>
            <span className="ov-kpi-sub">Execution layer disabled</span>
          </div>
        </article>
      </div>

      <div className="ov-triple-row ov-row-mid">
        <article className="ov-panel">
          <div className="ov-panel-head">
            <div className="ov-panel-title">
              <div className="ov-panel-title-icon">
                <Radio aria-hidden />
              </div>
              <h2>MT5 connection</h2>
            </div>
            <span className={`ov-badge ${mt5Connected ? 'success' : 'neutral'}`}>
              {mt5Connected ? 'CONNECTED' : 'DISCONNECTED'}
            </span>
          </div>
          <dl className="ov-dl">
            <div className="ov-dl-row">
              <dt>Server</dt>
              <dd>{mt5Server}</dd>
            </div>
            <div className="ov-dl-row">
              <dt>Login</dt>
              <dd>{mt5Login}</dd>
            </div>
            <div className="ov-dl-row">
              <dt>Connection time</dt>
              <dd>{fmtShortTs(health?.mt5?.last_connected_at)}</dd>
            </div>
            <div className="ov-dl-row">
              <dt>Last heartbeat</dt>
              <dd>
                {health?.mt5?.heartbeat_at
                  ? `${fmtShortTs(health.mt5.heartbeat_at)}${mt5Status === 'CONNECTED' ? ' (Live)' : ''}`
                  : '—'}
              </dd>
            </div>
          </dl>
          <div className="ov-link-foot">
            <button type="button" onClick={() => go('system-control', 'mt5')}>
              View details <ChevronRight size={14} aria-hidden />
            </button>
          </div>
        </article>

        <article className="ov-panel">
          <div className="ov-panel-head">
            <div className="ov-panel-title">
              <div className="ov-panel-title-icon">
                <LineChart aria-hidden />
              </div>
              <h2>Market data status</h2>
            </div>
            <span className={`ov-badge ${miReady ? 'success' : 'neutral'}`}>{miReady ? 'READY' : 'OFFLINE'}</span>
          </div>
          <dl className="ov-dl">
            <div className="ov-dl-row">
              <dt>Data source</dt>
              <dd>{mt5Connected ? 'MT5 (Live)' : 'MT5 (Pending)'}</dd>
            </div>
            <div className="ov-dl-row">
              <dt>Instruments</dt>
              <dd>
                {instrumentCount} (FX + XAUUSD)
              </dd>
            </div>
            <div className="ov-dl-row">
              <dt>Last update</dt>
              <dd>{miReady ? fmtShortTs(now.toISOString()) : '—'}</dd>
            </div>
            <div className="ov-dl-row">
              <dt>Next update</dt>
              <dd>{nextUpdateLabel}</dd>
            </div>
          </dl>
          <div className="ov-link-foot">
            <button type="button" onClick={() => go('strength-intelligence')}>
              View details <ChevronRight size={14} aria-hidden />
            </button>
          </div>
        </article>

        <article className="ov-panel">
          <div className="ov-panel-head">
            <div className="ov-panel-title">
              <div className="ov-panel-title-icon">
                <Activity aria-hidden />
              </div>
              <h2>Autonomous engine health</h2>
            </div>
            <span className={`ov-badge ${miReady ? 'warning' : 'neutral'}`}>PARTIAL</span>
          </div>
          <ul className="ov-engine-list">
            <li>
              <span>Market intelligence</span>
              <span className={`ov-engine-dot ${miReady ? 'green' : 'orange'}`}>
                <i aria-hidden /> {miReady ? 'Healthy' : 'Awaiting worker'}
              </span>
            </li>
            <li>
              <span>Workflow Orchestrator</span>
              <span className="ov-engine-dot orange">
                <i aria-hidden /> Paused
              </span>
            </li>
            <li>
              <span>Execution Engine</span>
              <span className="ov-engine-dot red">
                <i aria-hidden /> Disabled (Analysis Only)
              </span>
            </li>
            <li>
              <span>Risk Engine</span>
              <span className="ov-engine-dot orange">
                <i aria-hidden /> Paused
              </span>
            </li>
            <li>
              <span>AI Engine</span>
              <span className="ov-engine-dot orange">
                <i aria-hidden /> Paused
              </span>
            </li>
          </ul>
          <div className="ov-link-foot">
            <button type="button" onClick={() => go('workflow-engine')}>
              View details <ChevronRight size={14} aria-hidden />
            </button>
          </div>
        </article>
      </div>

      <div className="ov-triple-row ov-row-bot">
        <article className="ov-panel ov-chart-panel">
          <div className="ov-chart-head">
            <div className="ov-chart-title-row">
              <div className="ov-panel-title-icon" aria-hidden>
                <BarChart3 />
              </div>
              <h2 className="ov-panel-heading">Account balance &amp; equity</h2>
            </div>
            <div className="ov-chart-tabs" role="tablist" aria-label="Chart range">
              {(['1D', '1W', '1M', '3M', '1Y'] as const).map((r) => (
                <button
                  key={r}
                  type="button"
                  role="tab"
                  aria-selected={chartRange === r}
                  className={chartRange === r ? 'ov-chart-tab active' : 'ov-chart-tab'}
                  onClick={() => setChartRange(r)}
                >
                  {r}
                </button>
              ))}
            </div>
          </div>
          <div className="ov-chart-legend">
            <span>
              <i className="balance" aria-hidden /> Balance
            </span>
            <span>
              <i className="equity" aria-hidden /> Equity
            </span>
          </div>
          <BalanceEquityChart
            balance={balance}
            equity={equity}
            currency={currency}
            active={hasFinancialActivity(balance, equity)}
          />
        </article>

        <article className="ov-panel">
          <div className="ov-activity-head">
            <h2>Recent activity / alerts</h2>
            <button type="button" className="ov-link-foot" style={{ padding: 0 }} onClick={() => go('system-control', 'audit')}>
              View all
            </button>
          </div>
          {recentAudit.length === 0 ? (
            <p className="muted ov-activity-empty" style={{ margin: 0 }}>
              No recent audit events. Connect MT5 and link accounts in System Control.
            </p>
          ) : (
            <ul className="ov-activity-list">
              {recentAudit.slice(0, 3).map((e) => (
                <li key={e.id} className="ov-activity-item">
                  <div className="ov-activity-icon">
                    <Link2 aria-hidden />
                    <span className={`ov-activity-dot ${auditDotClass(e.action)}`} aria-hidden />
                  </div>
                  <div className="ov-activity-body">
                    <b>{e.action}</b>
                    <span>{auditLabel(e.action)}</span>
                    <time dateTime={e.created_at}>{fmtShortTs(e.created_at)}</time>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </article>

        <article className="ov-panel">
          <div className="ov-panel-head">
            <h2 className="ov-panel-heading">Portfolio risk</h2>
            <button type="button" className="ov-link-foot" style={{ padding: 0, margin: 0 }} onClick={() => go('risk-portfolio')}>
              View details
            </button>
          </div>
          <div className="ov-risk-body">
            <div className="ov-donut" style={{ '--pct': `${marginUsedPct * 3.6}deg` } as React.CSSProperties}>
              <div className="ov-donut-label">
                {marginUsedPct.toFixed(0)}%
                <br />
                Risk usage
              </div>
            </div>
            <div className="ov-risk-metrics">
              <div>
                <span>Current risk</span>
                <b>0.00%</b>
              </div>
              <div>
                <span>Daily P/L</span>
                <b>0.00 {currency}</b>
              </div>
              <div>
                <span>Open risk</span>
                <b>0.00 {currency}</b>
              </div>
              <div>
                <span>Margin usage</span>
                <b>{marginUsedPct.toFixed(2)}%</b>
              </div>
            </div>
          </div>
        </article>
      </div>

      <section className="ov-platform" aria-label="Platform health">
        <div className="ov-platform-head">
          <h2>Platform health</h2>
          <button type="button" className="ov-link-foot" style={{ padding: 0, margin: 0 }} onClick={() => go('system-control')}>
            View system control <ChevronRight size={14} aria-hidden />
          </button>
        </div>
        <div className="ov-pills">
          <span className={`ov-pill ${apiOk ? 'green' : 'red'}`}>
            <i aria-hidden /> API · {apiOk ? 'Healthy' : 'Degraded'}
          </span>
          <span className={`ov-pill ${dbOk ? 'green' : 'red'}`}>
            <i aria-hidden /> SQLite · {dbOk ? 'Healthy' : 'Degraded'}
          </span>
          <span className={`ov-pill ${miReady ? 'green' : 'orange'}`}>
            <i aria-hidden /> Market data · {miReady ? 'Ready' : 'Pending'}
          </span>
          <span className={`ov-pill ${mt5Connected ? 'green' : 'orange'}`}>
            <i aria-hidden /> MT5 · {mt5Connected ? 'Connected' : 'Disconnected'}
          </span>
          <span className="ov-pill orange">
            <i aria-hidden /> Workers · Paused
          </span>
          <span className="ov-pill orange">
            <i aria-hidden /> AI engine · Paused
          </span>
          <span className="ov-pill orange">
            <i aria-hidden /> Risk engine · Paused
          </span>
          <span className="ov-pill red">
            <i aria-hidden /> Execution · Disabled
          </span>
        </div>
      </section>
    </div>
  );
}

function hasFinancialActivity(balance: number, equity: number) {
  return balance !== 0 || equity !== 0;
}

function auditDotClass(action: string) {
  if (/CONNECT|AUTO_LINK|CREATED/i.test(action)) return 'green';
  if (/DISCONNECT|ERROR|REMOVED/i.test(action)) return 'orange';
  return 'blue';
}

const CHART_X_LABELS = ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00'];
const CHART_Y_LABELS = ['1.0', '0.5', '0.0'];

function BalanceEquityChart({
  balance,
  equity,
  currency,
  active,
}: {
  balance: number;
  equity: number;
  currency: string;
  active: boolean;
}) {
  const max = Math.max(balance, equity, 1);
  const bY = 88 - (balance / max) * 72;
  const eY = 88 - (equity / max) * 72;
  return (
    <div className="ov-chart-frame">
      <svg className="ov-chart-svg" viewBox="0 0 400 110" preserveAspectRatio="none" aria-hidden>
        {CHART_Y_LABELS.map((label, i) => {
          const y = 14 + i * 37;
          return (
            <g key={label}>
              <text x="4" y={y + 3} className="ov-chart-axis">
                {label}
              </text>
              <line x1="28" x2="392" y1={y} y2={y} stroke="#e8edf3" strokeWidth="1" />
            </g>
          );
        })}
        <line x1="28" y1="88" x2="392" y2="88" stroke="#cbd5e1" strokeWidth="1" />
        {CHART_X_LABELS.map((label, i) => {
          const x = 28 + (364 / (CHART_X_LABELS.length - 1)) * i;
          return (
            <text key={label} x={x} y="106" textAnchor="middle" className="ov-chart-axis">
              {label}
            </text>
          );
        })}
        {active ? (
          <>
            <polyline
              fill="none"
              stroke="#2563eb"
              strokeWidth="2"
              points={`28,88 100,${bY} 200,${bY + 6} 300,${bY - 3} 392,${bY}`}
            />
            <polyline
              fill="none"
              stroke="#67e8f9"
              strokeWidth="2"
              points={`28,88 100,${eY} 200,${eY - 5} 300,${eY + 2} 392,${eY}`}
            />
          </>
        ) : null}
      </svg>
      {!active ? (
        <div className="ov-chart-empty-state">
          <div className="ov-chart-empty-icon" aria-hidden>
            <BarChart3 />
          </div>
          <b>No trading activity yet</b>
          <span>Account balance data will appear here once trading is active.</span>
        </div>
      ) : (
        <p className="ov-chart-live-hint">
          Live {balance.toFixed(2)} {currency} · Equity {equity.toFixed(2)} {currency}
        </p>
      )}
    </div>
  );
}

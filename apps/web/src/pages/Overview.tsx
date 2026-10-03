import React from 'react';
import { Bell, Building2, LineChart, Radio, Server } from 'lucide-react';
import { Card, PageHeader, Status } from '../components/Ui';
import { SectionCard } from '../components/SectionCard';
import type { AuthUser, Health, Summary, Tenant, TradingAccount, AuditEvent } from '../types';
import { marketIntelligenceApi } from '../features/market-intelligence/api';
import { get } from '../lib/api';

export function Overview({
  health,
  summary,
  tenant,
  user,
  tenantId,
  instrumentCount = 29,
}: {
  health: Health | null;
  summary: Summary | null;
  tenant?: Tenant;
  user?: AuthUser | null;
  tenantId: string;
  instrumentCount?: number;
}) {
  const [miReady, setMiReady] = React.useState(false);
  const [accounts, setAccounts] = React.useState<TradingAccount[]>([]);
  const [recentAudit, setRecentAudit] = React.useState<AuditEvent[]>([]);

  React.useEffect(() => {
    marketIntelligenceApi.health().then((h) => setMiReady(h.status === 'ready')).catch(() => setMiReady(false));
  }, []);

  React.useEffect(() => {
    if (!tenantId) return;
    get<TradingAccount[]>(`/tenants/${tenantId}/accounts`).then(setAccounts).catch(() => setAccounts([]));
    get<AuditEvent[]>(`/tenants/${tenantId}/audit?limit=8`).then(setRecentAudit).catch(() => setRecentAudit([]));
  }, [tenantId]);

  const balance = accounts.reduce((s, a) => s + (a.balance ?? 0), 0);
  const equity = accounts.reduce((s, a) => s + (a.equity ?? 0), 0);
  const primary = accounts[0];

  return (
    <>
      <PageHeader
        title="Overview"
        subtitle="Operational command surface — live platform context, health and autonomous posture."
      />
      <div className="overview-grid">
        <SectionCard title="Tenant & trading account context" description="Active workspace and registry.">
          <div className="kv-list">
            <Kv k="Tenant" v={tenant?.name ?? '—'} />
            <Kv k="Reporting currency" v={tenant?.reporting_currency ?? 'USD'} />
            <Kv k="Registered accounts" v={String(summary?.accounts ?? accounts.length)} />
            <Kv k="Operator" v={user?.display_name ?? user?.username ?? '—'} />
          </div>
        </SectionCard>

        <SectionCard title="Account balance / equity / margin" description="Aggregated from trading account registry.">
          <div className="kv-list">
            <Kv k="Total balance" v={accounts.length ? balance.toFixed(2) : '—'} />
            <Kv k="Total equity" v={accounts.length ? equity.toFixed(2) : '—'} />
            <Kv k="Primary account" v={primary?.account_name ?? 'None registered'} />
            <Kv k="Free margin" v="—" hint="Requires MT5 sync" />
          </div>
        </SectionCard>

        <SectionCard title="MT5 connection status">
          <Status value={health?.mt5?.status ?? 'DISCONNECTED'} />
          <p className="muted section-hint">{health?.mt5?.message ?? health?.mt5?.adapter ?? 'LOCAL_MT5'}</p>
        </SectionCard>

        <SectionCard title="Market data status">
          <Status value={miReady ? 'READY' : 'DISCONNECTED'} />
          <p className="muted section-hint">Strength intelligence API · closed-bar policy</p>
        </SectionCard>

        <SectionCard title="Operating mode">
          <Status value={summary?.mode ?? 'ANALYSIS_ONLY'} />
        </SectionCard>

        <SectionCard title="Autonomous engine health">
          <div className="kv-list">
            <Kv k="Market intelligence" v={miReady ? 'API ready' : 'Awaiting worker'} />
            <Kv k="Workflow orchestrator" v="Awaiting integration" />
            <Kv k="Execution path" v="Disabled (analysis-only)" />
          </div>
        </SectionCard>

        <SectionCard title="Instruments monitored">
          <strong className="overview-stat">{instrumentCount}</strong>
          <p className="muted section-hint">Reference universe (FX + XAUUSD)</p>
        </SectionCard>

        <SectionCard title="Active opportunities">
          <strong className="overview-stat">0</strong>
          <p className="muted section-hint">Opportunity engine not connected</p>
        </SectionCard>

        <SectionCard title="Open positions">
          <strong className="overview-stat">0</strong>
          <p className="muted section-hint">Execution layer disabled</p>
        </SectionCard>

        <SectionCard title="Portfolio risk">
          <strong className="overview-stat">—</strong>
          <p className="muted section-hint">Risk authorization engine pending</p>
        </SectionCard>

        <SectionCard title="Recent activity / alerts" description="Latest tenant audit events.">
          {recentAudit.length === 0 ? (
            <p className="muted">No recent audit events. Administrative actions appear here automatically.</p>
          ) : (
            <ul className="activity-list">
              {recentAudit.slice(0, 5).map((e) => (
                <li key={e.id}>
                  <Bell size={14} />
                  <span>
                    <b>{e.action}</b> · {e.created_at}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
      </div>

      <div className="metric-grid">
        <Card className="metric">
          <div className="metric-icon">
            <Server />
          </div>
          <div>
            <span>API</span>
            <strong>{health?.api ?? 'OFFLINE'}</strong>
          </div>
        </Card>
        <Card className="metric">
          <div className="metric-icon">
            <Building2 />
          </div>
          <div>
            <span>SQLite</span>
            <strong>{health?.database ?? '—'}</strong>
          </div>
        </Card>
        <Card className="metric">
          <div className="metric-icon">
            <Radio />
          </div>
          <div>
            <span>MT5</span>
            <strong>{health?.mt5?.status ?? 'DISCONNECTED'}</strong>
          </div>
        </Card>
        <Card className="metric">
          <div className="metric-icon">
            <LineChart />
          </div>
          <div>
            <span>Connections</span>
            <strong>{summary?.connections ?? 0}</strong>
          </div>
        </Card>
      </div>
    </>
  );
}

function Kv({ k, v, hint }: { k: string; v: string; hint?: string }) {
  return (
    <div className="kv-row">
      <span>{k}</span>
      <div>
        <b>{v}</b>
        {hint && <small>{hint}</small>}
      </div>
    </div>
  );
}

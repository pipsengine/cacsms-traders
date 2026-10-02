import React from 'react';
import {
  Activity,
  Building2,
  Database,
  Radio,
  Server,
  ShieldCheck,
  TrendingUp,
  Users,
  WalletCards,
  Workflow,
} from 'lucide-react';
import { Card, PageHeader, Status } from '../components/Ui';
import type { AuthUser, Health, Summary, Tenant } from '../types';
import { marketIntelligenceApi } from '../features/market-intelligence/api';

export function Overview({
  health,
  summary,
  tenant,
  user,
  instrumentCount = 29,
}: {
  health: Health | null;
  summary: Summary | null;
  tenant?: Tenant;
  user?: AuthUser | null;
  instrumentCount?: number;
}) {
  const [miStatus, setMiStatus] = React.useState<string>('CHECKING');
  const [escalations, setEscalations] = React.useState(0);

  React.useEffect(() => {
    marketIntelligenceApi
      .health()
      .then((h) => setMiStatus(h.status === 'ready' ? 'READY' : 'PAUSED'))
      .catch(() => setMiStatus('OFFLINE'));
    marketIntelligenceApi
      .relationships()
      .then((rows) =>
        setEscalations(rows.filter((r) => r.inspection_priority === 'HIGH' || r.inspection_priority === 'CRITICAL').length),
      )
      .catch(() => setEscalations(0));
  }, []);

  return (
    <>
      <PageHeader
        title="Overview"
        subtitle="Operational dashboard — tenant context, platform health, intelligence status and activity."
      />
      <div className="metric-grid">
        <Metric icon={<Building2 />} label="Active tenant" value={tenant?.name ?? '—'} detail={tenant?.reporting_currency ?? 'USD'} />
        <Metric icon={<Users />} label="Platform users" value={String(summary?.users ?? '—')} detail="RBAC enforced" />
        <Metric icon={<WalletCards />} label="Trading accounts" value={String(summary?.accounts ?? 0)} detail="Registry" />
        <Metric icon={<Database />} label="Database" value={health?.database ?? 'CHECKING'} detail="SQLite · WAL" />
      </div>
      <div className="metric-grid">
        <Metric icon={<Server />} label="API" value={health?.api ?? 'OFFLINE'} detail="FastAPI" />
        <Metric icon={<Radio />} label="MT5 gateway" value={health?.mt5?.status ?? 'DISCONNECTED'} detail={health?.mt5?.adapter ?? 'LOCAL_MT5'} />
        <Metric icon={<Activity />} label="Operating mode" value={(summary?.mode ?? 'ANALYSIS_ONLY').replaceAll('_', ' ')} detail="System-wide" />
        <Metric icon={<TrendingUp />} label="Market intelligence" value={miStatus} detail={`${escalations} escalations`} />
      </div>
      <div className="two-col">
        <Card>
          <div className="card-title">
            <div>
              <h2>Autonomous engines</h2>
              <p>Backend processing status (browser is observability only).</p>
            </div>
          </div>
          <div className="readiness">
            <Row icon={<TrendingUp />} title="Strength intelligence" text="API layer active; worker supplies snapshots." />
            <Row icon={<Workflow />} title="Workflow orchestrator" text="Awaiting orchestration API integration." />
            <Row icon={<ShieldCheck />} title="Risk & execution" text="Analysis-only — no live order path." />
          </div>
        </Card>
        <Card>
          <div className="card-title">
            <div>
              <h2>Trading posture</h2>
              <p>Foundation-safe defaults.</p>
            </div>
          </div>
          <div className="health-row">
            <span>Open positions</span>
            <b>0</b>
          </div>
          <div className="health-row">
            <span>Active opportunities</span>
            <b>0</b>
          </div>
          <div className="health-row">
            <span>Portfolio risk utilization</span>
            <b>—</b>
          </div>
          <div className="health-row">
            <span>Reference universe</span>
            <b>{instrumentCount} instruments</b>
          </div>
          <div className="health-row">
            <span>Signed in as</span>
            <b>{user?.display_name ?? user?.username ?? '—'}</b>
          </div>
        </Card>
      </div>
      <Card>
        <div className="card-title">
          <div>
            <h2>Recent system activity</h2>
            <p>Use System Control → Audit Trail for full administrative history.</p>
          </div>
        </div>
        <p className="muted">Audit events are tenant-scoped and available under System Control. Autonomous decision logs will append here when workflow engines are connected.</p>
      </Card>
    </>
  );
}

function Metric({ icon, label, value, detail }: { icon: React.ReactNode; label: string; value: string; detail: string }) {
  return (
    <Card className="metric">
      <div className="metric-icon">{icon}</div>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{detail}</small>
      </div>
    </Card>
  );
}

function Row({ icon, title, text }: { icon: React.ReactNode; title: string; text: string }) {
  return (
    <div className="ready">
      {icon}
      <div>
        <b>{title}</b>
        <p>{text}</p>
      </div>
    </div>
  );
}

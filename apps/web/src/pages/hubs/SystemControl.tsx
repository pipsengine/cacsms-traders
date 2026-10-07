import { useState } from 'react';
import { Activity, Bell, Cable, FileText, Play, Settings, SlidersHorizontal } from 'lucide-react';
import { Card } from '../../components/Ui';
import { TabPanel } from '../../components/PageTabs';
import { SubTabs } from '../../components/SubTabs';
import { System } from '../System';
import { Audit } from '../Audit';
import { EnginePlaceholder } from '../../components/EnginePlaceholder';
import type { Health, Summary } from '../../types';
import { writeHashRoute } from '../../lib/routes';
import { Status } from '../../components/Ui';
import { SystemControlHubHeader } from './SystemControlHubHeader';
import { SystemControlMT5Panel } from './SystemControlMT5Panel';
import { SystemControlProviderOverview } from './SystemControlProviderOverview';
import { SystemControlCTraderPanel } from './SystemControlCTraderPanel';
import { NotificationsPanel } from '../../features/notifications/NotificationsPanel';

const TABS = [
  { id: 'health', label: 'System Health', icon: Activity },
  { id: 'mt5', label: 'Market & Trading Connections', icon: Cable },
  { id: 'mode', label: 'Operating Mode', icon: Play },
  { id: 'engines', label: 'Engine Control', icon: Settings },
  { id: 'config', label: 'Configuration', icon: SlidersHorizontal },
  { id: 'notifications', label: 'Notifications', icon: Bell },
  { id: 'audit', label: 'Audit Trail', icon: FileText },
] as const;

const HEALTH_ROWS = [
  { id: 'api', label: 'API', key: 'api' as const },
  { id: 'sqlite', label: 'SQLite', key: 'database' as const },
  { id: 'market', label: 'Market Data', custom: 'MARKET' },
  { id: 'mt5', label: 'MT5', custom: 'MT5' },
  { id: 'workers', label: 'Workers', custom: 'WORKERS' },
  { id: 'ai', label: 'AI Engine', custom: 'AI' },
  { id: 'risk', label: 'Risk Engine', custom: 'RISK' },
  { id: 'execution', label: 'Execution Engine', custom: 'EXEC' },
  { id: 'heartbeats', label: 'Heartbeats', custom: 'HB' },
];

const CONFIG_TABS = [
  { id: 'system', label: 'System Configuration' },
  { id: 'tenant', label: 'Tenant Configuration' },
  { id: 'account', label: 'Trading Account Configuration' },
  { id: 'engine', label: 'Engine Configuration' },
];

const AUDIT_TABS = [
  { id: 'all', label: 'All Events' },
  { id: 'user', label: 'User Actions' },
  { id: 'system', label: 'System Actions' },
  { id: 'security', label: 'Authentication / Security' },
  { id: 'ai', label: 'AI Decisions' },
  { id: 'config', label: 'Configuration Changes' },
  { id: 'risk', label: 'Risk Decisions' },
  { id: 'execution', label: 'Execution Decisions' },
];

export function SystemControl({
  initialTab = 'health',
  tenantId,
  health,
  summary,
  onChanged,
  isPlatformAdmin,
  autonomousStatus,
}: {
  initialTab?: string;
  tenantId: string;
  health: Health | null;
  summary: Summary | null;
  onChanged: () => void;
  isPlatformAdmin: boolean;
  autonomousStatus: string;
}) {
  const [tab, setTab] = useState(TABS.some((t) => t.id === initialTab) ? initialTab : 'health');
  const [configSub, setConfigSub] = useState('system');
  const [auditSub, setAuditSub] = useState('all');
  const [mt5Sub, setMt5Sub] = useState(() => new URLSearchParams(window.location.search).has('ctrader') ? 'ctrader' : 'overview');

  const pickTab = (id: string) => {
    setTab(id);
    writeHashRoute('system-control', id);
  };

  function healthValue(row: (typeof HEALTH_ROWS)[0]) {
    if (row.key === 'api') return health?.api ?? 'OFFLINE';
    if (row.key === 'database') return health?.database ?? 'OFFLINE';
    if (row.custom === 'MT5') return health?.mt5?.status ?? 'DISCONNECTED';
    if (row.custom === 'MARKET') return health?.market_data?.market_data_ready ? 'AVAILABLE' : 'MARKET DATA UNAVAILABLE';
    return 'PAUSED';
  }

  return (
    <div className="sc-hub">
      <SystemControlHubHeader health={health} summary={summary} enginesLabel={autonomousStatus} />

      <div className="sc-tabsFigma" role="tablist">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            type="button"
            key={id}
            role="tab"
            aria-selected={tab === id}
            className={tab === id ? 'selected' : ''}
            onClick={() => pickTab(id)}
          >
            <Icon />
            {label}
          </button>
        ))}
      </div>

      <TabPanel active={tab} id="health">
        <div style={{ marginTop: 16 }}>
        <Card>
          <div className="card-title">
            <div>
              <h2>System health matrix</h2>
              <p>Live foundation signals plus reserved engine slots.</p>
            </div>
          </div>
          {HEALTH_ROWS.map((row) => (
            <div className="health-row" key={row.id}>
              <span>{row.label}</span>
              <Status value={healthValue(row)} />
            </div>
          ))}
          <div className="health-row">
            <span>Operating mode</span>
            <Status value={summary?.mode ?? 'ANALYSIS_ONLY'} />
          </div>
        </Card>
        </div>
      </TabPanel>

      <TabPanel active={tab} id="mt5">
        <div className="sc-subtabs">
          <button type="button" className={mt5Sub === 'overview' ? 'sc-btnPrimary sc-btnSmall' : 'sc-btnSecondary sc-btnSmall'} onClick={() => setMt5Sub('overview')}>Overview</button>
          <button
            type="button"
            className={mt5Sub === 'local' ? 'sc-btnPrimary sc-btnSmall' : 'sc-btnSecondary sc-btnSmall'}
            onClick={() => setMt5Sub('local')}
          >
            MT5
          </button>
          <button
            type="button"
            className={mt5Sub === 'ctrader' ? 'sc-btnPrimary sc-btnSmall' : 'sc-btnSecondary sc-btnSmall'}
            onClick={() => setMt5Sub('ctrader')}
          >
            cTrader Direct
          </button>
          <button
            type="button"
            className={mt5Sub === 'remote' ? 'sc-btnPrimary sc-btnSmall' : 'sc-btnSecondary sc-btnSmall'}
            onClick={() => setMt5Sub('remote')}
          >
            Remote Connections (Future)
          </button>
        </div>
        <TabPanel active={mt5Sub} id="overview">
          <SystemControlProviderOverview tenantId={tenantId} isPlatformAdmin={isPlatformAdmin} onChanged={onChanged} />
        </TabPanel>
        <TabPanel active={mt5Sub} id="local">
          <SystemControlMT5Panel tenantId={tenantId} onRefreshGlobal={onChanged} />
        </TabPanel>
        <TabPanel active={mt5Sub} id="ctrader">
          <SystemControlCTraderPanel tenantId={tenantId} onRefreshGlobal={onChanged} />
        </TabPanel>
        <TabPanel active={mt5Sub} id="remote">
          <EnginePlaceholder
            title="Remote MT5 connections"
            body="Remote terminal gateways will register here with the same contract as local MT5."
            engine="REMOTE_MT5"
          />
        </TabPanel>
      </TabPanel>

      <TabPanel active={tab} id="mode">
        <div style={{ marginTop: 16 }}>
          <System mode={summary?.mode ?? 'ANALYSIS_ONLY'} onChanged={onChanged} isPlatformAdmin={isPlatformAdmin} embedded />
        </div>
      </TabPanel>

      <TabPanel active={tab} id="engines">
        <div style={{ marginTop: 16 }}>
          <EnginePlaceholder
            title="Engine control"
            body="Start/stop/pause autonomous workers and set safe operational bounds. Controls will invoke server APIs only."
            engine="engine_control"
          />
        </div>
      </TabPanel>

      <TabPanel active={tab} id="config">
        <SubTabs tabs={CONFIG_TABS} active={configSub} onChange={setConfigSub} />
        {CONFIG_TABS.map((c) => (
          <TabPanel key={c.id} active={configSub} id={c.id}>
            <EnginePlaceholder
              title={c.label}
              body="Configuration is persisted in SQLite and applied by backend services. Editing UI will map to tenant_settings and system_settings APIs."
              engine={c.id}
            />
          </TabPanel>
        ))}
      </TabPanel>

      <TabPanel active={tab} id="notifications">
        <NotificationsPanel tenantId={tenantId} />
      </TabPanel>

      <TabPanel active={tab} id="audit">
        <SubTabs tabs={AUDIT_TABS} active={auditSub} onChange={setAuditSub} />
        <Audit tenantId={tenantId} embedded category={auditSub} />
      </TabPanel>
    </div>
  );
}

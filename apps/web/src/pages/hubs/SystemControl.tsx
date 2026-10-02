import { useState } from 'react';
import { PageHeader, Card } from '../../components/Ui';
import { PageTabs, TabPanel } from '../../components/PageTabs';
import { Connections } from '../Connections';
import { System } from '../System';
import { Audit } from '../Audit';
import { EnginePlaceholder } from '../../components/EnginePlaceholder';
import type { Health, Summary } from '../../types';
import { writeHashRoute } from '../../lib/routes';
import { Status } from '../../components/Ui';

const TABS = [
  { id: 'health', label: 'System Health' },
  { id: 'mt5', label: 'MT5 Connections' },
  { id: 'mode', label: 'Operating Mode' },
  { id: 'config', label: 'Configuration' },
  { id: 'audit', label: 'Audit Trail' },
];

export function SystemControl({
  initialTab = 'health',
  tenantId,
  health,
  summary,
  onChanged,
  isPlatformAdmin,
}: {
  initialTab?: string;
  tenantId: string;
  health: Health | null;
  summary: Summary | null;
  onChanged: () => void;
  isPlatformAdmin: boolean;
}) {
  const [tab, setTab] = useState(TABS.some((t) => t.id === initialTab) ? initialTab : 'health');
  const pickTab = (id: string) => {
    setTab(id);
    writeHashRoute('system-control', id);
  };

  return (
    <>
      <PageHeader title="System Control" subtitle="Runtime health, MT5 gateway, operating mode, configuration and audit." />
      <PageTabs tabs={TABS} active={tab} onChange={pickTab} />

      <TabPanel active={tab} id="health">
        <Card>
          <div className="card-title">
            <div>
              <h2>Platform health</h2>
              <p>API, database and adapter status from live endpoints.</p>
            </div>
          </div>
          <div className="health-row">
            <span>API</span>
            <Status value={health?.api ?? 'OFFLINE'} />
          </div>
          <div className="health-row">
            <span>SQLite</span>
            <Status value={health?.database ?? 'OFFLINE'} />
          </div>
          <div className="health-row">
            <span>MT5 adapter</span>
            <Status value={health?.mt5?.status ?? 'DISCONNECTED'} />
          </div>
          <div className="health-row">
            <span>Operating mode</span>
            <Status value={summary?.mode ?? 'ANALYSIS_ONLY'} />
          </div>
          <div className="health-row">
            <span>Connected accounts</span>
            <b>{summary?.connections ?? 0}</b>
          </div>
        </Card>
        <EnginePlaceholder
          title="Autonomous engine telemetry"
          body="Worker heartbeats and workflow engine health will surface here when orchestration APIs are connected."
          engine="worker_heartbeats"
        />
      </TabPanel>

      <TabPanel active={tab} id="mt5">
        <Connections tenantId={tenantId} />
      </TabPanel>

      <TabPanel active={tab} id="mode">
        <System mode={summary?.mode ?? 'ANALYSIS_ONLY'} onChanged={onChanged} isPlatformAdmin={isPlatformAdmin} />
      </TabPanel>

      <TabPanel active={tab} id="config">
        <EnginePlaceholder
          title="System configuration"
          body="Tenant settings, feature flags and integration endpoints will be managed here. Values remain server-authoritative."
          engine="system_settings / tenant_settings"
        />
      </TabPanel>

      <TabPanel active={tab} id="audit">
        <Audit tenantId={tenantId} />
      </TabPanel>
    </>
  );
}

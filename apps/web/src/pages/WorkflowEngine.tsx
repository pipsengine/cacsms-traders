import { useState } from 'react';
import { PageHeader, Card, Status } from '../components/Ui';
import { PageTabs, TabPanel } from '../components/PageTabs';
import { EnginePlaceholder } from '../components/EnginePlaceholder';
import { marketIntelligenceApi } from '../features/market-intelligence/api';
import { useAsync } from '../features/market-intelligence/hooks/useMarketIntelligence';

const MAIN_TABS = [
  { id: 'status', label: 'Engine Status' },
  { id: 'pipeline', label: 'Processing Pipeline' },
  { id: 'deps', label: 'Dependencies & Freshness' },
  { id: 'errors', label: 'Errors & Trace' },
];

const PIPELINE = [
  { id: 'market-data', label: 'Market Data Processing', engine: 'ingestion' },
  { id: 'strength', label: 'Strength Processing', engine: 'strength_engine' },
  { id: 'relationship', label: 'Relationship Analysis', engine: 'relationship_engine' },
  { id: 'scan', label: 'Market Scanning', engine: 'market_scanner' },
  { id: 'structure', label: 'Structure Analysis', engine: 'structure_intelligence' },
  { id: 'channel', label: 'Channel Analysis', engine: 'channel_intelligence' },
  { id: 'ai', label: 'AI Reasoning', engine: 'ai_reasoning' },
  { id: 'opportunity', label: 'Opportunity Processing', engine: 'opportunity_engine' },
  { id: 'confirm', label: 'Confirmation', engine: 'confirmation' },
  { id: 'risk', label: 'Risk Authorization', engine: 'risk_authorization' },
  { id: 'execution', label: 'Execution', engine: 'execution_gateway' },
  { id: 'positions', label: 'Position Management', engine: 'position_management' },
  { id: 'learning', label: 'Learning', engine: 'learning_analytics' },
];

export function WorkflowEngine() {
  const [tab, setTab] = useState('status');
  const mi = useAsync(() => marketIntelligenceApi.health(), []);

  const miLive = mi.data?.status === 'ready';

  return (
    <>
      <PageHeader
        title="Workflow Engine"
        subtitle="Backend autonomous pipeline observability — the browser never runs market or trading logic."
      />
      <PageTabs tabs={MAIN_TABS} active={tab} onChange={setTab} />

      <TabPanel active={tab} id="status">
        <div className="metric-grid">
          <Card className="mini">
            <span>Market intelligence API</span>
            <Status value={miLive ? 'READY' : 'PAUSED'} />
            <small>Strength & relationships layer</small>
          </Card>
          <Card className="mini">
            <span>Workflow orchestrator</span>
            <Status value="PAUSED" />
            <small>Awaiting integration</small>
          </Card>
          <Card className="mini">
            <span>Autonomous cycle</span>
            <Status value="ANALYSIS_ONLY" />
            <small>System operating mode</small>
          </Card>
        </div>
        <EnginePlaceholder
          title="Engine status registry"
          body="Unified worker status, last successful run and stage ownership will bind to workflow orchestration APIs."
          engine="workflow_orchestrator"
        />
      </TabPanel>

      <TabPanel active={tab} id="pipeline">
        <div className="pipeline-grid">
          {PIPELINE.map((s) => {
            const live = ['market-data', 'strength', 'relationship'].includes(s.id) && miLive;
            return (
              <Card key={s.id} className="pipeline-card">
                <span>{s.label}</span>
                <Status value={live ? 'READY' : 'PAUSED'} />
                <small>{live ? 'Layer reachable' : 'Awaiting engine integration'}</small>
              </Card>
            );
          })}
        </div>
      </TabPanel>

      <TabPanel active={tab} id="deps">
        <EnginePlaceholder
          title="Dependencies & heartbeats"
          body="Cross-stage dependencies, freshness thresholds and worker heartbeats will display from persisted runtime tables."
          engine="worker_heartbeats"
        />
      </TabPanel>

      <TabPanel active={tab} id="errors">
        <EnginePlaceholder
          title="Errors, retries & decision trace"
          body="Failed cycles, retry queues and correlation-scoped decision traces remain server-side. This view will replay them for operators."
          engine="system_events"
        />
      </TabPanel>
    </>
  );
}

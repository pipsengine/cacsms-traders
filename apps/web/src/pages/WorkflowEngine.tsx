import { PageHeader, Card, Status } from '../components/Ui';
import { EnginePlaceholder } from '../components/EnginePlaceholder';

const ENGINES = [
  { name: 'Market Intelligence Worker', status: 'READY', detail: 'Strength & relationship snapshots' },
  { name: 'Workflow Orchestrator', status: 'AWAITING', detail: 'Autonomous stage progression' },
  { name: 'Structure Intelligence', status: 'AWAITING', detail: 'Regime & swing hierarchy' },
  { name: 'Opportunity Engine', status: 'AWAITING', detail: 'Hypothesis lifecycle' },
];

export function WorkflowEngine() {
  return (
    <>
      <PageHeader
        title="Workflow Engine"
        subtitle="Observability for backend autonomous processing — states, runs, dependencies and errors."
      />
      <div className="metric-grid">
        {ENGINES.map((e) => (
          <Card key={e.name} className="mini">
            <span>{e.name}</span>
            <Status value={e.status === 'READY' ? 'READY' : 'PAUSED'} />
            <small>{e.detail}</small>
          </Card>
        ))}
      </div>
      <EnginePlaceholder
        title="Workflow run timeline"
        body="Latest runs, decision progression and dependency graphs will stream from backend workflow APIs. The browser never executes market or trading logic."
        engine="workflow_orchestrator"
      />
    </>
  );
}

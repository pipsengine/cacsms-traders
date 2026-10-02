import { PageHeader, Notice } from '../components/Ui';
import { EnginePlaceholder } from '../components/EnginePlaceholder';

export function ExecutionPositions() {
  return (
    <>
      <PageHeader title="Execution & Positions" subtitle="Campaigns, orders, fills and position state — observability only." />
      <Notice title="Analysis-only boundary" text="Real order submission and autonomous execution remain disabled. This page will reflect backend execution state when approved." tone="warning" />
      <EnginePlaceholder
        title="Execution ledger"
        body="Active and closed positions, fills and campaign status will appear when the execution layer is integrated."
        engine="execution_gateway"
      />
    </>
  );
}

import { PageHeader } from '../components/Ui';
import { EnginePlaceholder } from '../components/EnginePlaceholder';

export function TradingOpportunities() {
  return (
    <>
      <PageHeader
        title="Trading Opportunities"
        subtitle="Central lifecycle for hypotheses and opportunities — filtering, evidence and confirmation state."
      />
      <EnginePlaceholder
        title="Opportunity registry"
        body="Discovered opportunities will list here with drill-down panels for evidence, confirmation and entry quality. Backend OP logic remains separate from this observability UI."
        engine="opportunity_engine"
      />
    </>
  );
}

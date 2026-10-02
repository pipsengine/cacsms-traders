import { PageHeader } from '../components/Ui';
import { EnginePlaceholder } from '../components/EnginePlaceholder';

export function RiskPortfolio() {
  return (
    <>
      <PageHeader title="Risk & Portfolio" subtitle="Exposure, risk budgets, concentration and authorization decisions." />
      <EnginePlaceholder
        title="Portfolio risk cockpit"
        body="Account and campaign risk views will consume authorization APIs. Production risk algorithms are not enabled in this foundation build."
        engine="risk_authorization"
      />
    </>
  );
}

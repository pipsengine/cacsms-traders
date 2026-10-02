import { PageHeader } from '../components/Ui';
import { EnginePlaceholder } from '../components/EnginePlaceholder';

export function PerformanceLearning() {
  return (
    <>
      <PageHeader title="Performance & Learning" subtitle="Outcomes, strategy analysis and future AI-learning diagnostics." />
      <EnginePlaceholder
        title="Performance analytics"
        body="Statistics and learning evidence will bind to closed-loop APIs. No simulated P&amp;L or mock outcomes are shown."
        engine="learning_analytics"
      />
    </>
  );
}

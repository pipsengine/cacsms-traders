import { AdvancedChartWorkspace } from '../features/advanced-chart-analysis/AdvancedChartWorkspace';
import '../features/advanced-chart-analysis/advanced-chart-analysis.css';

export function AdvancedChartAnalysis() {
  const params = new URLSearchParams(window.location.search);
  const initialSymbol = params.get('symbol') || undefined;

  return (
    <div className="advanced-chart-page">
      <AdvancedChartWorkspace initialSymbol={initialSymbol} />
    </div>
  );
}

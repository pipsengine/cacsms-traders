import { ChartCandlestick } from 'lucide-react';
import { AdvancedChartWorkspace } from '../features/advanced-chart-analysis/AdvancedChartWorkspace';
import '../features/advanced-chart-analysis/advanced-chart-analysis.css';

export function AdvancedChartAnalysis() {
  const params = new URLSearchParams(window.location.search);
  const initialSymbol = params.get('symbol') || undefined;

  return (
    <div className="hub-page advanced-chart-page">
      <header className="hub-crumb">
        <p className="hub-crumb-trail">
          Market Vision <span aria-hidden>›</span> <span>Advanced Chart Analysis</span>
        </p>
        <h1>
          <ChartCandlestick size={22} aria-hidden /> Advanced Chart Analysis
        </h1>
        <p className="hub-crumb-sub aca-sub">Professional multi-symbol technical analysis with AI and structural intelligence.</p>
      </header>
      <AdvancedChartWorkspace initialSymbol={initialSymbol} />
    </div>
  );
}

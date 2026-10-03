import { useCallback, useState } from 'react';
import { PageHeader } from '../../components/Ui';
import { PageTabs, TabPanel } from '../../components/PageTabs';
import { marketIntelligenceApi } from '../../features/market-intelligence/api';
import { useAsync } from '../../features/market-intelligence/hooks/useMarketIntelligence';
import { MetricCard } from '../../features/market-intelligence/components/MetricCard';
import { StrengthMatrixTable } from '../../features/market-intelligence/components/StrengthMatrixTable';
import { AvgStrengthRanking } from '../../features/market-intelligence/components/AvgStrengthRanking';
import { MatrixStatusBar } from '../../features/market-intelligence/components/MatrixStatusBar';
import { RelationshipTable } from '../../features/market-intelligence/components/RelationshipTable';
import { RelationshipLegend } from '../../features/market-intelligence/components/RelationshipLegend';
import { LoadingSkeleton } from '../../features/market-intelligence/components/LoadingSkeleton';
import { ErrorState } from '../../features/market-intelligence/components/ErrorState';
import { EmptyState } from '../../features/market-intelligence/components/EmptyState';
import { StrengthHistoryPanel } from '../../features/market-intelligence/components/StrengthHistoryPanel';
import { RelationshipAnalysisPanel } from '../hub-panels/RelationshipAnalysisPanel';
import { writeHashRoute } from '../../lib/routes';
import type { CalculationMode } from '../../features/market-intelligence/types';

const TFS = ['ALL', 'YTD', 'Q', 'MN', 'W1', 'D1', 'H8', 'H1', 'M15', 'M5', 'M1'];
const CURRENCIES = ['EUR', 'GBP', 'USD', 'JPY', 'AUD', 'NZD', 'CAD', 'CHF'];
const CALC_MODES: { id: CalculationMode; label: string; disabled?: boolean }[] = [
  { id: 'CLOSE_CLOSE', label: 'Close-to-close' },
  { id: 'MA', label: 'MA difference', disabled: true },
  { id: 'RSI', label: 'RSI difference', disabled: true },
];
const TABS = [
  { id: 'matrix', label: 'Strength Matrix' },
  { id: 'historical', label: 'Historical Strength' },
  { id: 'relationships', label: 'Pair Relationships' },
  { id: 'analysis', label: 'Relationship Analysis' },
];

export function StrengthIntelligence({ initialTab = 'matrix' }: { initialTab?: string }) {
  const [tab, setTab] = useState(TABS.some((t) => t.id === initialTab) ? initialTab : 'matrix');
  const pickTab = (id: string) => {
    setTab(id);
    writeHashRoute('strength-intelligence', id);
  };
  const [tf, setTf] = useState('ALL');
  const [sortBy, setSortBy] = useState('AVG');
  const [calcMode, setCalcMode] = useState<CalculationMode>('CLOSE_CLOSE');
  const [histCurrency, setHistCurrency] = useState('EUR');
  const [histTf, setHistTf] = useState('H1');
  const [focusPair, setFocusPair] = useState('EURUSD');
  const [computing, setComputing] = useState(false);

  const matrixLoader = useCallback(
    () => marketIntelligenceApi.matrix(sortBy, calcMode),
    [sortBy, calcMode],
  );
  const matrix = useAsync(matrixLoader, [matrixLoader]);

  const rel = useAsync(() => marketIntelligenceApi.relationships(tf === 'ALL' ? undefined : tf), [tf]);
  const hist = useAsync(
    () => marketIntelligenceApi.strengthHistory(histCurrency, histTf),
    [histCurrency, histTf],
  );
  const pairHist = useAsync(() => marketIntelligenceApi.relationshipHistory(focusPair, histTf), [focusPair, histTf]);

  const high =
    rel.data?.filter((x) => x.inspection_priority === 'HIGH' || x.inspection_priority === 'CRITICAL').length ?? 0;
  const eq = rel.data?.filter((x) => x.state === 'EQUILIBRIUM').length ?? 0;

  const runCompute = async (fullCycle = false) => {
    setComputing(true);
    try {
      if (fullCycle) {
        await marketIntelligenceApi.runCycle(true);
      } else {
        await marketIntelligenceApi.computeMatrix(sortBy, calcMode);
      }
      matrix.refresh();
      rel.refresh();
    } catch (e) {
      matrix.refresh();
      throw e;
    } finally {
      setComputing(false);
    }
  };

  const hasMatrix = (matrix.data?.matrix?.length ?? 0) > 0;
  const missingHistory = matrix.data?.meta && !matrix.data.meta.historical_ok;

  return (
    <div className="mi-page mi-page-embedded">
      <PageHeader
        title="Strength Intelligence"
        subtitle="Relative currency strength, historical dynamics and pair relationships — analysis only, no trade signals."
      />
      <div className="mi-metrics">
        <MetricCard label="Currencies" value="8" detail="Major FX basket" />
        <MetricCard label="FX relationships" value="28" detail="Full cross matrix" />
        <MetricCard label="High inspection" value={high} detail="Structural follow-up" />
        <MetricCard label="Equilibrium" value={eq} detail="Retained by design" />
      </div>
      <div className="hub-toolbar">
        <PageTabs tabs={TABS} active={tab} onChange={pickTab} />
        {(tab === 'matrix' || tab === 'relationships') && (
          <select value={tf} onChange={(e) => setTf(e.target.value)} aria-label="Timeframe filter">
            {TFS.map((x) => (
              <option key={x}>{x}</option>
            ))}
          </select>
        )}
      </div>

      <TabPanel active={tab} id="matrix">
        <section className="mi-card">
          <header>
            <div>
              <span className="mi-eyebrow">Cross-sectional intelligence</span>
              <h2>Multi-timeframe currency strength</h2>
            </div>
            <span className="mi-note">Closed bars · EarnForex CSM · historical dynamics</span>
          </header>
          <div className="mi-matrix-controls">
            <label>
              Calculation
              <select
                value={calcMode}
                onChange={(e) => setCalcMode(e.target.value as CalculationMode)}
                aria-label="Calculation mode"
              >
                {CALC_MODES.map((m) => (
                  <option key={m.id} value={m.id} disabled={m.disabled}>
                    {m.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Sort by
              <select value={sortBy} onChange={(e) => setSortBy(e.target.value)} aria-label="Sort strength by">
                {['AVG', 'YTD', 'Q', 'MN', 'W1', 'D1', 'H8', 'H1', 'M15', 'M5', 'M1'].map((x) => (
                  <option key={x}>{x}</option>
                ))}
              </select>
            </label>
          </div>
          <MatrixStatusBar
            meta={matrix.data?.meta ?? null}
            loading={matrix.loading || computing}
            onRefresh={() => void runCompute(true).catch(() => undefined)}
          />
          {matrix.loading && !matrix.data ? (
            <LoadingSkeleton />
          ) : matrix.error ? (
            <ErrorState message={matrix.error} onRetry={matrix.refresh} />
          ) : hasMatrix && matrix.data ? (
            <>
              <StrengthMatrixTable
                matrix={matrix.data.matrix}
                meta={matrix.data.meta}
                sortBy={sortBy}
                onSortBy={setSortBy}
              />
              <AvgStrengthRanking rows={matrix.data.avg_ranking} />
            </>
          ) : missingHistory ? (
            <div className="mi-error mi-missing-history">
              <span>
                Historical data needed for one or more pairs/timeframes. Ingest closed candles from MT5, then
                recalculate.
              </span>
              <button type="button" onClick={() => void runCompute(true)}>
                Retry
              </button>
            </div>
          ) : (
            <EmptyState
              title="Waiting for strength snapshots"
              body="Connect market data, ingest closed candles for all 28 pairs, then run Recalculate. Missing data is never fabricated."
              action={
                <button type="button" className="mi-primary-btn" onClick={() => void runCompute(true)}>
                  Ingest & calculate
                </button>
              }
            />
          )}
        </section>
      </TabPanel>

      <TabPanel active={tab} id="historical">
        <div className="hub-inline-filters">
          <label>
            Currency
            <select value={histCurrency} onChange={(e) => setHistCurrency(e.target.value)}>
              {CURRENCIES.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </label>
          <label>
            Timeframe
            <select value={histTf} onChange={(e) => setHistTf(e.target.value)}>
              {TFS.filter((x) => x !== 'ALL').map((x) => (
                <option key={x}>{x}</option>
              ))}
            </select>
          </label>
        </div>
        {hist.loading ? (
          <LoadingSkeleton />
        ) : hist.error ? (
          <ErrorState message={hist.error} onRetry={hist.refresh} />
        ) : hist.data?.length ? (
          <StrengthHistoryPanel currency={histCurrency} rows={hist.data} />
        ) : (
          <EmptyState title="No historical strength" body="History appears after persisted strength snapshots exist." />
        )}
      </TabPanel>

      <TabPanel active={tab} id="relationships">
        <section className="mi-card">
          <header>
            <div>
              <span className="mi-eyebrow">Pairwise intelligence</span>
              <h2>Currency relationship map</h2>
            </div>
          </header>
          {rel.loading ? (
            <LoadingSkeleton />
          ) : rel.error ? (
            <ErrorState message={rel.error} onRetry={rel.refresh} />
          ) : rel.data?.length ? (
            <RelationshipTable rows={rel.data} />
          ) : (
            <EmptyState title="No relationship snapshots" body="Relationships appear after strength calculation." />
          )}
        </section>
        <RelationshipLegend />
      </TabPanel>

      <TabPanel active={tab} id="analysis">
        <div className="hub-inline-filters">
          <label>
            Focus pair
            <select value={focusPair} onChange={(e) => setFocusPair(e.target.value)}>
              {(rel.data?.map((r) => r.pair) ?? ['EURUSD', 'GBPUSD', 'USDJPY']).slice(0, 28).map((p) => (
                <option key={p}>{p}</option>
              ))}
            </select>
          </label>
        </div>
        <RelationshipAnalysisPanel
          pair={focusPair}
          rows={pairHist.data}
          loading={pairHist.loading}
          error={pairHist.error}
          onRetry={pairHist.refresh}
        />
      </TabPanel>
    </div>
  );
}

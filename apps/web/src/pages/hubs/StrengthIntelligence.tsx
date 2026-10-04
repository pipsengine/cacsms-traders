import { useCallback, useEffect, useState } from 'react';
import { Grid3x3 } from 'lucide-react';
import { PageTabs, TabPanel } from '../../components/PageTabs';
import { marketIntelligenceApi } from '../../features/market-intelligence/api';
import { usePollingAsync } from '../../features/market-intelligence/hooks/useMarketIntelligence';
import {
  CURRENCY_FILTER_OPTIONS,
  MATRIX_TFS,
  StrengthMatrixTable,
  type SortDir,
  type ValueMode,
} from '../../features/market-intelligence/components/StrengthMatrixTable';
import { AvgStrengthRanking } from '../../features/market-intelligence/components/AvgStrengthRanking';
import { MatrixStatusBar } from '../../features/market-intelligence/components/MatrixStatusBar';
import { StrengthPageHeader } from '../../features/market-intelligence/components/StrengthPageHeader';
import { CurrencyStrengthStrip } from '../../features/market-intelligence/components/CurrencyStrengthStrip';
import {
  MatrixBlockingState,
  MatrixStatusBanners,
} from '../../features/market-intelligence/components/MatrixPanelStates';
import { HistoricalStrengthTab } from '../../features/market-intelligence/components/HistoricalStrengthTab';
import { PairRelationshipsTab } from '../../features/market-intelligence/components/PairRelationshipsTab';
import { RelationshipAnalysisTab } from '../../features/market-intelligence/components/RelationshipAnalysisTab';
import { writeHashRoute } from '../../lib/routes';
import type { Health } from '../../types';
import type { CalculationMode } from '../../features/market-intelligence/types';

const SORT_TFS = ['AVG', ...MATRIX_TFS.filter((tf) => tf !== 'AVG')];
const POLL_MS = 1000;
const CALC_MODES: { id: CalculationMode; label: string }[] = [
  { id: 'CLOSE_CLOSE', label: 'Close-to-Close' },
  { id: 'MA', label: 'MA difference' },
  { id: 'RSI', label: 'RSI difference' },
  { id: 'RSI_MA', label: 'RSI MA' },
  { id: 'STOCH_MAIN', label: 'Stochastic main' },
  { id: 'STOCH_SIGNAL', label: 'Stochastic signal' },
];
const TABS = [
  { id: 'matrix', label: 'Strength Matrix' },
  { id: 'historical', label: 'Historical Strength' },
  { id: 'relationships', label: 'Pair Relationships' },
  { id: 'analysis', label: 'Relationship Analysis' },
];

export function StrengthIntelligence({
  initialTab = 'matrix',
}: {
  initialTab?: string;
  health?: Health | null;
}) {
  const [tab, setTab] = useState(TABS.some((t) => t.id === initialTab) ? initialTab : 'matrix');
  const pickTab = (id: string) => {
    setTab(id);
    writeHashRoute('strength-intelligence', id);
  };
  const [sortBy, setSortBy] = useState('AVG');
  const [currencyFilter, setCurrencyFilter] = useState('ALL');
  const [focusPair, setFocusPair] = useState('EURUSD');
  const [pageVisible, setPageVisible] = useState(
    () => typeof document !== 'undefined' && document.visibilityState === 'visible',
  );

  useEffect(() => {
    const onVis = () => setPageVisible(document.visibilityState === 'visible');
    document.addEventListener('visibilitychange', onVis);
    return () => document.removeEventListener('visibilitychange', onVis);
  }, []);

  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [valueMode, setValueMode] = useState<ValueMode>('score');
  const sortMatrix = (tf: string) => {
    setSortDir((d) => (tf === sortBy && d === 'desc' ? 'asc' : 'desc'));
    setSortBy(tf);
  };

  const [calcMode, setCalcMode] = useState<CalculationMode>('CLOSE_CLOSE');
  const matrixLoader = useCallback(() => marketIntelligenceApi.matrix('AVG', calcMode), [calcMode]);
  const matrix = usePollingAsync(matrixLoader, [matrixLoader], {
    enabled: pageVisible,
    intervalMs: POLL_MS,
  });

  const data = matrix.data;
  const meta = data?.meta ?? null;
  const modeReady = !!data && data.meta.calculation_mode === calcMode && !data.meta.mode_pending;
  const hasMatrix = modeReady && data.matrix.length > 0;
  const hasScores = !!data?.matrix.some((r) => r.scores.AVG !== undefined);

  return (
    <div className="si-page">
      <StrengthPageHeader meta={meta} apiError={!!matrix.error && !!data} />

      {data?.currency_summary.length ? (
        <CurrencyStrengthStrip cards={data.currency_summary} stale={!!meta?.stale} />
      ) : null}

      <div className="si-tabs-wrap">
        <PageTabs tabs={TABS} active={tab} onChange={pickTab} />
      </div>

      <TabPanel active={tab} id="matrix">
        <section className="mi-card si-matrix-card">
          <header className="mi-matrix-card-head">
            <div className="si-card-head">
              <span className="si-icon-block" aria-hidden>
                <Grid3x3 size={16} />
              </span>
              <div>
                <h2>Multi-timeframe currency strength matrix</h2>
                <p className="mi-matrix-sub">
                  Relative strength score (0–100) across multiple timeframes. Higher value = stronger currency.
                </p>
              </div>
            </div>
            <div className="mi-matrix-controls mi-matrix-controls--inline">
              <label>
                Calculation
                <select
                  value={calcMode}
                  onChange={(e) => setCalcMode(e.target.value as CalculationMode)}
                  aria-label="Calculation mode"
                >
                  {CALC_MODES.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Values
                <select
                  value={valueMode}
                  onChange={(e) => setValueMode(e.target.value as ValueMode)}
                  aria-label="Value display"
                >
                  <option value="score">Score (0–100)</option>
                  <option value="raw">% change (EarnForex)</option>
                </select>
              </label>
              <label>
                Sort by
                <select
                  value={sortBy}
                  onChange={(e) => {
                    setSortBy(e.target.value);
                    setSortDir('desc');
                  }}
                  aria-label="Sort strength by"
                >
                  {SORT_TFS.map((x) => (
                    <option key={x}>{x}</option>
                  ))}
                </select>
              </label>
              <label>
                Currency
                <select
                  value={currencyFilter}
                  onChange={(e) => setCurrencyFilter(e.target.value)}
                  aria-label="Currency"
                >
                  {CURRENCY_FILTER_OPTIONS.map((x) => (
                    <option key={x}>{x}</option>
                  ))}
                </select>
              </label>
            </div>
          </header>

          {hasMatrix && meta ? (
            <>
              <MatrixStatusBanners meta={meta} error={matrix.error} hasScores={hasScores} onRetry={matrix.refresh} />
              <div className={`mi-matrix-split ${meta.stale ? 'is-stale' : ''}`}>
                <StrengthMatrixTable
                  matrix={data.matrix}
                  sortBy={sortBy}
                  sortDir={sortDir}
                  onSortBy={sortMatrix}
                  valueMode={valueMode}
                  currencyFilter={currencyFilter}
                />
                <AvgStrengthRanking rows={data.avg_ranking} />
              </div>
              <MatrixStatusBar meta={meta} />
            </>
          ) : (
            <MatrixBlockingState loading={matrix.loading} error={matrix.error} onRetry={matrix.refresh} />
          )}
        </section>
      </TabPanel>

      <TabPanel active={tab} id="historical">
        <HistoricalStrengthTab enabled={pageVisible && tab === 'historical'} />
      </TabPanel>

      <TabPanel active={tab} id="relationships">
        <PairRelationshipsTab
          enabled={pageVisible && tab === 'relationships'}
          onAnalyse={(pair) => {
            setFocusPair(pair);
            pickTab('analysis');
          }}
        />
      </TabPanel>

      <TabPanel active={tab} id="analysis">
        <RelationshipAnalysisTab enabled={pageVisible && tab === 'analysis'} pair={focusPair} onPairChange={setFocusPair} />
      </TabPanel>
    </div>
  );
}

import { useCallback, useEffect, useState } from 'react';
import { Grid3x3 } from 'lucide-react';
import { PageTabs, TabPanel } from '../../components/PageTabs';
import { marketIntelligenceApi } from '../../features/market-intelligence/api';
import { useAsync, usePollingAsync } from '../../features/market-intelligence/hooks/useMarketIntelligence';
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
import { RelationshipTable } from '../../features/market-intelligence/components/RelationshipTable';
import { RelationshipLegend } from '../../features/market-intelligence/components/RelationshipLegend';
import { EmptyState } from '../../features/market-intelligence/components/EmptyState';
import { ErrorState } from '../../features/market-intelligence/components/ErrorState';
import { LoadingSkeleton } from '../../features/market-intelligence/components/LoadingSkeleton';
import { StrengthHistoryPanel } from '../../features/market-intelligence/components/StrengthHistoryPanel';
import { RelationshipAnalysisPanel } from '../hub-panels/RelationshipAnalysisPanel';
import { writeHashRoute } from '../../lib/routes';
import type { Health } from '../../types';
import type { CalculationMode } from '../../features/market-intelligence/types';

const CURRENCIES = ['EUR', 'GBP', 'USD', 'JPY', 'AUD', 'NZD', 'CAD', 'CHF'];
const REL_TFS = ['ALL', 'YTD', 'Q', 'MN', 'W', 'D1', 'H8', 'H1', 'M15', 'M5', 'M1'];
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
  const [relTf, setRelTf] = useState('ALL');
  const [sortBy, setSortBy] = useState('AVG');
  const [currencyFilter, setCurrencyFilter] = useState('ALL');
  const [histCurrency, setHistCurrency] = useState('EUR');
  const [histTf, setHistTf] = useState('H1');
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

  const rel = useAsync(
    () => marketIntelligenceApi.relationships(relTf === 'ALL' ? undefined : relTf),
    [relTf],
    { enabled: tab === 'relationships' || tab === 'analysis' },
  );
  const hist = useAsync(
    () => marketIntelligenceApi.strengthHistory(histCurrency, histTf),
    [histCurrency, histTf],
    { enabled: tab === 'historical' },
  );
  const pairHist = useAsync(
    () => marketIntelligenceApi.relationshipHistory(focusPair, histTf),
    [focusPair, histTf],
    { enabled: tab === 'analysis' },
  );

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
              {SORT_TFS.map((x) => (
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
        <div className="hub-toolbar" style={{ marginTop: 0 }}>
          <select value={relTf} onChange={(e) => setRelTf(e.target.value)} aria-label="Timeframe filter">
            {REL_TFS.map((x) => (
              <option key={x}>{x}</option>
            ))}
          </select>
        </div>
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

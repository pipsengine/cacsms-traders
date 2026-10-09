import { useCallback, useEffect, useMemo, useState } from 'react';
import { outlookApi, outlookCache } from '../features/ai-outlook/api';
import { ChartAnalysis } from '../features/ai-outlook/components/ChartAnalysis';
import { DailyOutlook } from '../features/ai-outlook/components/DailyOutlook';
import { HistoricalOutlook } from '../features/ai-outlook/components/HistoricalOutlook';
import { KeyLevels } from '../features/ai-outlook/components/KeyLevels';
import { ScenarioAnalysis } from '../features/ai-outlook/components/ScenarioAnalysis';
import type { CandleState } from '../features/ai-outlook/components/OutlookChart';
import { HISTORY_LIMIT, MINI_TFS, NoOpportunity, SessionCards, StatusCluster, SymbolPicker, TfBar, dayLabel, runState, type OutlookTf } from '../features/ai-outlook/components/shared';
import { usePollingAsync } from '../features/market-intelligence/hooks/useMarketIntelligence';
import { Blocking } from '../features/market-structure/components/StructureUi';
import { useCandles, useShortScreen, useVisible } from '../features/market-structure/hooks';
import { liveState, useLive, useLiveCandles } from '../features/market-structure/live';

const TABS = [
  { id: 'daily', label: 'Daily Outlook' },
  { id: 'scenarios', label: 'Scenario Analysis' },
  { id: 'levels', label: 'Key Levels' },
  { id: 'chart', label: 'AI Chart Analysis' },
  { id: 'history', label: 'Historical Outlook' },
] as const;
type TabId = (typeof TABS)[number]['id'];

const CAPTIONS: Record<TabId, Partial<Record<string, string>>> = {
  daily: {},
  scenarios: {},
  levels: { ASIAN: 'Key Levels Focus', LONDON: 'Breakout Watch', NEW_YORK: 'Continuation' },
  chart: {},
  history: { ASIAN: 'Review Outlook', LONDON: 'Track Progress', NEW_YORK: 'Compare Results' },
};

export function AiMarketOutlook({ initialTab, onTab }: { initialTab?: string; onTab?: (tab: string) => void }) {
  const visible = useVisible();
  const short = useShortScreen();
  const [tab, setTabState] = useState<TabId>(() => (TABS.some((t) => t.id === initialTab) ? (initialTab as TabId) : 'daily'));
  const [symbol, setSymbol] = useState<string | null>(null);
  const [tf, setTf] = useState<OutlookTf>('D1');
  const [days, setDays] = useState(30);
  const [tick, setTick] = useState(0);
  const [runBusy, setRunBusy] = useState(false);

  useEffect(() => {
    if (initialTab && TABS.some((t) => t.id === initialTab)) setTabState(initialTab as TabId);
  }, [initialTab]);
  const setTab = (t: TabId) => {
    setTabState(t);
    onTab?.(t);
    if (t === 'chart' && tf === 'D1') setTf('H8');
    if (t !== 'chart' && (tf === 'H8' || tf === 'H1' || tf === 'M30') && t !== 'daily') setTf('D1');
  };

  const [fresh, setFresh] = useState(0);
  useEffect(() => {
    if (!visible) return;
    let stopped = false;
    const catchUp = () =>
      outlookApi
        .catchUp()
        .then((r) => {
          if (!stopped && r.ran) setFresh((n) => n + 1);
        })
        .catch(() => undefined);
    void catchUp();
    const id = window.setInterval(catchUp, 60000);
    return () => {
      stopped = true;
      window.clearInterval(id);
    };
  }, [visible]);

  const [cachedLatest] = useState(() => outlookCache.read('latest'));
  const [cachedDetail] = useState(() => outlookCache.read('detail'));
  const latestLoader = useCallback(() => outlookApi.latest(), [tick, fresh]);
  const latest = usePollingAsync(latestLoader, [latestLoader], { enabled: visible, intervalMs: 30000 });
  const latestData = latest.data ?? cachedLatest;
  useEffect(() => outlookCache.write('latest', latest.data), [latest.data]);
  const rows = useMemo(() => latestData?.rows ?? [], [latestData]);
  const opportunities = latestData?.opportunities ?? [];
  const isHistory = tab === 'history';

  useEffect(() => {
    if (symbol && rows.some((r) => r.symbol === symbol && (r.qualified || isHistory || r.status === 'PUBLISHED'))) return;
    const first = opportunities[0]?.symbol ?? (isHistory ? 'XAUUSD' : null);
    if (first !== symbol) setSymbol(first);
  }, [rows, opportunities, symbol, isHistory]);

  const active = symbol;
  const detailLoader = useCallback(() => (active ? outlookApi.symbol(active) : Promise.resolve(null)), [active, tick, fresh]);
  const hasRun = !!latestData?.run;
  const detail = usePollingAsync(detailLoader, [detailLoader], { enabled: visible && hasRun && !!active && !isHistory, intervalMs: 30000 });
  useEffect(() => outlookCache.write('detail', detail.data), [detail.data]);
  const detailData = detail.data ?? cachedDetail;
  const o = detailData && detailData.outlook.symbol === active ? detailData.outlook : null;

  const mtfLoader = useCallback(() => (active ? outlookApi.mtf(active, null, 42) : Promise.resolve(null)), [active, tick]);
  const mtf = usePollingAsync(mtfLoader, [mtfLoader], { enabled: visible && hasRun && !!active && tab === 'chart', intervalMs: 120000 });

  const historyLoader = useCallback(() => (active ? outlookApi.history(active, days) : Promise.resolve(null)), [active, days, tick]);
  const history = usePollingAsync(historyLoader, [historyLoader], { enabled: visible && !!active && isHistory, intervalMs: 120000 });

  const chartTf: OutlookTf = isHistory ? 'D1' : tf;
  const limit = isHistory ? 400 : HISTORY_LIMIT[tf];
  const c = useCandles(active ?? 'XAUUSD', chartTf, visible && !!active, tick, limit);
  const liveTfs = useMemo(() => (tab === 'chart' ? [chartTf, ...MINI_TFS] : [chartTf]), [tab, chartTf]);
  const live = useLive(active, liveTfs, visible && !!active);
  const liveBars = useLiveCandles(`${active}|${chartTf}`, c.candles, live.data?.forming?.[chartTf]);
  const candles: CandleState = {
    candles: liveBars,
    loading: c.loading,
    error: c.error ?? null,
    price: live.data?.quote?.price ?? null,
    live: active ? liveState(live.data, live.error) : undefined,
    forming: liveBars.length > 0 && liveBars.at(-1) !== c.candles.at(-1),
  };
  const chartHeight = short ? 300 : 372;

  const run = latestData?.run ?? null;
  const schedule = latestData?.schedule ?? null;
  const st = runState(latestData?.current?.state);

  const body = () => {
    if (!latestData) return latest.error ? <Blocking title="AI Market Outlook unavailable" error={latest.error} /> : <Blocking loading="Loading the latest published outlook…" />;
    if (!run) {
      const cur = latestData.current;
      return (
        <Blocking
          title={cur ? `Daily cycle ${st.label.toLowerCase()} for ${dayLabel(cur.analysis_date)}` : 'No published outlook yet'}
          reason={cur?.error ?? cur?.log.at(-1)?.message ?? 'The first outlook is generated automatically after the next D1 close.'}
        />
      );
    }
    if (isHistory) {
      if (!active) return <Blocking loading="Selecting instrument…" />;
      return (
        <HistoricalOutlook
          symbol={active}
          digits={rows.find((r) => r.symbol === active)?.digits ?? 5}
          data={history.data && history.data.symbol === active && history.data.days === days ? history.data : null}
          loading={history.loading}
          error={history.error}
          days={days}
          onDays={setDays}
          candles={candles}
          chartHeight={chartHeight}
        />
      );
    }
    if (!active) return <NoOpportunity rows={rows} run={run} />;
    if (!o) return detail.error ? <Blocking title={`${active} outlook unavailable`} error={detail.error} /> : <Blocking loading={`Loading ${active} outlook…`} />;
    if (o.status !== 'PUBLISHED') return <Blocking title={`${active} — ${o.status === 'FAILED' ? 'analysis failed' : 'insufficient data'}`} reason={o.reason ?? 'No outlook for this instrument today'} />;
    const props = { o, tf, onTf: setTf, candles, chartHeight };
    if (tab === 'scenarios') return <ScenarioAnalysis {...props} />;
    if (tab === 'levels') return <KeyLevels {...props} />;
    if (tab === 'chart') return <ChartAnalysis {...props} mtf={mtf.data && mtf.data.symbol === active ? mtf.data : null} forming={live.data?.forming} />;
    return <DailyOutlook {...props} />;
  };

  const sessions = o?.session_plan ?? null;
  return (
    <div className="mst-page mao-page">
      <header className="mao-head">
        <div>
          <nav className="mst-crumb" aria-label="Breadcrumb">
            Market Vision <span aria-hidden>›</span> <span>AI Market Outlook</span>
          </nav>
          <h1>AI Market Outlook (Daily)</h1>
          <p>End-of-day AI analysis, multi-timeframe context and next move projection for the upcoming sessions.</p>
        </div>
        <div className="mao-head-right">
          <StatusCluster
            run={run}
            current={latestData?.current ?? null}
            schedule={schedule}
            onReload={() => setTick((t) => t + 1)}
            busy={latest.refreshing || detail.refreshing}
            runBusy={runBusy}
            onRunNow={() => {
              setRunBusy(true);
              outlookApi
                .runNow()
                .then(() => setTick((t) => t + 1))
                .finally(() => setRunBusy(false));
            }}
          />
          {tab !== 'daily' ? <SessionCards plans={sessions} schedule={schedule} captions={CAPTIONS[tab]} /> : null}
        </div>
      </header>

      <div className="mao-tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t.id} role="tab" aria-selected={tab === t.id} className={tab === t.id ? 'is-on' : ''} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
        {latestData?.stale ? <span className="mao-stale">Showing the last published outlook — today’s cycle is {st.label.toLowerCase()}.</span> : null}
      </div>

      <div className="mao-toolbar">
        <SymbolPicker symbol={active} rows={rows} onSelect={setSymbol} allowAll={isHistory} />
        <TfBar value={chartTf} onChange={(t) => !isHistory && setTf(t)} />
        {tab === 'daily' ? (
          <>
            <div className="mao-date">
              <small>Analysis Date</small>
              <b>{run ? `${dayLabel(run.analysis_date)} (Daily Close)` : '—'}</b>
            </div>
            <SessionCards plans={sessions} schedule={schedule} />
          </>
        ) : null}
      </div>

      {body()}
    </div>
  );
}

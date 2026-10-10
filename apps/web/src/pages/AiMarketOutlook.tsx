import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { outlookApi, outlookCache } from '../features/ai-outlook/api';
import { ChartAnalysis } from '../features/ai-outlook/components/ChartAnalysis';
import { DailyOutlook } from '../features/ai-outlook/components/DailyOutlook';
import { HistoricalOutlook } from '../features/ai-outlook/components/HistoricalOutlook';
import { KeyLevels } from '../features/ai-outlook/components/KeyLevels';
import { ScenarioAnalysis } from '../features/ai-outlook/components/ScenarioAnalysis';
import type { CandleState } from '../features/ai-outlook/components/OutlookChart';
import { GOLD_TFS, HISTORY_LIMIT, MINI_TFS, NoOpportunity, SessionCards, StatusCluster, SymbolPicker, TfBar, dayLabel, qualifiedByConfidence, runState, type OutlookTf } from '../features/ai-outlook/components/shared';
import { usePollingAsync } from '../features/market-intelligence/hooks/useMarketIntelligence';
import { Blocking } from '../features/market-structure/components/StructureUi';
import { useCandles, useShortScreen, useVisible } from '../features/market-structure/hooks';
import { liveState, useLive, useLiveCandles } from '../features/market-structure/live';

const HORIZONS = [
  { id: 'daily', api: 'DAILY', label: 'Daily Outlook', tf: 'D1' as OutlookTf, title: 'Daily Analysis (D1 Close)', close: 'Daily Close', blurb: 'Next trading day and Asian, London and New York session outlook for every instrument.' },
  { id: 'weekly', api: 'WEEKLY', label: 'Weekly Outlook', tf: 'W' as OutlookTf, title: 'Weekly Analysis (W1 Close)', close: 'Weekly Close', blurb: 'Upcoming week direction, confirmed weekly fractals and SCH beneath the weekly chart.' },
  { id: 'monthly', api: 'MONTHLY', label: 'Monthly Outlook', tf: 'MN' as OutlookTf, title: 'Monthly Analysis (MN Close)', close: 'Monthly Close', blurb: 'Strategic outlook for the next trading month. It does not cancel a valid shorter-term opportunity.' },
  { id: 'gold', api: 'H8', label: 'Gold H8 Session Outlook', tf: 'H8' as OutlookTf, title: 'Gold H8 Session (XAUUSD)', close: 'H8 Close', blurb: 'XAUUSD operational direction after each closed H8 candle, with H1 validation and M15 confirmation.' },
] as const;
type HorizonId = (typeof HORIZONS)[number]['id'];
const SECTIONS = [
  { id: 'overview', label: 'Outlook' },
  { id: 'scenarios', label: 'Scenario Analysis' },
  { id: 'levels', label: 'Key Levels' },
  { id: 'chart', label: 'AI Chart Analysis' },
  { id: 'history', label: 'Historical Outlook' },
] as const;
type SectionId = (typeof SECTIONS)[number]['id'];

const CAPTIONS: Partial<Record<SectionId, Partial<Record<string, string>>>> = {
  levels: { ASIAN: 'Key Levels Focus', LONDON: 'Breakout Watch', NEW_YORK: 'Continuation' },
  history: { ASIAN: 'Review Outlook', LONDON: 'Track Progress', NEW_YORK: 'Compare Results' },
};

/** A payload belongs to the tab being viewed. Older daily responses omit the field. */
function forHorizon(payloadHorizon: string | undefined, apiHorizon: string) {
  return (payloadHorizon || 'DAILY') === apiHorizon;
}

function parseTab(tab?: string): { horizon: HorizonId; section: SectionId } {
  if (tab === 'weekly' || tab === 'monthly' || tab === 'gold') return { horizon: tab, section: 'overview' };
  if (tab === 'scenarios' || tab === 'levels' || tab === 'chart' || tab === 'history') return { horizon: 'daily', section: tab };
  return { horizon: 'daily', section: 'overview' };
}

export function AiMarketOutlook({ initialTab, onTab }: { initialTab?: string; onTab?: (tab: string) => void }) {
  const visible = useVisible();
  const short = useShortScreen();
  const start = parseTab(initialTab);
  const [horizon, setHorizon] = useState<HorizonId>(start.horizon);
  const [section, setSection] = useState<SectionId>(start.section);
  const [symbol, setSymbol] = useState<string | null>(null);
  const [tf, setTf] = useState<OutlookTf>(HORIZONS.find((h) => h.id === start.horizon)?.tf ?? 'D1');
  const [days, setDays] = useState(30);
  const [tick, setTick] = useState(0);
  const [runBusy, setRunBusy] = useState(false);
  const spec = HORIZONS.find((h) => h.id === horizon) ?? HORIZONS[0];
  const apiHorizon = spec.api;

  useEffect(() => {
    const next = parseTab(initialTab);
    setHorizon(next.horizon);
    setSection(next.section);
  }, [initialTab]);

  const chooseHorizon = (id: HorizonId) => {
    const next = HORIZONS.find((h) => h.id === id) ?? HORIZONS[0];
    setHorizon(id);
    setSection('overview');
    setTf(next.tf);
    setSymbol(id === 'gold' ? 'XAUUSD' : null);
    setTick((t) => t + 1);
    onTab?.(id);
  };
  const chooseSection = (id: SectionId) => {
    setSection(id);
    onTab?.(horizon === 'daily' && id !== 'overview' ? id : horizon);
    if (id === 'chart' && tf === 'D1') setTf('H8');
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
  const [packs, setPacks] = useState<Record<string, NonNullable<typeof cachedLatest>>>(() => (cachedLatest ? { [cachedLatest.horizon || 'DAILY']: cachedLatest } : {}));
  const latestLoader = useCallback(() => outlookApi.latest(null, apiHorizon), [tick, fresh, apiHorizon]);
  const latest = usePollingAsync(latestLoader, [latestLoader], { enabled: visible, intervalMs: 30000 });
  useEffect(() => {
    if (!latest.data) return;
    const key = latest.data.horizon || 'DAILY';
    setPacks((prev) => (prev[key] === latest.data ? prev : { ...prev, [key]: latest.data! }));
  }, [latest.data]);
  const latestData = packs[apiHorizon] ?? null;
  useEffect(() => {
    if (apiHorizon === 'DAILY' && latest.data && forHorizon(latest.data.horizon, 'DAILY')) outlookCache.write('latest', latest.data);
  }, [latest.data, apiHorizon]);
  const rows = useMemo(() => latestData?.rows ?? [], [latestData]);
  const isHistory = section === 'history';
  const isGold = horizon === 'gold';
  const seenRun = useRef<string | null>(null);

  useEffect(() => {
    if (!latestData?.run) return;
    const token = `${apiHorizon}:${latestData.run.id}`;
    if (seenRun.current === token) return;
    seenRun.current = token;
    if (isGold) {
      setSymbol('XAUUSD');
      return;
    }
    const top = qualifiedByConfidence(rows)[0]?.symbol ?? (isHistory ? rows.find((r) => r.status === 'PUBLISHED')?.symbol ?? null : null);
    setSymbol(top);
  }, [apiHorizon, latestData, rows, isGold, isHistory]);

  const active = isGold ? 'XAUUSD' : symbol;
  const detailLoader = useCallback(() => (active ? outlookApi.symbol(active, null, apiHorizon) : Promise.resolve(null)), [active, tick, fresh, apiHorizon]);
  const hasRun = !!latestData?.run;
  const detail = usePollingAsync(detailLoader, [detailLoader], { enabled: visible && hasRun && !!active && !isHistory, intervalMs: 30000 });
  useEffect(() => {
    if (apiHorizon === 'DAILY' && detail.data && forHorizon(detail.data.outlook.horizon ?? detail.data.run.horizon, 'DAILY')) outlookCache.write('detail', detail.data);
  }, [detail.data, apiHorizon]);
  const detailMatches = (payload: NonNullable<typeof detail.data> | null) =>
    !!payload && payload.outlook.symbol === active && forHorizon(payload.outlook.horizon ?? payload.run.horizon, apiHorizon);
  const detailData = detailMatches(detail.data) ? detail.data : apiHorizon === 'DAILY' && detailMatches(cachedDetail) ? cachedDetail : null;
  const o = detailData?.outlook ?? null;

  const mtfLoader = useCallback(() => (active ? outlookApi.mtf(active, null, 42, apiHorizon) : Promise.resolve(null)), [active, tick, apiHorizon]);
  const mtf = usePollingAsync(mtfLoader, [mtfLoader], { enabled: visible && hasRun && !!active && section === 'chart', intervalMs: 120000 });

  const historyLoader = useCallback(() => (active ? outlookApi.history(active, days, apiHorizon) : Promise.resolve(null)), [active, days, tick, apiHorizon]);
  const history = usePollingAsync(historyLoader, [historyLoader], { enabled: visible && !!active && isHistory, intervalMs: 120000 });

  const chartTf: OutlookTf = isHistory ? spec.tf : tf;
  const limit = isHistory ? 400 : HISTORY_LIMIT[chartTf];
  const c = useCandles(active ?? 'XAUUSD', chartTf, visible && !!active, tick, limit);
  const liveTfs = useMemo(() => (section === 'chart' ? [chartTf, ...MINI_TFS] : [chartTf]), [section, chartTf]);
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
  const waiting = horizon === 'weekly' ? 'W1' : horizon === 'monthly' ? 'MN' : horizon === 'gold' ? 'H8' : 'D1';

  const body = () => {
    if (!latestData) return latest.error ? <Blocking title="AI Market Outlook unavailable" error={latest.error} /> : <Blocking loading="Loading the latest published outlook…" />;
    if (!run) {
      const cur = latestData.current;
      return (
        <Blocking
          title={cur ? `${spec.label} ${st.label.toLowerCase()} for ${dayLabel(cur.close_at || cur.analysis_date)}` : `No published ${spec.label.toLowerCase()} yet`}
          reason={cur?.error ?? cur?.log.at(-1)?.message ?? `The first outlook is generated automatically after the next finalized ${waiting} candle close.`}
        />
      );
    }
    if (isHistory) {
      if (!active) return <Blocking loading="Selecting instrument…" />;
      return (
        <HistoricalOutlook
          symbol={active}
          digits={rows.find((r) => r.symbol === active)?.digits ?? (isGold ? 2 : 5)}
          data={history.data && history.data.symbol === active && history.data.days === days && forHorizon(history.data.horizon, apiHorizon) ? history.data : null}
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
    if (o.status !== 'PUBLISHED') return <Blocking title={`${active} — ${o.status === 'FAILED' ? 'analysis failed' : 'insufficient data'}`} reason={o.reason ?? 'No outlook for this instrument on this close'} />;
    const props = { o, tf, onTf: setTf, candles, chartHeight };
    if (section === 'scenarios') return <ScenarioAnalysis {...props} />;
    if (section === 'levels') return <KeyLevels {...props} />;
    if (section === 'chart') return <ChartAnalysis {...props} mtf={mtf.data && mtf.data.symbol === active && forHorizon(mtf.data.horizon, apiHorizon) ? mtf.data : null} forming={live.data?.forming} />;
    return <DailyOutlook {...props} />;
  };

  const sessions = o?.session_plan ?? null;
  const context = o?.weekly?.interpretation || o?.strategic?.role || (o?.gold_session ? `Execution confirmation is M15. ${o.gold_session.force_trade ? '' : 'A setup is handed to Stage 7 and Stage 8 only after closed-bar confirmation.'}` : null);
  return (
    <div className="mst-page mao-page">
      <header className="mao-head">
        <div>
          <nav className="mst-crumb" aria-label="Breadcrumb">
            Market Vision <span aria-hidden>›</span> <span>AI Market Outlook</span>
          </nav>
          <h1>{spec.label}</h1>
          <p>{spec.blurb}</p>
        </div>
        <div className="mao-head-right">
          <StatusCluster
            title={spec.title}
            run={run}
            current={latestData?.current ?? null}
            schedule={schedule}
            withDays={horizon === 'weekly' || horizon === 'monthly'}
            onReload={() => setTick((t) => t + 1)}
            busy={latest.refreshing || detail.refreshing}
            runBusy={runBusy}
            onRunNow={
              horizon === 'daily'
                ? () => {
                    setRunBusy(true);
                    outlookApi
                      .runNow()
                      .then(() => setTick((t) => t + 1))
                      .finally(() => setRunBusy(false));
                  }
                : undefined
            }
          />
          {horizon === 'daily' && section !== 'overview' ? <SessionCards plans={sessions} schedule={schedule} captions={CAPTIONS[section]} /> : null}
        </div>
      </header>

      <div className="mao-tabs" role="tablist" aria-label="Outlook horizon">
        {HORIZONS.map((item) => (
          <button key={item.id} role="tab" aria-selected={horizon === item.id} className={horizon === item.id ? 'is-on' : ''} onClick={() => chooseHorizon(item.id)}>
            {item.label}
          </button>
        ))}
        {latestData?.stale ? <span className="mao-stale">Showing the last published outlook — the current cycle is {st.label.toLowerCase()}.</span> : null}
      </div>
      <div className="mao-tabs is-sub" role="tablist" aria-label="Outlook section">
        {SECTIONS.map((item) => (
          <button key={item.id} role="tab" aria-selected={section === item.id} className={section === item.id ? 'is-on' : ''} onClick={() => chooseSection(item.id)}>
            {item.label}
          </button>
        ))}
      </div>

      <div className="mao-toolbar">
        <SymbolPicker key={apiHorizon} label={`${spec.label} opportunities`} symbol={active} rows={isGold ? rows.filter((r) => r.symbol === 'XAUUSD') : rows} onSelect={setSymbol} allowAll={isHistory && !isGold} />
        <TfBar value={chartTf} tfs={isGold ? GOLD_TFS : undefined} onChange={(t) => !isHistory && setTf(t)} />
        <div className="mao-date">
          <small>Analysis close</small>
          <b>{run ? `${dayLabel(run.close_at || run.analysis_date)} (${spec.close})` : '—'}</b>
        </div>
        {horizon === 'daily' && section === 'overview' ? <SessionCards plans={sessions} schedule={schedule} /> : null}
      </div>
      {context && section === 'overview' ? <p className="mao-horizon-note">{context}</p> : null}

      {body()}
    </div>
  );
}

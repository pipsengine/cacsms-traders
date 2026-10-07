import { useCallback, useEffect, useMemo, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { EnginePlaceholder } from '../components/EnginePlaceholder';
import { usePollingAsync } from '../features/market-intelligence/hooks/useMarketIntelligence';
import { InstrumentIcon } from '../features/market-scanner/components/InstrumentIcon';
import { priceDigits } from '../features/market-scanner/format';
import { marketStructureApi } from '../features/market-structure/api';
import { StructureChart } from '../features/market-structure/components/StructureChart';
import {
  BoundaryDetails,
  DecisionPanel,
  DevelopingFractalPanel,
  HypothesisPanel,
  MtfAlignment,
  RangeSummaryCards,
} from '../features/market-structure/components/RangePanels';
import { RangeSymbolsTable } from '../features/market-structure/components/RangeSymbolsTable';
import { StructureOverview } from '../features/market-structure/components/StructureOverview';
import { TrendStructure } from '../features/market-structure/components/TrendStructure';
import type { HeaderTf, RangeMeta, TrendTf } from '../features/market-structure/types';

const TABS = [
  { id: 'overview', label: 'Structure Overview' },
  { id: 'trend', label: 'Trend Structure' },
  { id: 'range', label: 'Range Structure' },
  { id: 'fractals', label: 'Fractals' },
  { id: 'bos', label: 'BOS / CHoCH' },
];
const HEADER_TFS: HeaderTf[] = ['W', 'D', 'H8', 'H4'];
const TF_API: Record<HeaderTf, string> = { W: 'W', D: 'D1', H8: 'H8', H4: 'H4' };
const TF_TITLE: Record<HeaderTf, string> = { W: 'Weekly', D: 'Daily', H8: 'H8', H4: 'H4' };
const TF_BARS: Record<string, number> = { W: 160, D1: 72, H8: 72, H4: 120 };
const TREND_BARS: Record<TrendTf, number> = { W: 120, D1: 110, H8: 110, H1: 110 };

function useVisible() {
  const [visible, setVisible] = useState(() => typeof document === 'undefined' || document.visibilityState === 'visible');
  useEffect(() => {
    const onVis = () => setVisible(document.visibilityState === 'visible');
    document.addEventListener('visibilitychange', onVis);
    return () => document.removeEventListener('visibilitychange', onVis);
  }, []);
  return visible;
}

const SHORT_SCREEN = '(max-height: 900px)';

function useShortScreen() {
  const [short, setShort] = useState(() => typeof window !== 'undefined' && window.matchMedia(SHORT_SCREEN).matches);
  useEffect(() => {
    const mq = window.matchMedia(SHORT_SCREEN);
    const onChange = () => setShort(mq.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);
  return short;
}

function useCandles(symbol: string, tf: string, enabled: boolean, tick: number, limit = TF_BARS[tf] ?? 90) {
  const loader = useCallback(() => marketStructureApi.candles(symbol, tf, limit), [symbol, tf, tick, limit]);
  const res = usePollingAsync(loader, [loader], { enabled, intervalMs: 60000 });
  const ok = res.data?.symbol === symbol && res.data.timeframe === tf;
  return { candles: ok ? res.data!.candles : [], loading: res.loading || !ok, error: res.error };
}

function liveStatus(meta: RangeMeta | null, error: boolean) {
  if (!meta) return { tone: error ? 'off' : 'warn', label: error ? 'Analysis Unavailable' : 'Connecting' };
  if (!meta.mt5_connected) return { tone: 'off', label: 'MT5 Disconnected' };
  if (meta.stale) return { tone: 'warn', label: 'Stale Analysis' };
  return { tone: 'live', label: 'Live Analysis' };
}

function localStamp(iso: string | null | undefined) {
  if (!iso) return '—';
  return new Intl.DateTimeFormat('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZoneName: 'short',
  }).format(new Date(iso));
}

export function MarketStructure() {
  const visible = useVisible();
  const short = useShortScreen();
  const [tab, setTab] = useState('overview');
  const [symbol, setSymbol] = useState('XAUUSD');
  const [tf, setTf] = useState<HeaderTf>('W');
  const [tick, setTick] = useState(0);
  const active = visible && tab === 'range';

  const listLoader = useCallback(() => marketStructureApi.ranges(), [tick]);
  const list = usePollingAsync(listLoader, [listLoader], { enabled: visible, intervalMs: 5000 });
  const detailLoader = useCallback(() => marketStructureApi.range(symbol), [symbol, tick]);
  const detail = usePollingAsync(detailLoader, [detailLoader], { enabled: active, intervalMs: 5000 });
  const overviewLoader = useCallback(() => marketStructureApi.overview(), [tick]);
  const overview = usePollingAsync(overviewLoader, [overviewLoader], { enabled: visible && tab === 'overview', intervalMs: 5000 });
  const [trendTf, setTrendTf] = useState<TrendTf>('D1');
  const trendActive = visible && tab === 'trend';
  const trendsLoader = useCallback(() => marketStructureApi.trends(), [tick]);
  const trends = usePollingAsync(trendsLoader, [trendsLoader], { enabled: trendActive, intervalMs: 5000 });
  const trendLoader = useCallback(() => marketStructureApi.trend(symbol), [symbol, tick]);
  const trend = usePollingAsync(trendLoader, [trendLoader], { enabled: trendActive, intervalMs: 5000 });
  const trendCandles = useCandles(symbol, trendTf, trendActive, tick, TREND_BARS[trendTf]);
  const trendDetail = trend.data && trend.data.summary.symbol === symbol ? trend.data : null;

  const mainTf = TF_API[tf];
  const main = useCandles(symbol, mainTf, active, tick);
  const d1 = useCandles(symbol, 'D1', active, tick);
  const h8 = useCandles(symbol, 'H8', active, tick);

  const meta = list.data?.meta ?? null;
  const rows = list.data?.rows ?? [];
  const d = detail.data && detail.data.summary.symbol === symbol ? detail.data : null;
  const row = d?.summary ?? rows.find((r) => r.symbol === symbol) ?? null;
  const digits = row ? priceDigits({ digits: row.digits ?? undefined, symbol: row.symbol, quote: row.quote }) : 2;
  const status = liveStatus(meta, !!list.error);
  const extremePct = Number(meta?.range_settings?.extreme_pct ?? 20);
  const breakoutMin = Number((meta?.range_settings?.hypothesis_bands as { label_min?: number } | undefined)?.label_min ?? 55);
  const symbols = useMemo(() => (rows.length ? rows.map((r) => r.symbol) : ['XAUUSD']), [rows]);

  return (
    <div className="mst-page">
      <header className="mst-head">
        <div>
          <nav className="mst-crumb" aria-label="Breadcrumb">
            Market Vision <span aria-hidden>›</span> <span>Market Structure</span>
          </nav>
          <h1>Market Structure</h1>
          <p>Analyse market structure, weekly ranges and fractal levels across multiple timeframes</p>
        </div>
        <div className="mst-head-actions">
          <label className="mst-symbol-select">
            <InstrumentIcon base={symbol.slice(0, 3)} quote={symbol.slice(3, 6)} size="sm" />
            <select value={symbol} onChange={(e) => setSymbol(e.target.value)} aria-label="Instrument">
              {symbols.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <div className="mst-tf" role="group" aria-label="Primary chart timeframe">
            {HEADER_TFS.map((x) => (
              <button key={x} className={tf === x ? 'is-on' : ''} onClick={() => setTf(x)}>
                {x}
              </button>
            ))}
          </div>
          <div className={`mst-live is-${status.tone}`} role="status">
            <b>
              <i aria-hidden /> {status.label}
            </b>
            <small>Last update: {localStamp(meta?.last_cycle_at)}</small>
          </div>
          <button className="mst-refresh" aria-label="Reload analysis" title="Reload latest analysis" onClick={() => setTick((t) => t + 1)}>
            <RefreshCw size={16} className={list.refreshing || detail.refreshing || overview.refreshing || trends.refreshing || trend.refreshing ? 'is-spin' : ''} />
          </button>
        </div>
      </header>

      <div className="mst-tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t.id} role="tab" aria-selected={tab === t.id} className={tab === t.id ? 'is-on' : ''} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'overview' ? (
        overview.data ? (
          <StructureOverview data={overview.data} selected={symbol} onSelect={setSymbol} />
        ) : (
          <section className={`mst-card mst-blocking ${overview.error ? 'is-error' : ''}`}>
            {overview.error ? (
              <>
                <strong>Structure Overview unavailable</strong>
                <span>{overview.error}</span>
                <button className="mst-view" onClick={overview.refresh}>
                  Retry
                </button>
              </>
            ) : (
              <>
                <span className="mst-spinner" aria-hidden />
                Loading structure overview…
              </>
            )}
          </section>
        )
      ) : tab === 'trend' ? (
        trends.data ? (
          <TrendStructure
            data={trends.data}
            detail={trendDetail}
            detailError={trend.error}
            symbol={symbol}
            onSelect={setSymbol}
            tf={trendTf}
            onTf={setTrendTf}
            candles={trendCandles}
            chartHeight={short ? 250 : 318}
          />
        ) : (
          <section className={`mst-card mst-blocking ${trends.error ? 'is-error' : ''}`}>
            {trends.error ? (
              <>
                <strong>Trend Structure unavailable</strong>
                <span>{trends.error}</span>
                <button className="mst-view" onClick={trends.refresh}>
                  Retry
                </button>
              </>
            ) : (
              <>
                <span className="mst-spinner" aria-hidden />
                Loading trend structure…
              </>
            )}
          </section>
        )
      ) : tab !== 'range' ? (
        <EnginePlaceholder
          title={TABS.find((t) => t.id === tab)!.label}
          body="This structure view will bind to the structure intelligence engine. Range Structure is live."
          engine="structure_intelligence"
        />
      ) : list.error && !list.data ? (
        <section className="mst-card mst-blocking is-error">
          <strong>Range Structure unavailable</strong>
          <span>{list.error}</span>
          <button className="mst-view" onClick={list.refresh}>
            Retry
          </button>
        </section>
      ) : !d ? (
        <section className="mst-card mst-blocking">
          <span className="mst-spinner" aria-hidden />
          {detail.error ? `Analysis unavailable: ${detail.error}` : `Loading ${symbol} range structure…`}
        </section>
      ) : !d.available ? (
        <>
          <section className="mst-card mst-blocking">
            <strong>{symbol} — range structure unavailable</strong>
            <span>{d.summary.unavailable_reason}</span>
          </section>
          <RangeSymbolsTable rows={rows} counts={list.data?.counts ?? null} extremePct={extremePct} breakoutMin={breakoutMin} selected={symbol} onView={setSymbol} />
        </>
      ) : (
        <>
          <RangeSummaryCards row={d.summary} core={d.range} view={d.view} digits={digits} />
          <div className={`mst-charts ${meta?.stale ? 'is-stale' : ''}`}>
            <StructureChart
              symbol={symbol}
              title={TF_TITLE[tf]}
              tf={mainTf}
              candles={main.candles}
              loading={main.loading}
              error={main.error}
              digits={digits}
              lastPrice={d.summary.price}
              range={{ ...d.range, fractals: mainTf === 'W' ? d.range.fractals : [] }}
              height={short ? 172 : 236}
            />
            <StructureChart
                symbol={symbol}
                title="Daily"
                tf="D1"
                candles={d1.candles}
                loading={d1.loading}
                error={d1.error}
                digits={digits}
                lastPrice={d.summary.price}
                channel={d.channels.D1}
                height={short ? 196 : 260}
              />
            <StructureChart
                symbol={symbol}
                title="H8"
                tf="H8"
                candles={h8.candles}
                loading={h8.loading}
                error={h8.error}
                digits={digits}
                lastPrice={d.summary.price}
                channel={d.channels.H8}
                height={short ? 196 : 260}
              />
          </div>
          <div className="mst-intel">
            <BoundaryDetails core={d.range} digits={digits} />
            <DevelopingFractalPanel view={d.view} digits={digits} />
            <div className="mst-intel-mid">
              <MtfAlignment view={d.view} />
              <HypothesisPanel view={d.view} />
            </div>
            <DecisionPanel view={d.view} />
          </div>
          <RangeSymbolsTable
            rows={rows}
            counts={list.data?.counts ?? null}
            extremePct={extremePct}
            breakoutMin={breakoutMin}
            selected={symbol}
            onView={(s) => {
              setSymbol(s);
              window.scrollTo({ top: 0, behavior: 'smooth' });
            }}
          />
        </>
      )}
    </div>
  );
}

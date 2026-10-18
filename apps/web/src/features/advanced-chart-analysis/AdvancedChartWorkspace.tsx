import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  BarChart3,
  CandlestickChart,
  GitCompare,
  Layers,
  LayoutTemplate,
  LineChart,
  Maximize2,
  Minus,
  MousePointer2,
  PenLine,
  Save,
  Search,
  Settings2,
  Shapes,
  Sigma,
  Square,
  Target,
  Trash2,
  TrendingUp,
  Type,
  Undo2,
  Redo2,
  Magnet,
} from 'lucide-react';
import { usePollingAsync } from '../market-intelligence/hooks/useMarketIntelligence';
import { chartApi } from './api';
import { PriceChart } from './PriceChart';
import { RsiPane } from './RsiPane';
import { MacdPane } from './MacdPane';
import { AtrPane } from './AtrPane';
import { useChartIntel } from './useChartIntel';
import type { Analysis, Candle, Drawing, Overlay, Quote } from './types';

const TF = ['M1', 'M5', 'M15', 'M30', 'H1', 'H8', 'D1', 'W1', 'MN', 'Q'] as const;
const DEFAULT_SYMBOLS = ['XAUUSD'];
const LAYER_OPTIONS = [
  'My Drawings',
  'AI Market Outlook',
  'Market Structure (BOS/CHoCH)',
  'Channel Intelligence',
  'Key Levels (S/R)',
  'Moving Averages',
  'Indicators',
  'Volume',
  'Supertrend (10, 3)',
] as const;

const INDICATOR_PANES = ['RSI (14)', 'MACD (12,26,9)', 'ATR (14)'] as const;
type IndicatorPane = (typeof INDICATOR_PANES)[number];

function fmtPrice(symbol: string, v: number | null | undefined) {
  if (v == null) return '—';
  return v.toFixed(symbol === 'XAUUSD' ? 2 : 5);
}

export function AdvancedChartWorkspace({ initialSymbol }: { initialSymbol?: string }) {
  const [symbol, setSymbol] = useState(initialSymbol || 'XAUUSD');
  const [tf, setTf] = useState('H1');
  const [symbols, setSymbols] = useState<string[]>(DEFAULT_SYMBOLS);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [drawings, setDrawings] = useState<Drawing[]>([]);
  const [overlays, setOverlays] = useState<Overlay[]>([]);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [analyses, setAnalyses] = useState<Analysis[]>([]);
  const [layers, setLayers] = useState<string[]>([...LAYER_OPTIONS]);
  const [tool, setTool] = useState('cursor');
  const [tab, setTab] = useState('Indicators');
  const [watchTab, setWatchTab] = useState<'all' | 'forex' | 'commodities' | 'indices'>('all');
  const [watchSearch, setWatchSearch] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [panel, setPanel] = useState(true);
  const [full, setFull] = useState(false);
  const [notes, setNotes] = useState('');
  const [source, setSource] = useState('Strategy-Based');
  const [direction, setDirection] = useState('BUY');
  const [strategy, setStrategy] = useState('Channel Continuation');
  const [selectedAnalysis, setSelectedAnalysis] = useState<string | undefined>();
  const [workspaceRev, setWorkspaceRev] = useState<string | null>(null);
  const [watchQuotes, setWatchQuotes] = useState<Record<string, Quote>>({});
  const [snapEnabled, setSnapEnabled] = useState(true);
  const [indicatorPane, setIndicatorPane] = useState<IndicatorPane>('RSI (14)');
  const [histTick, setHistTick] = useState(0);
  const drawHistoryRef = useRef<Drawing[][]>([[]]);
  const histIdxRef = useRef(0);
  const fetchGen = useRef(0);
  const intel = useChartIntel(symbol);

  const resetDrawHistory = useCallback((list: Drawing[]) => {
    drawHistoryRef.current = [list];
    histIdxRef.current = 0;
    setDrawings(list);
    setHistTick((x) => x + 1);
  }, []);

  const commitDrawings = useCallback((next: Drawing[]) => {
    const trimmed = drawHistoryRef.current.slice(0, histIdxRef.current + 1);
    trimmed.push(next);
    drawHistoryRef.current = trimmed;
    histIdxRef.current = trimmed.length - 1;
    setDrawings(next);
    setHistTick((x) => x + 1);
  }, []);

  const undoDrawing = useCallback(() => {
    if (histIdxRef.current <= 0) return;
    histIdxRef.current -= 1;
    setDrawings(drawHistoryRef.current[histIdxRef.current] ?? []);
    setHistTick((x) => x + 1);
  }, []);

  const redoDrawing = useCallback(() => {
    if (histIdxRef.current >= drawHistoryRef.current.length - 1) return;
    histIdxRef.current += 1;
    setDrawings(drawHistoryRef.current[histIdxRef.current] ?? []);
    setHistTick((x) => x + 1);
  }, []);

  const canUndo = histIdxRef.current > 0;
  const canRedo = histIdxRef.current < drawHistoryRef.current.length - 1;
  void histTick;

  useEffect(() => {
    chartApi.symbols().then(setSymbols).catch(() => undefined);
  }, []);

  const loadBundle = useCallback(async (sym: string, timeframe: string, signal: AbortSignal) => {
    const [cs, ov, ws, an, q] = await Promise.all([
      chartApi.candles(sym, timeframe),
      chartApi.overlays(sym, timeframe),
      chartApi.workspace(sym, timeframe),
      chartApi.analyses(sym),
      chartApi.quote(sym),
    ]);
    if (signal.aborted) return;
    setCandles(cs);
    setOverlays(ov);
    resetDrawHistory(ws.drawings);
    if (ws.layers?.length) setLayers(ws.layers);
    setAnalyses(an);
    setQuote(q);
    setWorkspaceRev(ws.updated_at ?? null);
  }, [resetDrawHistory]);

  useEffect(() => {
    const gen = ++fetchGen.current;
    const ctrl = new AbortController();
    setBusy(true);
    setError('');
    loadBundle(symbol, tf, ctrl.signal)
      .catch((e: Error) => {
        if (!ctrl.signal.aborted) {
          setError(`Market data or workspace unavailable: ${e.message}`);
          setCandles([]);
          setOverlays([]);
          setQuote(null);
        }
      })
      .finally(() => {
        if (fetchGen.current === gen && !ctrl.signal.aborted) setBusy(false);
      });
    return () => ctrl.abort();
  }, [symbol, tf, loadBundle]);

  const refreshQuote = useCallback(async () => {
    try {
      setQuote(await chartApi.quote(symbol));
    } catch {
      /* keep */
    }
  }, [symbol]);

  const refreshCandles = useCallback(async () => {
    try {
      setCandles(await chartApi.candles(symbol, tf));
    } catch {
      /* keep */
    }
  }, [symbol, tf]);

  usePollingAsync(refreshQuote, [refreshQuote], { enabled: true, intervalMs: 2000 });
  usePollingAsync(refreshCandles, [refreshCandles], { enabled: true, intervalMs: 5000 });

  const addDrawing = useCallback((d: Drawing) => {
    setDrawings((old) => {
      const next = [...old, d];
      const trimmed = drawHistoryRef.current.slice(0, histIdxRef.current + 1);
      trimmed.push(next);
      drawHistoryRef.current = trimmed;
      histIdxRef.current = trimmed.length - 1;
      setHistTick((x) => x + 1);
      return next;
    });
  }, []);

  const save = async () => {
    setBusy(true);
    try {
      const saved = await chartApi.saveWorkspace({
        symbol,
        timeframe: tf,
        drawings,
        indicators: layers.includes('Indicators') ? ['RSI'] : [],
        layers,
        expected_updated_at: workspaceRev,
      });
      setWorkspaceRev(saved.updated_at ?? null);
      setNotice('Layout saved for this symbol and timeframe');
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  const saveAnalysis = async () => {
    try {
      const a = await chartApi.saveAnalysis({ symbol, timeframe: tf, title: `${symbol} ${tf} analysis`, notes });
      setAnalyses((v) => [a, ...v]);
      setSelectedAnalysis(a.id);
      setNotice('Analysis saved');
    } catch (e) {
      setError(String(e));
    }
  };

  const createOpportunity = async () => {
    try {
      const v = await chartApi.createOpportunity({ symbol, timeframe: tf, direction, strategy, notes, analysis_id: selectedAnalysis });
      setNotice(`Potential opportunity ${v.id} saved for review`);
    } catch (e) {
      setError(String(e));
    }
  };

  const watchSymbols = useMemo(() => {
    let list = symbols;
    if (watchTab === 'forex') list = symbols.filter((s) => s !== 'XAUUSD');
    if (watchTab === 'commodities') list = symbols.filter((s) => s === 'XAUUSD');
    if (watchTab === 'indices') list = [];
    const q = watchSearch.toUpperCase();
    return list.filter((s) => s.includes(q));
  }, [symbols, watchTab, watchSearch]);

  const watchBatchKey = watchSymbols.slice(0, 35).join(',');
  const refreshWatchQuotes = useCallback(async () => {
    const batch = watchSymbols.slice(0, 35);
    if (!batch.length) return;
    try {
      setWatchQuotes(await chartApi.quotes(batch));
    } catch {
      /* keep last batch */
    }
  }, [watchBatchKey]);

  usePollingAsync(refreshWatchQuotes, [refreshWatchQuotes], { enabled: true, intervalMs: 5000 });

  const latest = candles.at(-1);
  const prev = candles.length > 1 ? candles[candles.length - 2] : null;
  const chgPct = latest && prev && prev.close ? ((latest.close - prev.close) / prev.close) * 100 : null;

  const shownOverlays = overlays.filter((o) => {
    if (o.source === 'ai' && layers.includes('AI Market Outlook')) return true;
    if (o.source === 'structure' && layers.some((l) => l.startsWith('Market Structure'))) return true;
    if (o.source === 'channel' && layers.includes('Channel Intelligence')) return true;
    if (o.source === 'levels' && layers.some((l) => l.startsWith('Key Levels'))) return true;
    return false;
  });

  const o = intel.data?.outlook?.outlook;
  const range = intel.data?.range?.available ? intel.data.range : null;
  const trend = intel.data?.trend?.available ? intel.data.trend : null;
  const dir = o?.expected_direction ?? 'NEUTRAL';
  const verdictClass = dir === 'BULLISH' ? 'bull' : dir === 'BEARISH' ? 'bear' : 'neutral';
  const evidence = o?.confidence?.primary != null ? Math.round(o.confidence.primary) : null;

  return (
    <div className={full ? 'advanced-chart-analysis fullscreen' : 'advanced-chart-analysis'}>
      <div className="aca-top-actions">
        <button type="button" onClick={save} disabled={busy}>
          <Save size={15} /> Save Layout
        </button>
        <button type="button" onClick={() => setPanel((x) => !x)}>
          <Layers size={15} /> {panel ? 'Hide Panels' : 'Show Panels'}
        </button>
        <button type="button" onClick={() => setFull((x) => !x)}>
          <Maximize2 size={15} /> {full ? 'Exit Fullscreen' : 'Expand'}
        </button>
      </div>
      {error && (
        <div className="error" role="alert">
          {error}{' '}
          <button type="button" onClick={() => window.location.reload()}>
            Retry
          </button>
        </div>
      )}
      {notice && (
        <div className="notice" role="status" onClick={() => setNotice('')}>
          {notice} ×
        </div>
      )}
      <div className="workspace">
        <div className="chart-column">
          <div className="chart-card">
            <div className="chart-toolbar">
              <select aria-label="Symbol" value={symbol} onChange={(e) => setSymbol(e.target.value)}>
                {symbols.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
              <div className="timeframes">
                {TF.map((t) => (
                  <button key={t} type="button" className={t === tf ? 'selected' : ''} onClick={() => setTf(t)}>
                    {t}
                  </button>
                ))}
              </div>
              <span className="toolbar-sep" />
              <button type="button" title="Candlestick">
                <CandlestickChart size={15} /> Candlestick
              </button>
              <button type="button" title="Indicators">
                <LineChart size={15} /> Indicators
              </button>
              <button type="button" title="Compare symbols" disabled>
                <GitCompare size={15} /> Compare
              </button>
              <button type="button" title="Templates">
                <LayoutTemplate size={15} /> Templates
              </button>
              <div className="aca-toolbar-meta">
                {latest && (
                  <span>
                    O {fmtPrice(symbol, latest.open)} H {fmtPrice(symbol, latest.high)} L {fmtPrice(symbol, latest.low)} C{' '}
                    {fmtPrice(symbol, latest.close)}
                  </span>
                )}
                {chgPct != null && (
                  <span className={chgPct >= 0 ? 'aca-chg-up' : 'aca-chg-down'}>
                    {chgPct >= 0 ? '+' : ''}
                    {chgPct.toFixed(2)}%
                  </span>
                )}
              </div>
            </div>
            <div className="chart-area">
              <div className="drawing-tools">
                {[
                  { id: 'cursor', Icon: MousePointer2, title: 'Crosshair' },
                  { id: 'trendline', Icon: PenLine, title: 'Trendline' },
                  { id: 'horizontal', Icon: Minus, title: 'Horizontal line' },
                  { id: 'rectangle', Icon: Square, title: 'Rectangle zone' },
                  { id: 'text', Icon: Type, title: 'Text' },
                ].map(({ id, Icon, title }) => (
                  <button key={id} type="button" title={title} className={tool === id ? 'active' : ''} onClick={() => setTool(id)}>
                    <Icon size={18} />
                  </button>
                ))}
                <hr />
                <button type="button" title="Fibonacci retracement" className={tool === 'fibonacci' ? 'active' : ''} onClick={() => setTool('fibonacci')}>
                  <Sigma size={17} />
                </button>
                <button type="button" title="Parallel channel (3 clicks)" className={tool === 'channel' ? 'active' : ''} onClick={() => setTool('channel')}>
                  <Shapes size={17} />
                </button>
                <button type="button" title={snapEnabled ? 'Snap to OHLC on' : 'Snap to OHLC off'} className={snapEnabled ? 'active' : ''} onClick={() => setSnapEnabled((x) => !x)}>
                  <Magnet size={17} />
                </button>
                <button type="button" title="Undo drawing" disabled={!canUndo} onClick={undoDrawing}>
                  <Undo2 size={17} />
                </button>
                <button type="button" title="Redo drawing" disabled={!canRedo} onClick={redoDrawing}>
                  <Redo2 size={17} />
                </button>
                <button
                  type="button"
                  title="Remove last drawing"
                  onClick={() => {
                    if (!drawings.length) return;
                    commitDrawings(drawings.slice(0, -1));
                  }}
                >
                  <Trash2 size={17} />
                </button>
              </div>
              <div className="price-area">
                <div className="chart-heading">
                  <strong>
                    {symbol} · {tf}
                  </strong>
                  {quote?.bid != null && <span>Bid {fmtPrice(symbol, quote.bid)}</span>}
                  {quote?.stale && <b className="stale">STALE QUOTE</b>}
                  {latest && !latest.closed && <b className="stale">FORMING BAR</b>}
                </div>
                {busy && <div className="loading">Loading chart…</div>}
                <PriceChart
                  symbol={symbol}
                  timeframe={tf}
                  candles={candles}
                  drawings={layers.includes('My Drawings') ? drawings : []}
                  overlays={shownOverlays}
                  tool={tool}
                  onDrawing={addDrawing}
                  showVolume={layers.includes('Volume')}
                  showEMA={layers.includes('Moving Averages')}
                  showSupertrend={layers.includes('Supertrend (10, 3)')}
                  snapEnabled={snapEnabled}
                />
              </div>
            </div>
            <div className="chart-tabs">
              {['Indicators', 'Pine Editor', 'Strategy Tester', 'Trading Panel'].map((t) => (
                <button key={t} type="button" className={tab === t ? 'selected' : ''} onClick={() => setTab(t)}>
                  {t}
                </button>
              ))}
            </div>
            <div className="tab-content">
              {tab === 'Indicators' && layers.includes('Indicators') && (
                <>
                  <div className="aca-indicator-tabs">
                    {INDICATOR_PANES.map((p) => (
                      <button key={p} type="button" className={indicatorPane === p ? 'selected' : ''} onClick={() => setIndicatorPane(p)}>
                        {p}
                      </button>
                    ))}
                  </div>
                  {indicatorPane === 'RSI (14)' && <RsiPane candles={candles} />}
                  {indicatorPane === 'MACD (12,26,9)' && <MacdPane candles={candles} />}
                  {indicatorPane === 'ATR (14)' && <AtrPane candles={candles} />}
                </>
              )}
              {tab === 'Indicators' && !layers.includes('Indicators') && (
                <span>Enable the Indicators layer to show RSI, MACD, and ATR panes.</span>
              )}
              {tab === 'Pine Editor' && <span>Pine Editor connects to your Cacsms scripting boundary — not enabled in this environment.</span>}
              {tab === 'Strategy Tester' && <span>Strategy Tester uses the autonomous backtest pipeline — open Cacsms Engine for full runs.</span>}
              {tab === 'Trading Panel' && <span>Draft opportunities only; execution remains in engine Stages 2–3.</span>}
            </div>
          </div>
          <div className="bottom-panels">
            <section className="card">
              <div className="card-head">
                <strong>AI Market Outlook ({symbol})</strong>
                <a href="#/ai-market-outlook">View full</a>
              </div>
              {o ? (
                <>
                  <div className="aca-verdict">
                    <span className={`aca-badge ${verdictClass}`}>{dir === 'BULLISH' ? 'Bullish' : dir === 'BEARISH' ? 'Bearish' : 'Neutral'}</span>
                    {evidence != null && <span>Evidence score {evidence}/100</span>}
                  </div>
                  {evidence != null && (
                    <div className="aca-evidence-bar">
                      <span style={{ width: `${Math.min(100, evidence)}%` }} />
                    </div>
                  )}
                  <p style={{ fontSize: 12, lineHeight: 1.5, margin: '0 0 8px' }}>{o.primary_scenario?.summary ?? o.phase?.title ?? 'Published outlook loaded.'}</p>
                  <dl className="aca-kv-grid">
                    <dt>Entry zone</dt>
                    <dd>{o.erz?.label ?? '—'}</dd>
                    <dt>Invalidation</dt>
                    <dd>{o.invalidation?.price != null ? fmtPrice(symbol, o.invalidation.price) : '—'}</dd>
                    <dt>Target 1</dt>
                    <dd>{o.targets?.[0]?.price != null ? fmtPrice(symbol, o.targets[0].price) : '—'}</dd>
                    <dt>Target 2</dt>
                    <dd>{o.targets?.[1]?.price != null ? fmtPrice(symbol, o.targets[1].price) : '—'}</dd>
                  </dl>
                </>
              ) : (
                <p className="muted">No published outlook for {symbol}. Overlays appear when intelligence is available.</p>
              )}
            </section>
            <section className="card">
              <div className="card-head">
                <strong>Market Structure</strong>
                <a href="#/market-structure">View full</a>
              </div>
              <div className="metricline">
                <span>Current structure</span>
                <b>{trend?.summary?.state?.label ?? range?.summary?.regime?.label ?? '—'}</b>
              </div>
              <div className="metricline">
                <span>Range high</span>
                <b>{range?.range?.range_high != null ? fmtPrice(symbol, range.range.range_high) : '—'}</b>
              </div>
              <div className="metricline">
                <span>Range low</span>
                <b>{range?.range?.range_low != null ? fmtPrice(symbol, range.range.range_low) : '—'}</b>
              </div>
              <div className="metricline">
                <span>Chart timeframe</span>
                <b>{tf}</b>
              </div>
              <div className="metricline">
                <span>Confirmed overlays</span>
                <b>{overlays.filter((x) => x.confirmed).length}</b>
              </div>
            </section>
            <section className="card">
              <div className="card-head">
                <strong>Recent Analysis</strong>
                <button type="button" className="link" onClick={saveAnalysis}>
                  Save current
                </button>
              </div>
              <textarea placeholder="Notes before saving…" value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} />
              {analyses.slice(0, 4).map((a) => (
                <button
                  type="button"
                  className="analysis-row"
                  key={a.id}
                  onClick={() => {
                    setNotes(a.notes);
                    setSelectedAnalysis(a.id);
                  }}
                >
                  <span>{a.title}</span>
                  <small>{new Date(a.created_at).toLocaleString()}</small>
                </button>
              ))}
              {!analyses.length && <p style={{ fontSize: 11, color: '#94a3b8' }}>No saved analyses yet.</p>}
            </section>
          </div>
        </div>
        {panel && (
          <aside className="rightpanels">
            <section className="card watchlist">
              <div className="card-head">
                <strong>Watchlist</strong>
                <span>{symbols.length} symbols</span>
              </div>
              <div className="aca-watch-tabs">
                {(['all', 'forex', 'commodities', 'indices'] as const).map((t) => (
                  <button key={t} type="button" className={watchTab === t ? 'active' : ''} onClick={() => setWatchTab(t)}>
                    {t === 'all' ? 'All' : t[0].toUpperCase() + t.slice(1)}
                  </button>
                ))}
              </div>
              <div className="watch-search">
                <Search size={14} />
                <input placeholder="Filter symbols" value={watchSearch} onChange={(e) => setWatchSearch(e.target.value)} />
              </div>
              <div className="aca-watch-head">
                <span>Symbol</span>
                <span>Bid</span>
                <span>Ask</span>
                <span>Chg%</span>
              </div>
              <div className="watch-scroll">
                {watchSymbols.map((s) => {
                  const isActive = s === symbol;
                  const wq = watchQuotes[s];
                  const bid = wq?.bid ?? (isActive ? quote?.bid : null);
                  const ask = wq?.ask ?? (isActive ? quote?.ask : null);
                  const chg = wq?.change_pct ?? (isActive ? chgPct : null);
                  return (
                    <button type="button" key={s} className={`watchrow ${isActive ? 'current' : ''}`} onClick={() => setSymbol(s)}>
                      <strong>{s}</strong>
                      <span>{fmtPrice(s, bid)}</span>
                      <span>{fmtPrice(s, ask)}</span>
                      <span className={chg != null && chg >= 0 ? 'aca-chg-up' : 'aca-chg-down'}>
                        {chg != null ? `${chg >= 0 ? '+' : ''}${chg.toFixed(2)}%` : '—'}
                      </span>
                    </button>
                  );
                })}
              </div>
            </section>
            <section className="card">
              <div className="card-head">
                <strong>Drawing tree</strong>
                <span>{drawings.length}</span>
              </div>
              <div className="aca-drawing-list">
                {drawings.slice(0, 12).map((d) => (
                  <div className="aca-drawing-row" key={d.id}>
                    <span>{d.kind}</span>
                    <button
                      type="button"
                      className="link"
                      onClick={() => commitDrawings(drawings.filter((x) => x.id !== d.id))}
                    >
                      Remove
                    </button>
                  </div>
                ))}
                {!drawings.length && <p className="muted" style={{ fontSize: 11, margin: 0 }}>No drawings on this layout.</p>}
              </div>
            </section>
            <section className="card">
              <div className="card-head">
                <strong>Analysis Layers</strong>
                <Settings2 size={15} />
              </div>
              {LAYER_OPTIONS.map((l) => (
                <label className="layer" key={l}>
                  <input
                    type="checkbox"
                    checked={layers.includes(l)}
                    onChange={(e) => setLayers((v) => (e.target.checked ? [...v, l] : v.filter((x) => x !== l)))}
                  />
                  <span>{l}</span>
                  <button type="button" className="aca-layer-gear" aria-label={`${l} settings`}>
                    <Settings2 size={13} />
                  </button>
                </label>
              ))}
            </section>
            <section className="card opportunity">
              <div className="card-head">
                <strong>Create Opportunity</strong>
                <span>Manual draft</span>
              </div>
              <div className="field">
                <label htmlFor="aca-source">Source</label>
                <select id="aca-source" value={source} onChange={(e) => setSource(e.target.value)}>
                  {['Strategy-Based', 'AI Outlook', 'Structure Break'].map((x) => (
                    <option key={x} value={x}>
                      {x}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="aca-strategy">Strategy type</label>
                <select id="aca-strategy" value={strategy} onChange={(e) => setStrategy(e.target.value)}>
                  {['Trend-in-Trend', 'Channel Continuation', 'Breakout–Retest'].map((x) => (
                    <option key={x} value={x}>
                      {x}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <span>Direction</span>
                <div className="two-buttons">
                  <button type="button" className={direction === 'BUY' ? 'buy' : ''} onClick={() => setDirection('BUY')}>
                    Buy
                  </button>
                  <button type="button" className={direction === 'SELL' ? 'sell' : ''} onClick={() => setDirection('SELL')}>
                    Sell
                  </button>
                </div>
              </div>
              <textarea placeholder="Notes…" value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} />
              <button type="button" className="primary" onClick={createOpportunity}>
                <Target size={16} /> Save as Potential Opportunity
              </button>
              <small>No broker order is placed. Confirmation and risk gates remain mandatory.</small>
            </section>
          </aside>
        )}
      </div>
    </div>
  );
}

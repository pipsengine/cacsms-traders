import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Bell, BellOff, RefreshCw, Settings } from 'lucide-react';
import { usePollingAsync } from '../features/market-intelligence/hooks/useMarketIntelligence';
import { h8BosBtlApi } from '../features/h8-bos-btl/api';
import { BreakChart } from '../features/h8-bos-btl/components/BreakChart';
import { AlertStrip, AnalysisPanel, SummaryCards, fmtUtc } from '../features/h8-bos-btl/components/H8Panels';
import { h1Overlays, h8Overlays, m30Overlays, weeklyOverlays } from '../features/h8-bos-btl/overlays';
import type { AlertKind, ChartTf, H8BosBtlDetail } from '../features/h8-bos-btl/types';

const CHART_TITLES: Record<ChartTf, string> = {
  W: 'W — Weekly (Fractal + SCH)',
  H8: 'H8 — Primary Structure (BOS / BTL)',
  H1: 'H1 — Structural Validation',
  M30: 'M30 — Confirmation / Retest',
};
const PILLS = ['W', 'D', 'H8', 'H1', 'M30'];

function urlSymbol() {
  return new URLSearchParams(window.location.search).get('symbol')?.toUpperCase() ?? '';
}

function writeUrlSymbol(symbol: string) {
  const q = new URLSearchParams(window.location.search);
  q.set('symbol', symbol);
  window.history.replaceState(null, '', `${window.location.pathname}?${q}${window.location.hash}`);
}

function ChartCard({ tf, d }: { tf: ChartTf; d: H8BosBtlDetail }) {
  const overlays = useMemo(
    () => (tf === 'W' ? weeklyOverlays(d) : tf === 'H8' ? h8Overlays(d) : tf === 'H1' ? h1Overlays(d) : m30Overlays(d)),
    [tf, d],
  );
  const status = tf === 'W' ? d.weekly.state : tf === 'H8' ? d.retest_status?.label : tf === 'H1' ? d.h1.status.label : d.m30.status.label;
  return (
    <article className="h8b-chart-card">
      <header>
        <b>{CHART_TITLES[tf]}</b>
        <div className="h8b-chart-meta">
          {status && <span className="h8b-chart-status">{status}</span>}
          <div className="h8b-pills" aria-hidden>
            {PILLS.map((p) => (
              <span key={p} className={p === tf ? 'is-on' : ''}>
                {p}
              </span>
            ))}
          </div>
        </div>
      </header>
      <BreakChart
        tf={tf}
        candles={d.candles[tf]}
        digits={d.digits}
        overlays={overlays}
        sch={tf === 'W' ? d.weekly.sch : undefined}
        price={tf === 'W' ? null : d.price}
      />
    </article>
  );
}

function SettingsPopover({ settings, onClose }: { settings: Record<string, unknown>; onClose: () => void }) {
  return (
    <div className="h8b-pop" role="dialog" aria-label="Detection thresholds">
      <header>
        <b>Detection thresholds</b>
        <button type="button" onClick={onClose} aria-label="Close">
          ×
        </button>
      </header>
      <dl>
        {Object.entries(settings).map(([k, v]) => (
          <div key={k}>
            <dt>{k.replace(/_/g, ' ')}</dt>
            <dd>{typeof v === 'object' ? Object.entries(v as Record<string, unknown>).map(([a, b]) => `${a} ${b}`).join(' · ') : String(v)}</dd>
          </div>
        ))}
      </dl>
      <small>Configured centrally (H8BB_* environment overrides). Read-only here.</small>
    </div>
  );
}

export function H8BosBtl() {
  const [symbol, setSymbol] = useState(urlSymbol);
  const [filter, setFilter] = useState<AlertKind | null>(null);
  const [alertsOn, setAlertsOn] = useState(true);
  const [showSettings, setShowSettings] = useState(false);
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  const seen = useRef<Map<string, string> | null>(null);

  const summary = usePollingAsync(h8BosBtlApi.summary, [], { intervalMs: 10000 });
  const data = summary.data;

  useEffect(() => {
    if (!symbol && data?.alerts.length) {
      setSymbol(data.alerts[0].symbol);
      writeUrlSymbol(data.alerts[0].symbol);
    }
  }, [symbol, data]);

  useEffect(() => {
    if (!data) return;
    const sig = (a: (typeof data.alerts)[number]) => `${a.kind}|${a.analysis_id ?? ''}`;
    if (!seen.current) {
      seen.current = new Map(data.alerts.map((a) => [a.symbol, sig(a)]));
      return;
    }
    const prev = seen.current;
    const added = data.alerts.filter((a) => a.kind !== 'MONITORING' && prev.get(a.symbol) !== sig(a)).map((a) => a.symbol);
    data.alerts.forEach((a) => prev.set(a.symbol, sig(a)));
    if (added.length) setFresh((s) => new Set([...s, ...added]));
  }, [data]);

  const loader = useCallback(() => h8BosBtlApi.latest(symbol), [symbol]);
  const detail = usePollingAsync(loader, [loader], { enabled: !!symbol, intervalMs: 15000 });
  const d = detail.data?.symbol === symbol ? detail.data : null;

  const select = (s: string) => {
    setSymbol(s);
    writeUrlSymbol(s);
    setFresh((prev) => {
      if (!prev.has(s)) return prev;
      const next = new Set(prev);
      next.delete(s);
      return next;
    });
  };

  const alerts = useMemo(() => (data?.alerts ?? []).filter((a) => !filter || a.kind === filter), [data, filter]);
  const meta = data?.meta;
  const live = meta && !meta.stale;
  const refreshing = summary.refreshing || detail.refreshing || summary.loading || detail.loading;

  return (
    <div className="h8b-page">
      <div className="h8b-head">
        <div>
          <h1>
            H8 BOS &amp; BTL Intelligence
            <span className={`h8b-live${live ? '' : ' is-stale'}`}>
              {live ? 'AUTONOMOUS • LIVE' : meta ? `STALE • ${(meta.stale_reason ?? '').replace(/_/g, ' ')}` : 'CONNECTING'}
            </span>
          </h1>
          <p>
            Multi-timeframe structural analysis with Weekly Fractal + SCH (W), H8 structure, H1 validation and M30 confirmation.
            {meta?.last_cycle_at && <span className="h8b-muted"> Last cycle {fmtUtc(meta.last_cycle_at)}.</span>}
          </p>
        </div>
        <div className="h8b-actions">
          <select value={symbol} onChange={(e) => select(e.target.value)} aria-label="Symbol">
            {!symbol && <option value="">All Symbols</option>}
            {[...(data?.alerts ?? [])]
              .sort((a, b) => a.symbol.localeCompare(b.symbol))
              .map((a) => (
                <option key={a.symbol} value={a.symbol}>
                  {a.symbol}
                </option>
              ))}
          </select>
          <button type="button" className={alertsOn ? 'h8b-primary' : ''} onClick={() => setAlertsOn((v) => !v)} title="Show NEW markers for incoming alerts">
            {alertsOn ? <Bell size={15} /> : <BellOff size={15} />}
            Alerts {alertsOn ? 'ON' : 'OFF'}
          </button>
          <div className="h8b-pop-anchor">
            <button type="button" onClick={() => setShowSettings((v) => !v)} aria-label="Detection thresholds">
              <Settings size={15} />
            </button>
            {showSettings && meta && <SettingsPopover settings={meta.h8bb_settings} onClose={() => setShowSettings(false)} />}
          </div>
          <button
            type="button"
            onClick={() => {
              summary.refresh();
              detail.refresh();
            }}
            aria-label="Reload latest analysis"
            title="Reload the latest published analysis"
          >
            <RefreshCw size={15} className={refreshing ? 'h8b-spin' : ''} />
          </button>
        </div>
      </div>

      {summary.error && !data && <div className="h8b-error">Unable to load H8 BOS &amp; BTL analysis: {summary.error}</div>}
      {data && <SummaryCards data={data} filter={filter} onFilter={setFilter} />}
      {data && <AlertStrip alerts={alerts} selected={symbol} fresh={alertsOn ? fresh : new Set()} onSelect={select} />}

      <div className="h8b-workspace">
        {d && d.available ? (
          <>
            <div className="h8b-charts">
              {(['W', 'H8', 'H1', 'M30'] as ChartTf[]).map((tf) => (
                <ChartCard key={tf} tf={tf} d={d} />
              ))}
            </div>
            <AnalysisPanel key={d.symbol} d={d} />
          </>
        ) : (
          <div className="h8b-empty">
            {detail.error
              ? `Unable to load ${symbol}: ${detail.error}`
              : d && !d.available
                ? `${d.symbol}: ${d.reason}`
                : symbol
                  ? `Loading ${symbol} analysis…`
                  : 'Waiting for the first scanner cycle…'}
          </div>
        )}
      </div>
    </div>
  );
}

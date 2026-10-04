import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { AlertTriangle, Maximize2, Star, X } from 'lucide-react';
import { usePollingAsync } from '../../market-intelligence/hooks/useMarketIntelligence';
import { marketScannerApi } from '../api';
import { CandleChart } from './CandleChart';
import { InstrumentIcon } from './InstrumentIcon';
import { ChannelPill, ScoreBadge, StatusPill, VolatilityGlyph } from './ScannerTable';
import { ageText, fmtPct, fmtPrice, fmtSigned, pipSize, priceDigits, tone } from '../format';
import type { ChartTimeframe, ScannerInstrument, ScannerMeta, ScannerRow } from '../types';

const TABS = ['Overview', 'Structure', 'Channel', 'Strength', 'Analysis'] as const;
type Tab = (typeof TABS)[number];
const CHART_TFS: ChartTimeframe[] = ['M5', 'M15', 'H1', 'H8', 'D1', 'W', 'MN'];
const STRENGTH_TFS = ['YTD', 'Q', 'MN', 'W', 'D1', 'H8', 'H1', 'M15', 'M5', 'M1'];
const COMPONENT_LABELS: Record<string, string> = {
  strength: 'Strength differential',
  structure: 'Market structure',
  channel: 'Channel position',
  volatility: 'Volatility regime',
  alignment: 'Timeframe alignment',
};

function Info({ label, children, cls = '' }: { label: string; children: ReactNode; cls?: string }) {
  return (
    <div className={`ms-info ${cls}`}>
      <span>{label}</span>
      <strong>{children}</strong>
    </div>
  );
}

function spreadPips(row: ScannerRow) {
  if (row.spread_points == null || row.digits == null) return null;
  return (row.spread_points * 10 ** -row.digits) / pipSize(row);
}

function ChartBlock({
  inst,
  timeframe,
  onTimeframe,
  withChannel = false,
}: {
  inst: ScannerRow;
  timeframe: ChartTimeframe;
  onTimeframe: (tf: ChartTimeframe) => void;
  withChannel?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const loader = useCallback(() => marketScannerApi.candles(inst.symbol, timeframe, 120), [inst.symbol, timeframe]);
  const candles = usePollingAsync(loader, [loader], { intervalMs: 30000 });
  const list = candles.data?.symbol === inst.symbol && candles.data.timeframe === timeframe ? candles.data.candles : [];
  const digits = priceDigits(inst);

  useEffect(() => {
    if (!expanded) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setExpanded(false);
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [expanded]);

  const body = (h: number) =>
    candles.loading && !list.length ? (
      <div className="ms-chart-empty" style={{ height: h }}>
        Loading {timeframe} candles…
      </div>
    ) : !list.length ? (
      <div className="ms-chart-empty" style={{ height: h }}>
        {candles.error ? 'Candle history unavailable' : `No closed ${timeframe} candles stored for ${inst.symbol}`}
      </div>
    ) : (
      <CandleChart
        candles={list}
        timeframe={timeframe}
        digits={digits}
        lastPrice={inst.price}
        channel={withChannel ? inst.channel : null}
        height={h}
      />
    );

  const toolbar = (
    <div className="ms-chart-toolbar">
      <div className="ms-tf-group" role="group" aria-label="Chart timeframe">
        {CHART_TFS.map((tf) => (
          <button key={tf} className={tf === timeframe ? 'is-active' : ''} onClick={() => onTimeframe(tf)}>
            {tf}
          </button>
        ))}
      </div>
      <button className="ms-icon-btn" aria-label={expanded ? 'Close expanded chart' : 'Expand chart'} onClick={() => setExpanded(!expanded)}>
        {expanded ? <X size={15} /> : <Maximize2 size={15} />}
      </button>
    </div>
  );

  return (
    <>
      <div className="ms-chart-block">
        {toolbar}
        {body(190)}
      </div>
      {expanded ? (
        <div className="ms-chart-modal" role="dialog" aria-label={`${inst.symbol} ${timeframe} chart`} onClick={() => setExpanded(false)}>
          <div className="ms-chart-modal-inner" onClick={(e) => e.stopPropagation()}>
            <header>
              <strong>
                {inst.symbol} · {timeframe}
              </strong>
              <span>Closed candles · latest quote marked on price axis</span>
            </header>
            {toolbar}
            {body(Math.min(560, window.innerHeight - 200))}
          </div>
        </div>
      ) : null}
    </>
  );
}

function OverviewTab({ inst, d1Trend }: { inst: ScannerInstrument; d1Trend: string }) {
  const digits = priceDigits(inst);
  const spread = spreadPips(inst);
  const atrPips = inst.volatility?.atr != null && inst.base !== 'XAU' ? inst.volatility.atr / pipSize(inst) : null;
  const s = inst.strength;
  return (
    <>
      <h3 className="ms-panel-h3">Key Information (Autonomous Analysis)</h3>
      <div className="ms-info-grid">
        <Info label="Current Price">{fmtPrice(inst.price, digits)}</Info>
        <Info label="24h Change" cls={tone(inst.change_24h_pct)}>
          {fmtPct(inst.change_24h_pct)}
        </Info>
        <Info label={inst.day_range_basis === 'LAST_CLOSED_D1' ? 'Daily Range (last D1)' : 'Daily Range'}>
          {inst.day_high != null && inst.day_low != null
            ? `${fmtPrice(inst.day_low, digits)} – ${fmtPrice(inst.day_high, digits)}`
            : '—'}
        </Info>
        <Info label="ATR(14)">
          {inst.volatility?.atr != null ? `${fmtPrice(inst.volatility.atr, digits)}${atrPips != null ? ` (${atrPips.toFixed(1)} pips)` : ''}` : '—'}
        </Info>
        <Info label="Session">{inst.session ?? '—'}</Info>
        <Info label="Spread">{spread != null ? `${spread.toFixed(1)} pips` : 'No live quote'}</Info>
        <Info label="Trend (D1)" cls={d1Trend === 'Bullish' ? 'up' : d1Trend === 'Bearish' ? 'down' : ''}>
          {d1Trend}
        </Info>
        <Info label="Channel">
          <ChannelPill channel={inst.channel} />
        </Info>
        <Info label="Strength">
          {s?.differential != null
            ? `${inst.base} ${s.base_score?.toFixed(0)} / ${inst.quote} ${s.quote_score?.toFixed(0)}`
            : s?.quote_score != null
              ? `${inst.quote} ${s.quote_score.toFixed(0)}/100`
              : '—'}
        </Info>
        <Info label="Volatility">
          <span className="ms-vol">
            <VolatilityGlyph k={inst.volatility?.key} />
            {inst.volatility?.label ?? '—'}
          </span>
        </Info>
        <Info label="Status">
          <StatusPill status={inst.status} />
        </Info>
        <Info label="Score">
          <span className="ms-score-inline">
            <ScoreBadge row={inst} />
            <small>/100</small>
          </span>
        </Info>
      </div>
      <h3 className="ms-panel-h3">Primary Reasons</h3>
      <ul className="ms-reason-list">
        {inst.reasons.map((r) => (
          <li key={r}>{r}</li>
        ))}
      </ul>
    </>
  );
}

function StructureTab({ inst }: { inst: ScannerInstrument }) {
  const digits = priceDigits(inst);
  const st = inst.structure;
  return (
    <>
      <h3 className="ms-panel-h3">Market structure by timeframe</h3>
      <table className="ms-mini-table">
        <thead>
          <tr>
            <th>TF</th>
            <th>Structure</th>
            <th className="num">Swing high</th>
            <th className="num">Swing low</th>
          </tr>
        </thead>
        <tbody>
          {(inst.structures ?? []).map((s) => (
            <tr key={s.timeframe} className={s.timeframe === st?.timeframe ? 'is-primary' : ''}>
              <td>{s.timeframe}</td>
              <td className={s.key === 'BULLISH' ? 'up' : s.key === 'BEARISH' ? 'down' : ''}>
                {s.label}
                {s.event ? <small>{s.event.label}</small> : null}
              </td>
              <td className="num">{fmtPrice(s.swing_high, digits)}</td>
              <td className="num">{fmtPrice(s.swing_low, digits)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="ms-note">
        Fractal swings confirmed by two closed bars each side. Higher highs and higher lows classify as bullish, lower highs and
        lower lows as bearish, mixed swings as range. Primary timeframe: <strong>{st?.timeframe ?? '—'}</strong>
        {st?.agrees_with_strength === true
          ? ' — structure agrees with the strength differential.'
          : st?.agrees_with_strength === false
            ? ' — structure diverges from the strength differential.'
            : '.'}
      </p>
    </>
  );
}

function ChannelTab({ inst, timeframe, onTimeframe }: { inst: ScannerInstrument; timeframe: ChartTimeframe; onTimeframe: (tf: ChartTimeframe) => void }) {
  const ch = inst.channel;
  const digits = priceDigits(inst);
  const pos = ch?.position;
  return (
    <>
      <ChartBlock inst={inst} timeframe={timeframe} onTimeframe={onTimeframe} withChannel />
      {timeframe !== 'D1' ? <p className="ms-note">Switch to D1 to overlay the regression channel.</p> : null}
      <h3 className="ms-panel-h3">Regression channel (D1, {ch?.period ?? 50} bars, ±2σ)</h3>
      {ch && ch.key !== 'INSUFFICIENT' ? (
        <>
          <div className="ms-gauge" aria-label="Channel position">
            <span className="ms-gauge-track">
              <i style={{ left: `${Math.max(0, Math.min(100, (pos ?? 0.5) * 100))}%` }} />
            </span>
            <span className="ms-gauge-labels">
              <small>Lower</small>
              <small>Mid</small>
              <small>Upper</small>
            </span>
          </div>
          <div className="ms-info-grid is-3">
            <Info label="Upper">{fmtPrice(ch.upper, digits)}</Info>
            <Info label="Mid">{fmtPrice(ch.mid, digits)}</Info>
            <Info label="Lower">{fmtPrice(ch.lower, digits)}</Info>
            <Info label="Position">{pos != null ? `${(pos * 100).toFixed(0)}%` : '—'}</Info>
            <Info label="Direction">{ch.direction ? ch.direction[0] + ch.direction.slice(1).toLowerCase() : '—'}</Info>
            <Info label="Slope / bar">{ch.slope_pct_per_bar != null ? `${fmtSigned(ch.slope_pct_per_bar, 3)}%` : '—'}</Info>
          </div>
        </>
      ) : (
        <p className="ms-note">Insufficient D1 history for the regression channel.</p>
      )}
    </>
  );
}

function StrengthTab({ inst }: { inst: ScannerInstrument }) {
  const s = inst.strength;
  const tfs = inst.strength_timeframes;
  const max = Math.max(10, ...Object.values(tfs ?? {}).map((v) => Math.abs(v)));
  return (
    <>
      <h3 className="ms-panel-h3">Currency strength (0–100)</h3>
      <div className="ms-strength-pair">
        {[
          { c: inst.base, v: s?.base_score, cls: s?.base_class },
          { c: inst.quote, v: s?.quote_score, cls: s?.quote_class },
        ].map((x) => (
          <div key={x.c} className="ms-strength-ccy">
            <span>{x.c}</span>
            <span className="ms-bar">
              <i style={{ width: `${x.v ?? 0}%` }} />
            </span>
            <strong>{x.v != null ? x.v.toFixed(1) : inst.base === 'XAU' && x.c === 'XAU' ? 'n/a' : '—'}</strong>
          </div>
        ))}
      </div>
      {s?.differential != null ? (
        <div className="ms-info-grid is-3">
          <Info label="Differential" cls={tone(s.differential)}>
            {fmtSigned(s.differential)}
          </Info>
          <Info label="Relationship">{s.relationship?.label ?? '—'}</Info>
          <Info label="Alignment">{s.alignment ? `${s.alignment.aligned}/${s.alignment.total} (${s.alignment.label})` : '—'}</Info>
        </div>
      ) : (
        <p className="ms-note">XAU is not part of the 8-currency strength basket; only the {inst.quote} side is measured.</p>
      )}
      {tfs ? (
        <>
          <h3 className="ms-panel-h3">Differential by timeframe</h3>
          <div className="ms-tf-bars">
            {STRENGTH_TFS.filter((tf) => tfs[tf] !== undefined).map((tf) => {
              const v = tfs[tf];
              const w = (Math.abs(v) / max) * 50;
              return (
                <div key={tf} className="ms-tf-bar">
                  <span>{tf}</span>
                  <span className="ms-tf-track">
                    <i className={v >= 0 ? 'is-pos' : 'is-neg'} style={v >= 0 ? { left: '50%', width: `${w}%` } : { right: '50%', width: `${w}%` }} />
                    <b />
                  </span>
                  <strong className={tone(v)}>{fmtSigned(v)}</strong>
                </div>
              );
            })}
          </div>
        </>
      ) : null}
    </>
  );
}

function AnalysisTab({ inst, meta }: { inst: ScannerInstrument; meta: ScannerMeta | null }) {
  const weights = meta?.settings.weights ?? {};
  return (
    <>
      <h3 className="ms-panel-h3">Inspection score breakdown</h3>
      <div className="ms-components">
        {Object.entries(inst.score_components ?? {}).map(([k, v]) => (
          <div key={k} className={`ms-component ${v === null ? 'is-na' : ''}`}>
            <span>
              {COMPONENT_LABELS[k] ?? k}
              <small>weight {weights[k] ?? '—'}</small>
            </span>
            <span className="ms-bar">
              <i style={{ width: `${v ?? 0}%` }} />
            </span>
            <strong>{v === null ? 'n/a' : v}</strong>
          </div>
        ))}
      </div>
      <p className="ms-note">
        Unavailable components are excluded and the remaining weights renormalized. Status bands:{' '}
        {meta?.settings.status
          .filter((s) => s.key !== 'NEUTRAL')
          .map((s) => `${s.label} ≥ ${s.min}`)
          .join(' · ')}
        .
      </p>
      <h3 className="ms-panel-h3">All reasons</h3>
      <ul className="ms-reason-list">
        {inst.reasons.map((r) => (
          <li key={r}>{r}</li>
        ))}
      </ul>
      <p className="ms-note ms-note--strong">
        Inspection priority only — the scanner never issues trade direction or executes trades.
      </p>
    </>
  );
}

export function InstrumentPanel({
  row,
  meta,
  starred,
  onToggleStar,
  enabled,
}: {
  row: ScannerRow;
  meta: ScannerMeta | null;
  starred: boolean;
  onToggleStar: () => void;
  enabled: boolean;
}) {
  const [tab, setTab] = useState<Tab>('Overview');
  const [timeframe, setTimeframe] = useState<ChartTimeframe>('H1');
  const [channelTf, setChannelTf] = useState<ChartTimeframe>('D1');
  const loader = useCallback(() => marketScannerApi.instrument(row.symbol), [row.symbol]);
  const detail = usePollingAsync(loader, [loader], { enabled, intervalMs: 2000 });
  const fetched = detail.data?.instrument.symbol === row.symbol ? detail.data.instrument : null;
  const inst: ScannerInstrument = {
    ...row,
    structures: fetched?.structures,
    strength_timeframes: fetched?.strength_timeframes,
  };
  const digits = priceDigits(inst);
  const d1 = inst.structures?.find((s) => s.timeframe === 'D1');
  const excluded = inst.status.key === 'EXCLUDED';

  return (
    <aside className="ms-card ms-panel" aria-label={`${inst.symbol} details`}>
      <header className="ms-panel-head">
        <button className={`ms-star ${starred ? 'is-on' : ''}`} onClick={onToggleStar} aria-label={starred ? 'Unstar' : 'Star'}>
          <Star size={16} />
        </button>
        <InstrumentIcon base={inst.base} quote={inst.quote} size="lg" />
        <div className="ms-panel-title">
          <strong>{inst.symbol}</strong>
          <span>{inst.name}</span>
        </div>
        <div className="ms-panel-price">
          <strong>{fmtPrice(inst.price, digits)}</strong>
          <span className={tone(inst.change_24h)}>
            {inst.change_24h != null ? `${fmtSigned(inst.change_24h, digits)} (${fmtPct(inst.change_24h_pct)})` : '—'}
          </span>
          <small>{inst.price_live ? 'Live quote' : inst.price_at ? `Last close · ${ageText(inst.price_at)}` : ''}</small>
        </div>
      </header>

      <div className="ms-panel-tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? 'is-active' : ''} onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </div>

      <div className="ms-panel-body">
        {excluded ? (
          <div className="ms-excluded-note">
            <AlertTriangle size={18} aria-hidden />
            <div>
              <strong>Excluded from this cycle</strong>
              <span>{inst.excluded_reason ?? inst.reasons[0]}</span>
            </div>
          </div>
        ) : tab === 'Overview' ? (
          <>
            <ChartBlock inst={inst} timeframe={timeframe} onTimeframe={setTimeframe} />
            <OverviewTab inst={inst} d1Trend={d1?.label ?? '—'} />
          </>
        ) : tab === 'Structure' ? (
          <StructureTab inst={inst} />
        ) : tab === 'Channel' ? (
          <ChannelTab inst={inst} timeframe={channelTf} onTimeframe={setChannelTf} />
        ) : tab === 'Strength' ? (
          <StrengthTab inst={inst} />
        ) : (
          <AnalysisTab inst={inst} meta={meta} />
        )}
        {excluded ? <p className="ms-note">The instrument returns automatically once enough closed history is available.</p> : null}
      </div>
      {detail.error && !detail.data ? <p className="ms-note ms-panel-err">Detail unavailable: {detail.error}</p> : null}
    </aside>
  );
}

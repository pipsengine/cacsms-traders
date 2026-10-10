import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { ArrowRight, CalendarClock, ChevronDown, CircleCheck, Moon, RefreshCw, Sun, Sunrise } from 'lucide-react';
import { InstrumentIcon } from '../../market-scanner/components/InstrumentIcon';
import { fmtPrice } from '../../market-scanner/format';
import type { Annotation, OutlookRow, RunSummary, Schedule, SessionPlan, VCandle } from '../types';

export const TFS = ['Y', 'YTD', 'HY', 'Q', 'MN', 'W', 'D1', 'H8', 'H1', 'M30'] as const;
export const GOLD_TFS = ['MN', 'W', 'D1', 'H8', 'H1', 'M30', 'M15', 'M5'] as const;
export type OutlookTf = (typeof TFS)[number] | 'M15' | 'M5';
export const MINI_TFS: OutlookTf[] = ['Y', 'YTD', 'HY', 'Q', 'MN', 'W', 'D1', 'H8', 'H1'];
export const CANDLE_LIMIT: Record<OutlookTf, number> = { Y: 40, YTD: 220, HY: 40, Q: 48, MN: 120, W: 120, D1: 110, H8: 120, H1: 140, M30: 140, M15: 160, M5: 180 };
/** History loaded for zooming out / panning back; the chart opens on CANDLE_LIMIT bars. */
export const HISTORY_LIMIT: Record<OutlookTf, number> = { Y: 40, YTD: 220, HY: 40, Q: 48, MN: 240, W: 260, D1: 400, H8: 360, H1: 420, M30: 420, M15: 480, M5: 480 };

export const dirWord = (d?: string | null) => (d === 'BULLISH' ? 'Bullish' : d === 'BEARISH' ? 'Bearish' : d === 'RANGE' ? 'Range' : '—');
export const dirTone = (d?: string | null) => (d === 'BULLISH' || d === 'Bullish' ? 'is-bull' : d === 'BEARISH' || d === 'Bearish' ? 'is-bear' : 'is-range');
export const pct = (v: number | null | undefined, dp = 0) => (v == null ? '—' : `${v.toFixed(dp)}%`);
export const px = (v: number | null | undefined, dp: number) => fmtPrice(v ?? null, dp);

export function dayLabel(iso: string | null | undefined, opts: Intl.DateTimeFormatOptions = { day: '2-digit', month: 'short', year: 'numeric' }) {
  if (!iso) return '—';
  const raw = iso.includes('|') ? iso.split('|')[1] : iso;
  const d = raw.length === 10 ? new Date(`${raw}T12:00:00Z`) : new Date(raw);
  return new Intl.DateTimeFormat('en-GB', { ...opts, timeZone: 'UTC' }).format(d);
}

export function useNow(intervalMs = 1000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), intervalMs);
    return () => window.clearInterval(id);
  }, [intervalMs]);
  return now;
}

function countdown(target: string | undefined, now: number, withDays = false) {
  if (!target) return '—';
  const total = Math.max(0, Math.floor((Date.parse(target) - now) / 1000));
  const h = withDays ? Math.floor((total % 86400) / 3600) : Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const clock = `${h}h ${String(m).padStart(2, '0')}m ${String(total % 60).padStart(2, '0')}s`;
  return withDays ? `${Math.floor(total / 86400)}d ${clock}` : clock;
}

const RUN_STATE: Record<string, { label: string; tone: string }> = {
  PUBLISHED: { label: 'Completed', tone: 'is-green' },
  MONITORING: { label: 'Completed', tone: 'is-green' },
  EVALUATING: { label: 'Evaluating', tone: 'is-blue' },
  ARCHIVED: { label: 'Archived', tone: 'is-gray' },
  RETRY: { label: 'Retrying', tone: 'is-amber' },
  INSUFFICIENT_DATA: { label: 'Awaiting Data', tone: 'is-amber' },
  FAILED: { label: 'Failed', tone: 'is-red' },
  MISSED: { label: 'Missed', tone: 'is-red' },
  SCHEDULED: { label: 'Scheduled', tone: 'is-blue' },
};
export const runState = (s?: string | null) => RUN_STATE[s ?? ''] ?? { label: s ? 'Running' : 'Not started', tone: s ? 'is-blue' : 'is-gray' };

const RERUN_STATES = new Set(['INSUFFICIENT_DATA', 'RETRY', 'FAILED', 'SCHEDULED']);

export function StatusCluster({ run, current, schedule, onReload, onRunNow, runBusy, busy, title = 'Daily Analysis (Market Close)', withDays = false }: { run: RunSummary | null; current: RunSummary | null; schedule: Schedule | null; onReload: () => void; onRunNow?: () => void; runBusy?: boolean; busy: boolean; title?: string; withDays?: boolean }) {
  const now = useNow();
  const shown = current ?? run;
  const st = runState(shown?.state);
  const stamp = shown?.published_at ?? shown?.started_at ?? shown?.close_at;
  const canRun = Boolean(onRunNow && current && RERUN_STATES.has(current.state ?? ''));
  return (
    <div className="mao-status">
      <div className="mao-status-card">
        <CalendarClock size={18} />
        <div>
          <b>{title}</b>
          <small>
            {shown ? `${dayLabel(shown.analysis_date, { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' })} • ${stamp ? new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false, timeZoneName: 'short' }).format(new Date(stamp)) : '—'}` : 'No cycle yet'}
          </small>
        </div>
        <span className={`mao-chip ${st.tone}`} title={shown?.error ?? shown?.log.at(-1)?.message ?? undefined}>
          {st.label}
        </span>
      </div>
      <div className="mao-status-card is-next">
        <small>Next analysis in</small>
        <b>{countdown(schedule?.next_run_at, now, withDays)}</b>
      </div>
      {canRun ? (
        <button className="mao-run-btn" type="button" disabled={runBusy} onClick={onRunNow} title="Re-run today’s daily analysis with the latest market data">
          {runBusy ? 'Analysing…' : 'Run analysis now'}
        </button>
      ) : null}
      <button className="mao-icon-btn" aria-label="Reload outlook" title="Reload latest published outlook" onClick={onReload}>
        <RefreshCw size={16} className={busy ? 'is-spin' : ''} />
      </button>
    </div>
  );
}

const SESSION_ICON = { ASIAN: <Moon size={13} />, LONDON: <Sunrise size={13} />, NEW_YORK: <Sun size={13} /> };

export function SessionCards({ plans, schedule, captions }: { plans: SessionPlan[] | null; schedule: Schedule | null; captions?: Partial<Record<string, string>> }) {
  const now = useNow(30000);
  const windows = plans ?? schedule?.sessions.map((w) => ({ ...w, badge: '', bias: null, plan: '' })) ?? [];
  return (
    <div className="mao-sessions">
      {windows.map((w) => {
        const live = Date.parse(w.start) <= now && now < Date.parse(w.end);
        const done = now >= Date.parse(w.end);
        return (
          <div key={w.key} className={`mao-session ${live ? 'is-live' : ''} ${w.key === 'ASIAN' ? 'is-first' : ''}`} title={w.plan || undefined}>
            <b>
              {SESSION_ICON[w.key]} {w.label}
            </b>
            <span>
              <small>{captions?.[w.key] ?? (w.badge || (done ? 'Closed' : live ? 'Live' : 'Upcoming'))}</small>
              {w.bias ? <em className={dirTone(w.bias)}>{w.bias}</em> : null}
              <ArrowRight size={12} />
            </span>
          </div>
        );
      })}
    </div>
  );
}

export function qualifiedByConfidence(rows: OutlookRow[]) {
  return rows
    .filter((r) => r.qualified)
    .sort((a, b) => (b.confidence ?? -1) - (a.confidence ?? -1) || a.symbol.localeCompare(b.symbol));
}

export function SymbolPicker({ symbol, rows, onSelect, allowAll = false, label = 'Symbols with Opportunities' }: { symbol: string | null; rows: OutlookRow[]; onSelect: (s: string) => void; allowAll?: boolean; label?: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const opps = qualifiedByConfidence(rows);
  const others = allowAll ? rows.filter((r) => !r.qualified && r.status === 'PUBLISHED') : [];
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [open]);
  const item = (r: OutlookRow) => (
    <button key={r.symbol} role="option" aria-selected={r.symbol === symbol} className={r.symbol === symbol ? 'is-on' : ''} onClick={() => (onSelect(r.symbol), setOpen(false))}>
      <InstrumentIcon base={r.symbol.slice(0, 3)} quote={r.symbol.slice(3, 6)} size="sm" />
      <b>{r.symbol}</b>
      <span>{pct(r.confidence)}</span>
      <em className={`mao-dir ${dirTone(r.expected_direction)}`}>{dirWord(r.expected_direction)}</em>
    </button>
  );
  return (
    <div className="mao-picker" ref={ref}>
      <button className="mao-picker-btn" onClick={() => setOpen((v) => !v)} aria-haspopup="listbox" aria-expanded={open}>
        {symbol ? <InstrumentIcon base={symbol.slice(0, 3)} quote={symbol.slice(3, 6)} size="sm" /> : null}
        <b>{symbol ?? 'No opportunity'}</b>
        <ChevronDown size={15} />
      </button>
      {open ? (
        <div className="mao-picker-pop" role="listbox">
          <header>
            {label} <span>{opps.length}</span>
          </header>
          {opps.length ? opps.map(item) : <p className="mao-picker-empty">No qualified opportunities today</p>}
          {others.length ? (
            <>
              <header className="is-sub">Other analysed instruments (audit)</header>
              <div className="mao-picker-scroll">{others.map(item)}</div>
            </>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export function TfBar({ value, onChange, tfs = TFS }: { value: string; onChange: (t: OutlookTf) => void; tfs?: readonly OutlookTf[] }) {
  return (
    <div className="mao-tf" role="group" aria-label="Chart timeframe">
      {tfs.map((t) => (
        <button key={t} className={value === t ? 'is-on' : ''} aria-pressed={value === t} onClick={() => onChange(t)}>
          {t}
        </button>
      ))}
    </div>
  );
}

export function Kpi({ icon, tone, label, value, sub, bar, children }: { icon: ReactNode; tone: string; label: string; value?: ReactNode; sub?: ReactNode; bar?: number | null; children?: ReactNode }) {
  return (
    <section className={`mao-card mao-kpi ${tone}`}>
      <span className="mao-kpi-icon">{icon}</span>
      <div className="mao-kpi-body">
        <span className="mao-kpi-label">{label}</span>
        {value != null ? <strong>{value}</strong> : null}
        {bar != null ? (
          <span className="mao-bar">
            <i style={{ width: `${Math.max(0, Math.min(100, bar))}%` }} />
          </span>
        ) : null}
        {sub != null ? <small>{sub}</small> : null}
        {children}
      </div>
    </section>
  );
}

export function Card({ title, icon, extra, className = '', children }: { title: ReactNode; icon?: ReactNode; extra?: ReactNode; className?: string; children: ReactNode }) {
  return (
    <section className={`mao-card mao-panel ${className}`}>
      <header className="mao-panel-head">
        <h3>
          {icon}
          {title}
        </h3>
        {extra}
      </header>
      {children}
    </section>
  );
}

export function ProbBar({ value, tone }: { value: number; tone: string }) {
  return (
    <span className={`mao-prob ${tone}`}>
      <i style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </span>
  );
}

export function Chip({ tone, children, title }: { tone: string; children: ReactNode; title?: string }) {
  return (
    <span className={`mao-chip ${tone}`} title={title}>
      {children}
    </span>
  );
}

export function Check({ value }: { value: boolean | null }) {
  return value == null ? <span className="mao-dash">–</span> : value ? <span className="mao-yes">✓</span> : <span className="mao-no">✗</span>;
}

export const stepTone = (s: { done: boolean; unavailable?: boolean } | undefined) => (!s ? 'is-amber' : s.done ? 'is-green' : 'is-amber');
export const stepLabel = (s: { done: boolean; unavailable?: boolean } | undefined) => (!s ? 'Pending' : s.done ? 'Done' : s.unavailable ? 'Awaiting data' : 'Pending');

/** Tiny closed-candle chart for the multi-timeframe matrix and history rows (no axes). */
export function MiniCandles({ candles, channel, height = 64, tone = 'blue', className = '' }: { candles: VCandle[]; channel?: Annotation | null; height?: number; tone?: string; className?: string }) {
  const w = 160;
  const g = useMemo(() => {
    if (!candles.length) return null;
    let lo = Math.min(...candles.map((c) => c.l));
    let hi = Math.max(...candles.map((c) => c.h));
    const pad = (hi - lo) * 0.08 || hi * 0.001;
    lo -= pad;
    hi += pad;
    const step = w / candles.length;
    const t0 = Date.parse(candles[0].t);
    const t1 = Date.parse(candles[candles.length - 1].t);
    const xt = (t: string) => ((Date.parse(t) - t0) / ((t1 - t0) || 1)) * (w - step) + step / 2;
    return { lo, hi, step, x: (i: number) => step * (i + 0.5), y: (v: number) => 3 + ((hi - v) / (hi - lo)) * (height - 6), xt };
  }, [candles, height]);
  if (!g) return <div className={`mao-mini-empty ${className}`} style={{ height }}>No candles</div>;
  const bw = Math.max(1, g.step * 0.6);
  const L = channel?.lines;
  return (
    <svg className={`mao-mini ${className}`} viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="none" style={{ height }}>
      {L ? (
        <g className={`mao-mini-ch is-${tone}`}>
          <polygon points={`${g.xt(L.upper[0][0])},${g.y(L.upper[0][1])} ${g.xt(L.upper[1][0])},${g.y(L.upper[1][1])} ${g.xt(L.lower[1][0])},${g.y(L.lower[1][1])} ${g.xt(L.lower[0][0])},${g.y(L.lower[0][1])}`} />
          <line x1={g.xt(L.upper[0][0])} y1={g.y(L.upper[0][1])} x2={g.xt(L.upper[1][0])} y2={g.y(L.upper[1][1])} />
          <line x1={g.xt(L.lower[0][0])} y1={g.y(L.lower[0][1])} x2={g.xt(L.lower[1][0])} y2={g.y(L.lower[1][1])} />
        </g>
      ) : null}
      {candles.map((c, i) => (
        <g key={c.t} className={c.c >= c.o ? 'mst-up' : 'mst-down'}>
          <line x1={g.x(i)} x2={g.x(i)} y1={g.y(c.h)} y2={g.y(c.l)} />
          <rect x={g.x(i) - bw / 2} y={g.y(Math.max(c.o, c.c))} width={bw} height={Math.max(0.8, Math.abs(g.y(c.o) - g.y(c.c)))} />
        </g>
      ))}
    </svg>
  );
}

export function Spark({ values, tone }: { values: number[]; tone: string }) {
  if (values.length < 2) return <span className="mao-muted">—</span>;
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * 70},${18 - ((v - lo) / ((hi - lo) || 1)) * 16}`).join(' ');
  return (
    <svg className={`mao-spark ${tone}`} viewBox="0 0 70 20" width={70} height={20}>
      <polyline points={pts} />
    </svg>
  );
}

export function NoOpportunity({ rows, run }: { rows: OutlookRow[]; run: RunSummary | null }) {
  const watch = rows.filter((r) => r.status === 'PUBLISHED').sort((a, b) => (b.opportunity_score ?? 0) - (a.opportunity_score ?? 0)).slice(0, 6);
  return (
    <section className="mao-card mao-empty-state">
      <CircleCheck size={28} />
      <strong>No qualified opportunities today</strong>
      <p>
        {run ? `${run.symbols_published} instruments analysed at the ${dayLabel(run.analysis_date)} close; none met the probability, margin, data-quality and objective/invalidation thresholds.` : 'Awaiting the first published daily outlook.'}
      </p>
      {watch.length ? (
        <small>
          Closest candidates: {watch.map((r) => `${r.symbol} ${dirWord(r.expected_direction)} ${pct(r.confidence)}`).join(' · ')}
        </small>
      ) : null}
    </section>
  );
}

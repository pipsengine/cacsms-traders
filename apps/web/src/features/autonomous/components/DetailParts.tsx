import { useEffect, useState, type CSSProperties, type ReactNode } from 'react';
import { AlertTriangle, CircleCheck, Radio } from 'lucide-react';
import { InstrumentIcon } from '../../market-scanner/components/InstrumentIcon';
import { duration, pretty, utc, utcSeconds } from '../format';
import type { Transition } from '../types';

export function useNow(intervalMs = 1000) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), intervalMs);
    return () => window.clearInterval(t);
  }, [intervalMs]);
  return now;
}

export function Sym({ symbol }: { symbol: string }) {
  return (
    <span className="ae-sym">
      <InstrumentIcon base={symbol.slice(0, 3)} quote={symbol.slice(3, 6)} size="sm" />
      {symbol}
    </span>
  );
}

export type Kpi = { label: string; value: ReactNode; sub?: ReactNode; icon: ReactNode; color: string; subTone?: 'up' | 'down' | 'flat' };

export function KpiRow({ items }: { items: Kpi[] }) {
  return (
    <div className="ae-kpis" style={{ '--n': items.length } as CSSProperties}>
      {items.map((k) => (
        <div key={k.label} className="ae-kpi" style={{ '--kpi': k.color } as CSSProperties}>
          <span className="ae-kpi-icon" aria-hidden>
            {k.icon}
          </span>
          <div>
            <span>{k.label}</span>
            <b>{k.value}</b>
            {k.sub != null ? <small className={k.subTone ? `is-${k.subTone}` : ''}>{k.sub}</small> : null}
          </div>
        </div>
      ))}
    </div>
  );
}

export function Panel({
  title,
  extra,
  children,
  className = '',
}: {
  title: ReactNode;
  extra?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`ae-card ${className}`}>
      <header className="ae-card-head">
        <h3>{title}</h3>
        {extra}
      </header>
      {children}
    </section>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="ae-empty">{children}</div>;
}

/** Donut of the stage's own persisted counts; segments are the rows passed in. */
export function Donut({ total, label, rows, color }: { total: number; label: string; rows: { label: string; value: number; color: string }[]; color: string }) {
  const sum = rows.reduce((a, r) => a + r.value, 0);
  const R = 52;
  const C = 2 * Math.PI * R;
  let offset = 0;
  return (
    <div className="ae-donut-wrap">
      <svg viewBox="0 0 140 140" className="ae-donut" role="img" aria-label={`${total} ${label}`}>
        <circle cx="70" cy="70" r={R} className="ae-donut-track" />
        {sum > 0
          ? rows
              .filter((r) => r.value > 0)
              .map((r) => {
                const len = (r.value / sum) * C;
                const el = (
                  <circle
                    key={r.label}
                    cx="70"
                    cy="70"
                    r={R}
                    stroke={r.color}
                    strokeDasharray={`${len} ${C - len}`}
                    strokeDashoffset={-offset}
                    className="ae-donut-seg"
                  />
                );
                offset += len;
                return el;
              })
          : null}
        <text x="70" y="68" textAnchor="middle" className="ae-donut-n" style={{ fill: color }}>
          {total}
        </text>
        <text x="70" y="86" textAnchor="middle" className="ae-donut-l">
          {label}
        </text>
      </svg>
      <ul className="ae-donut-list">
        {rows.map((r) => (
          <li key={r.label}>
            <i style={{ background: r.color }} aria-hidden />
            <span>{r.label}</span>
            <b>{r.value}</b>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function CurrentOperation({
  title,
  badge,
  operation,
  progress,
  startedAt,
  nextStep,
  live,
  color,
  symbol,
}: {
  title: string;
  badge?: string | null;
  operation: string | null;
  progress?: number | null;
  startedAt?: string | null;
  nextStep?: string | null;
  live: boolean;
  color: string;
  symbol?: string | null;
}) {
  const now = useNow();
  return (
    <Panel
      title="Current Operation"
      extra={
        <span className={`ae-badge is-${live ? 'ok' : 'muted'}`}>
          <Radio size={11} /> {live ? 'Live' : 'Idle'}
        </span>
      }
    >
      <div className="ae-op" style={{ '--stage': color } as CSSProperties}>
        <div className="ae-op-title">
          {symbol ? <Sym symbol={symbol} /> : null}
          <strong>{title}</strong>
          {badge ? <span className="ae-tag">{badge}</span> : null}
        </div>
        <p>{operation ?? 'No operation recorded yet'}</p>
        {progress != null ? (
          <div className="ae-progress" aria-label={`Lifecycle progress ${progress}%`}>
            <span style={{ width: `${Math.max(0, Math.min(100, progress))}%` }} />
            <b>{progress}%</b>
          </div>
        ) : null}
        <dl className="ae-op-meta">
          <div>
            <dt>Start Time</dt>
            <dd>{startedAt ? `${utcSeconds(startedAt)} UTC` : '—'}</dd>
          </div>
          <div>
            <dt>Elapsed</dt>
            <dd>{duration(startedAt, now)}</dd>
          </div>
          <div className="is-wide">
            <dt>Next Step</dt>
            <dd>{nextStep ?? '—'}</dd>
          </div>
        </dl>
      </div>
    </Panel>
  );
}

export function DetectionsTable({ rows, digitsFor, empty }: { rows: Transition[]; digitsFor: (s: string) => number; empty: string }) {
  if (!rows.length) return <Empty>{empty}</Empty>;
  return (
    <div className="ae-table-wrap">
      <table className="ae-table">
        <thead>
          <tr>
            <th>Time</th>
            <th>Symbol</th>
            <th>TF</th>
            <th>Event</th>
            <th>Level</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((t) => {
            const lvl = t.evidence?.level ?? t.evidence?.close;
            return (
              <tr key={t.id} title={`${pretty(t.reason_code)}${t.detail ? ` — ${t.detail}` : ''}`}>
                <td>{utc(t.evidence_at, true)}</td>
                <td>{t.symbol ? <Sym symbol={t.symbol} /> : '—'}</td>
                <td>{t.timeframe ?? '—'}</td>
                <td>
                  <span className="ae-evt">{pretty(t.to_state)}</span>
                </td>
                <td className="ae-num">{typeof lvl === 'number' && t.symbol ? lvl.toFixed(digitsFor(t.symbol)) : '—'}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function Blockers({ blockers, warnings }: { blockers: string[]; warnings?: string[] }) {
  if (!blockers.length && !warnings?.length)
    return (
      <div className="ae-ok-note">
        <CircleCheck size={16} /> No blockers — this stage is progressing on backend evidence.
      </div>
    );
  return (
    <ul className="ae-blockers">
      {blockers.map((b) => (
        <li key={`b${b}`} className="is-bad">
          <AlertTriangle size={14} /> {b}
        </li>
      ))}
      {(warnings ?? []).map((w) => (
        <li key={`w${w}`} className="is-warn">
          <AlertTriangle size={14} /> {w}
        </li>
      ))}
    </ul>
  );
}

import type { ReactNode } from 'react';
import { CheckCircle2, Circle, CircleDot, XCircle } from 'lucide-react';
import { priceDigits } from '../../market-scanner/format';

export type Tone = 'is-green' | 'is-red' | 'is-amber' | 'is-blue' | 'is-rose' | 'is-purple' | 'is-gray';

export function Kpi({
  tone,
  icon,
  label,
  value,
  sub,
  bar,
}: {
  tone: Tone;
  icon: ReactNode;
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  bar?: number | null;
}) {
  return (
    <section className={`mst-card mtr-kpi ${tone}`}>
      <span className="mtr-kpi-icon">{icon}</span>
      <div>
        <span className="mtr-kpi-label">{label}</span>
        <strong>{value}</strong>
        {bar != null ? (
          <span className="mtr-bar">
            <i style={{ width: `${Math.max(0, Math.min(100, bar))}%` }} />
          </span>
        ) : null}
        {sub != null ? <small className="mtr-kpi-note">{sub}</small> : null}
      </div>
    </section>
  );
}

export function Panel({
  title,
  icon,
  extra,
  className = '',
  children,
}: {
  title: ReactNode;
  icon?: ReactNode;
  extra?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section className={`mst-card mst-panel msx-panel ${className}`}>
      <header className="mtr-panel-head">
        <h3>
          {icon} {title}
        </h3>
        {extra}
      </header>
      {children}
    </section>
  );
}

export function Kv({ label, children, tone }: { label: ReactNode; children: ReactNode; tone?: string }) {
  return (
    <div className="mtr-kv-row">
      <dt>{label}</dt>
      <dd className={tone}>{children}</dd>
    </div>
  );
}

export function Pill({ tone, children, title }: { tone: string; children: ReactNode; title?: string }) {
  return (
    <span className={`mtr-status ${tone}`} title={title}>
      {children}
    </span>
  );
}

export function Blocking({ loading, error, title, reason }: { loading?: string; error?: string; title?: string; reason?: string }) {
  return (
    <section className={`mst-card mst-blocking ${error ? 'is-error' : ''}`}>
      {title ? (
        <>
          <strong>{title}</strong>
          <span>{reason ?? error}</span>
        </>
      ) : (
        <>
          <span className="mst-spinner" aria-hidden />
          {loading}
        </>
      )}
    </section>
  );
}

export type Step = { label: string; description?: string; done: boolean; current?: boolean; at?: string | null };

export function Lifecycle({ steps, horizontal = false }: { steps: Step[]; horizontal?: boolean }) {
  const hasCurrent = steps.some((s) => s.current);
  const next = steps.findIndex((s) => !s.done);
  return (
    <ol className={`msx-steps ${horizontal ? 'is-row' : ''}`}>
      {steps.map((s, i) => {
        const state = s.current ? 'is-now' : s.done ? 'is-done' : !hasCurrent && i === next ? 'is-next' : '';
        return (
          <li key={s.label} className={state}>
            <span className="msx-step-dot">{s.done ? <CheckCircle2 size={15} /> : s.current ? <CircleDot size={15} /> : <Circle size={15} />}</span>
            <div>
              <b>{s.label}</b>
              {s.description ? <small>{s.description}</small> : null}
              {s.at ? <time dateTime={s.at}>{stamp(s.at)}</time> : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

export function EvidenceList({ items }: { items: { label: string; met: boolean }[] }) {
  return (
    <ul className="msx-evidence">
      {items.map((e) => (
        <li key={e.label} className={e.met ? 'is-met' : ''}>
          {e.met ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
          <span>{e.label}</span>
        </li>
      ))}
    </ul>
  );
}

export function Meter({ value, tone }: { value: number | null | undefined; tone?: string }) {
  const v = value == null ? 0 : Math.max(0, Math.min(100, value));
  const t = tone ?? (v >= 60 ? 'is-green' : v >= 40 ? 'is-amber' : 'is-red');
  return (
    <span className={`mtr-meter ${value == null ? '' : t}`}>
      <i style={{ width: `${v}%` }} />
    </span>
  );
}

export function stamp(iso: string | null | undefined, withTime = true) {
  if (!iso) return '—';
  const d = new Date(iso);
  const day = new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', year: withTime ? undefined : 'numeric' }).format(d);
  if (!withTime) return day;
  return `${day} ${new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false }).format(d)}`;
}

export function eventTime(iso: string, tf: string) {
  return tf === 'W' || tf === 'D1' || tf === 'MN' ? stamp(iso, false) : stamp(iso);
}

export function rowDigits(r: { digits?: number | null; symbol: string; quote: string }) {
  return priceDigits({ digits: r.digits ?? undefined, symbol: r.symbol, quote: r.quote });
}

export const statusTone = (k?: string | null) =>
  k === 'CONFIRMED' || k === 'COMPLETED' || k === 'ACTIVE' || k === 'IN_ZONE'
    ? 'is-green'
    : k === 'RETESTING' || k === 'TESTING' || k === 'DEVELOPING' || k === 'MONITORING' || k === 'PROVISIONAL' || k === 'FORMING'
      ? 'is-blue'
      : k === 'CANDIDATE' || k === 'PENDING' || k === 'WATCHING' || k === 'INSIDE'
        ? 'is-amber'
        : k === 'FAILED' || k === 'INVALID' || k === 'INVALIDATED'
          ? 'is-red'
          : 'is-gray';

export const regimeTone = (r?: string | null) =>
  r === 'BULLISH' || r === 'UPTREND' ? 'is-bull' : r === 'BEARISH' || r === 'DOWNTREND' ? 'is-bear' : r === 'RANGING' ? 'is-range' : 'is-neutral';

export const titleCase = (s?: string | null) => (s ? s.charAt(0) + s.slice(1).toLowerCase() : '—');

export function TfSwitch<T extends string>({
  tfs,
  value,
  onChange,
  label,
}: {
  tfs: readonly T[];
  value: T;
  onChange: (t: T) => void;
  label: string;
}) {
  return (
    <div className="mtr-tf" role="group" aria-label={label}>
      {tfs.map((x) => (
        <button key={x} className={value === x ? 'is-on' : ''} onClick={() => onChange(x)} aria-pressed={value === x}>
          {x}
        </button>
      ))}
    </div>
  );
}

import { useRef, useState, type ReactNode } from 'react';
import { Activity, ChevronLeft, ChevronRight, Eye, GitBranch, Layers, Radar, Zap } from 'lucide-react';
import { InstrumentIcon } from '../../market-scanner/components/InstrumentIcon';
import type { Alert, AlertKind, H8BosBtlDetail, H8BosBtlPayload } from '../types';

export const KIND_LABEL: Record<AlertKind, string> = {
  'BOS + BTL': 'BOS + BTL',
  BOS: 'BOS',
  BTL: 'BTL',
  DEVELOPING: 'Developing',
  MONITORING: 'Monitoring',
};
const KIND_CLASS: Record<AlertKind, string> = {
  'BOS + BTL': 'is-combo',
  BOS: 'is-bos',
  BTL: 'is-btl',
  DEVELOPING: 'is-dev',
  MONITORING: 'is-mon',
};

export const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export function fmtPrice(v: number | null | undefined, digits: number) {
  return v == null || !Number.isFinite(v) ? '—' : v.toFixed(digits);
}

export function fmtUtc(iso: string | null | undefined) {
  if (!iso) return '—';
  const d = new Date(iso);
  const mon = MONTHS[d.getUTCMonth()];
  return `${String(d.getUTCDate()).padStart(2, '0')} ${mon} ${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')} UTC`;
}

const dirClass = (d?: string | null) => (d === 'Bearish' ? 'is-bear' : d === 'Bullish' ? 'is-bull' : '');

export function SummaryCards({
  data,
  filter,
  onFilter,
}: {
  data: H8BosBtlPayload;
  filter: AlertKind | null;
  onFilter: (k: AlertKind | null) => void;
}) {
  const c = data.counts;
  const cards: { key: AlertKind | null; label: string; value: string; icon: ReactNode; tone: string }[] = [
    { key: null, label: 'Markets Scanned', value: `${c.scanned}/${c.total}`, icon: <Radar size={18} />, tone: 'blue' },
    { key: 'BOS + BTL', label: 'BOS + BTL', value: String(c['BOS + BTL']), icon: <Zap size={18} />, tone: 'red' },
    { key: 'BOS', label: 'BOS Only', value: String(c.BOS), icon: <Layers size={18} />, tone: 'orange' },
    { key: 'BTL', label: 'BTL Only', value: String(c.BTL), icon: <GitBranch size={18} />, tone: 'amber' },
    { key: 'DEVELOPING', label: 'Developing', value: String(c.DEVELOPING), icon: <Activity size={18} />, tone: 'violet' },
    { key: 'MONITORING', label: 'Monitoring', value: String(c.MONITORING), icon: <Eye size={18} />, tone: 'gray' },
  ];
  return (
    <div className="h8b-cards">
      {cards.map((k) => (
        <button
          type="button"
          key={k.label}
          className={`h8b-card tone-${k.tone}${filter === k.key && k.key ? ' is-on' : ''}`}
          onClick={() => onFilter(k.key === filter ? null : k.key)}
          title={k.key ? `Show only ${k.label} in the alert strip` : 'Show all alerts'}
        >
          <i>{k.icon}</i>
          <span>
            <b>{k.value}</b>
            <small>{k.label}</small>
          </span>
        </button>
      ))}
    </div>
  );
}

export function AlertStrip({
  alerts,
  selected,
  fresh,
  onSelect,
}: {
  alerts: Alert[];
  selected: string;
  fresh: Set<string>;
  onSelect: (s: string) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const scroll = (dir: number) => ref.current?.scrollBy({ left: dir * 360, behavior: 'smooth' });
  return (
    <div className="h8b-strip">
      <button type="button" className="h8b-arrow" onClick={() => scroll(-1)} aria-label="Scroll alerts left">
        <ChevronLeft size={16} />
      </button>
      <div className="h8b-strip-track" ref={ref}>
        {alerts.length === 0 && <span className="h8b-muted">No alerts match the filter</span>}
        {alerts.map((a) => (
          <button
            type="button"
            key={a.symbol}
            className={`h8b-chip ${KIND_CLASS[a.kind]}${a.symbol === selected ? ' is-selected' : ''}${fresh.has(a.symbol) ? ' is-new' : ''}`}
            onClick={() => onSelect(a.symbol)}
            title={a.closed_bar_proof.join('\n') || KIND_LABEL[a.kind]}
          >
            <InstrumentIcon base={a.base} quote={a.quote} size="sm" />
            <span>
              <b>{a.symbol}</b>
              <small>{KIND_LABEL[a.kind]}</small>
            </span>
            {fresh.has(a.symbol) && <em>NEW</em>}
          </button>
        ))}
      </div>
      <button type="button" className="h8b-arrow" onClick={() => scroll(1)} aria-label="Scroll alerts right">
        <ChevronRight size={16} />
      </button>
    </div>
  );
}

const TABS = ['Summary', 'Evidence', 'Scenarios', 'Trade Plan'] as const;

export function AnalysisPanel({ d }: { d: H8BosBtlDetail }) {
  const [tab, setTab] = useState<(typeof TABS)[number]>('Summary');
  const ev = d.event;
  const dg = d.digits;
  const confirmed = !!ev;
  const badge = confirmed ? `${d.kind} CONFIRMED` : d.kind === 'DEVELOPING' ? 'DEVELOPING' : 'MONITORING';
  const swingWord = ev?.direction === 'Bullish' ? 'Swing High' : 'Swing Low';
  return (
    <aside className="h8b-panel">
      <header>
        <div className="h8b-panel-title">
          <InstrumentIcon base={d.symbol.slice(0, 3)} quote={d.symbol.slice(3, 6)} size="sm" />
          <div>
            <b>{d.symbol} — H8</b>
            <small>{d.name}</small>
          </div>
        </div>
        <strong className={`h8b-badge ${confirmed ? dirClass(ev?.direction) : d.kind === 'DEVELOPING' ? 'is-dev' : 'is-mon'}`}>{badge}</strong>
      </header>
      <nav className="h8b-tabs">
        {TABS.map((t) => (
          <button type="button" key={t} className={t === tab ? 'is-on' : ''} onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </nav>
      <div className="h8b-panel-body">
        {tab === 'Summary' && (
          <>
            <section>
              <h3>Current Event</h3>
              <dl>
                <dt>Event Type</dt>
                <dd className={dirClass(ev?.direction ?? d.developing?.direction)}>
                  {ev ? ev.kind : d.developing ? `${d.developing.event} (developing)` : 'None — monitoring'}
                </dd>
                <dt>Direction</dt>
                <dd className={dirClass(d.direction)}>{d.direction}</dd>
                <dt>H8 Structure</dt>
                <dd>{d.h8.structure}</dd>
                <dt>Break Strength</dt>
                <dd>{ev ? `${ev.break_strength_atr.toFixed(2)} ATR` : '—'}</dd>
                <dt>H8 Close</dt>
                <dd>{fmtPrice(ev ? ev.close : d.h8.last_close, dg)}</dd>
                <dt>BTL Level</dt>
                <dd>{ev?.btl ? `${fmtPrice(ev.btl.level, dg)} (Trend Line)` : '—'}</dd>
                <dt>BOS Level</dt>
                <dd>{ev?.bos ? `${fmtPrice(ev.bos.level, dg)} (${swingWord})` : '—'}</dd>
                <dt>Retest Zone</dt>
                <dd className={dirClass(ev?.direction)}>{ev ? `${fmtPrice(ev.retest[0], dg)} – ${fmtPrice(ev.retest[1], dg)}` : '—'}</dd>
                <dt>Invalidation</dt>
                <dd>{fmtPrice(ev?.invalidation, dg)}</dd>
                <dt>Retest Status</dt>
                <dd>{d.retest_status?.label ?? '—'}</dd>
                <dt>Confirmed At</dt>
                <dd>{ev ? fmtUtc(ev.at) : '—'}</dd>
              </dl>
              {d.developing && <p className="h8b-note">{d.developing.detail}</p>}
            </section>
            <section>
              <h3>Weekly Context (Fractal + SCH)</h3>
              {d.weekly.available ? (
                <>
                  <dl>
                    <dt>SCH Direction</dt>
                    <dd className={dirClass(d.weekly.direction)}>{d.weekly.direction}</dd>
                    <dt>SCH State</dt>
                    <dd>{d.weekly.state}</dd>
                    <dt>Price Position</dt>
                    <dd>
                      {d.weekly.position_pct == null ? '—' : `${Math.round(d.weekly.position_pct)}% (${d.weekly.position_label})`}
                    </dd>
                    <dt>Fractal State</dt>
                    <dd>{d.weekly.fractal_state ?? '—'}</dd>
                  </dl>
                  <p className="h8b-note">{d.weekly.interpretation}</p>
                </>
              ) : (
                <p className="h8b-note">{d.weekly.reason}</p>
              )}
            </section>
            <section>
              <h3>Multi-Timeframe Context</h3>
              <table>
                <thead>
                  <tr>
                    <th>TF</th>
                    <th>Structure</th>
                    <th>Direction</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {d.mtf.map((r) => (
                    <tr key={r.tf}>
                      <td>{r.tf}</td>
                      <td>{r.structure}</td>
                      <td className={dirClass(r.direction)}>{r.direction ?? '—'}</td>
                      <td>{r.status ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          </>
        )}
        {tab === 'Evidence' && (
          <section>
            <h3>Closed-bar Evidence</h3>
            <ul className="h8b-evidence">
              {d.evidence.map((e, i) => (
                <li key={i} className={e.confirmed === true ? 'is-ok' : e.confirmed === false ? 'is-pending' : ''}>
                  <span className="h8b-tf">{e.tf}</span>
                  <div>
                    <b>{e.label}</b>
                    <small>{e.detail ?? '—'}</small>
                  </div>
                </li>
              ))}
            </ul>
            {ev && <p className="h8b-note">Analysis ID {ev.analysis_id}</p>}
          </section>
        )}
        {tab === 'Scenarios' && (
          <section>
            <h3>Structural Scenarios</h3>
            <ul className="h8b-evidence">
              {d.scenarios.map((s) => (
                <li key={s.key}>
                  <div>
                    <b>{s.title}</b>
                    <small>{s.detail}</small>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        )}
        {tab === 'Trade Plan' && (
          <section>
            <h3>Trade Plan</h3>
            <p className="h8b-note h8b-note--left">
              Analysis only. This page reports closed-bar structure and never issues BUY/SELL instructions; trade plans are produced by the
              Trading Opportunities workflow after risk authorization.
            </p>
            <dl>
              <dt>Structural bias</dt>
              <dd className={dirClass(d.direction)}>{d.direction}</dd>
              <dt>Reference zone</dt>
              <dd>{ev ? `${fmtPrice(ev.retest[0], dg)} – ${fmtPrice(ev.retest[1], dg)}` : '—'}</dd>
              <dt>Structure invalid beyond</dt>
              <dd>{fmtPrice(ev?.invalidation, dg)}</dd>
              <dt>H1 validation</dt>
              <dd>{d.h1.status.label}</dd>
              <dt>M30 confirmation</dt>
              <dd>{d.m30.status.label}</dd>
            </dl>
          </section>
        )}
      </div>
    </aside>
  );
}

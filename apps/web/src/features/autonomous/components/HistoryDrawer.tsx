import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { autonomousApi } from '../api';
import { OPP_STATE_TONE, pretty, price, utc, utcFull } from '../format';
import type { HistoryResponse, Opportunity, Transition } from '../types';
import { Empty, Sym } from './DetailParts';

function Timeline({ rows, digits }: { rows: Transition[]; digits: (s: string | null) => number }) {
  if (!rows.length) return <Empty>No transitions recorded.</Empty>;
  return (
    <ol className="ae-timeline">
      {rows.map((t) => {
        const close = t.evidence?.close;
        return (
          <li key={t.id} className={`is-${OPP_STATE_TONE[t.to_state] ?? 'muted'}`}>
            <i aria-hidden />
            <div>
              <div className="ae-tl-head">
                {t.symbol && rows.some((r) => r.symbol !== t.symbol) ? <Sym symbol={t.symbol} /> : null}
                <span className={`ae-tag is-${OPP_STATE_TONE[t.to_state] ?? 'muted'}`}>{t.to_state}</span>
                {t.from_state ? <small className="ae-muted">from {t.from_state}</small> : null}
              </div>
              <p>{t.detail ?? pretty(t.reason_code)}</p>
              <small className="ae-muted">
                Evidence {utcFull(t.evidence_at)} UTC · {t.reason_code}
                {typeof close === 'number' ? ` · close ${close.toFixed(digits(t.symbol))}` : ''}
                {t.provider ? ` · ${t.provider.toUpperCase()}` : ''}
              </small>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

const digitsOf = (s: string | null) => (!s ? 5 : s.startsWith('XAU') ? 2 : s.endsWith('JPY') ? 3 : 5);

/** Read-only audit trail: one opportunity's transitions, or the engine-wide log when no opportunity is chosen. */
export function HistoryDrawer({ target, onClose }: { target: Opportunity | 'ALL' | null; onClose: () => void }) {
  const [hist, setHist] = useState<HistoryResponse | null>(null);
  const [log, setLog] = useState<Transition[] | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!target) return;
    setHist(null);
    setLog(null);
    setError('');
    const req =
      target === 'ALL'
        ? autonomousApi.transitions('OPPORTUNITY', 200).then((r) => setLog(r.rows))
        : autonomousApi.history(target.id).then(setHist);
    req.catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [target]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  if (!target) return null;
  const o = hist?.opportunity;
  return (
    <div className="ae-drawer-backdrop" onClick={onClose}>
      <aside className="ae-drawer" role="dialog" aria-modal="true" aria-label="Opportunity history" onClick={(e) => e.stopPropagation()}>
        <header>
          <h3>{target === 'ALL' ? 'Opportunity Transition Log' : `${target.symbol} · ${target.type_label}`}</h3>
          <button type="button" className="ae-icon-btn" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </header>
        {error ? <div className="ae-banner is-bad">{error}</div> : null}
        {target !== 'ALL' && o ? (
          <dl className="ae-drawer-facts">
            <div>
              <dt>Direction</dt>
              <dd className={o.direction === 'BULLISH' ? 'is-up' : 'is-down'}>{pretty(o.direction)}</dd>
            </div>
            <div>
              <dt>Stage / State</dt>
              <dd>
                {o.stage_number}. {o.stage_label} · {o.state}
              </dd>
            </div>
            <div>
              <dt>Entry Zone</dt>
              <dd>
                {price(o.entry_lo, o.digits)} – {price(o.entry_hi, o.digits)}
              </dd>
            </div>
            <div>
              <dt>Invalidation</dt>
              <dd>{price(o.invalidation, o.digits)}</dd>
            </div>
            <div>
              <dt>Target 1 / 2</dt>
              <dd>
                {price(o.target_1, o.digits)} / {price(o.target_2, o.digits)}
              </dd>
            </div>
            <div>
              <dt>Reward : Risk</dt>
              <dd>{o.reward_risk != null ? o.reward_risk.toFixed(2) : '—'}</dd>
            </div>
            <div>
              <dt>Confidence / Quality</dt>
              <dd>
                {o.confidence != null ? `${o.confidence.toFixed(1)}%` : '—'} / {o.quality != null ? `${Math.round(o.quality)}%` : '—'}
              </dd>
            </div>
            <div>
              <dt>Parent → Trigger</dt>
              <dd>
                {o.parent_tf} → {o.trigger_tf}
              </dd>
            </div>
            <div>
              <dt>Origin</dt>
              <dd>{utc(o.origin_at, true)} UTC</dd>
            </div>
            <div>
              <dt>Evaluated Through</dt>
              <dd>{utc(o.evaluated_through, true)} UTC</dd>
            </div>
            <div>
              <dt>Provider</dt>
              <dd>{o.provider?.toUpperCase() ?? '—'}</dd>
            </div>
            <div>
              <dt>Outcome</dt>
              <dd>{o.outcome ? pretty(o.outcome) : o.status === 'ACTIVE' ? 'Open' : '—'}</dd>
            </div>
            {o.blockers.length ? (
              <div className="is-wide">
                <dt>Blockers</dt>
                <dd>{o.blockers.join(' · ')}</dd>
              </div>
            ) : null}
          </dl>
        ) : null}
        <div className="ae-drawer-body">
          {target === 'ALL' ? (
            log ? <Timeline rows={log} digits={digitsOf} /> : !error ? <Empty>Loading transitions…</Empty> : null
          ) : hist ? (
            <Timeline rows={hist.transitions} digits={digitsOf} />
          ) : !error ? (
            <Empty>Loading history…</Empty>
          ) : null}
        </div>
        <footer className="ae-muted ae-small">Read-only audit trail — transitions are append-only and written by the backend engine.</footer>
      </aside>
    </div>
  );
}

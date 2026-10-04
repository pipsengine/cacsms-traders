import { Radar } from 'lucide-react';
import { utcDateTime, ageText } from '../format';
import type { ScannerMeta } from '../types';

type Tone = 'live' | 'warn' | 'off';

function status(meta: ScannerMeta | null, apiError: boolean): { tone: Tone; title: string; sub: string } {
  if (apiError && !meta) return { tone: 'off', title: 'AUTONOMOUS SCANNER — UNAVAILABLE', sub: 'Scanner API not reachable' };
  if (!meta || meta.engine_state === 'STARTING') {
    return { tone: 'warn', title: 'AUTONOMOUS SCANNER — STARTING', sub: 'Waiting for first scan cycle' };
  }
  const scanned = `${meta.instruments_scanned}/${meta.instruments_total} instruments scanned`;
  if (meta.engine_state === 'ERROR') return { tone: 'off', title: 'AUTONOMOUS SCANNER — ERROR', sub: meta.engine_error ?? 'Scanner cycle failed' };
  if (apiError) return { tone: 'warn', title: 'AUTONOMOUS SCANNER — API INTERRUPTED', sub: `${scanned} · Showing last received cycle` };
  if (!meta.mt5_connected) return { tone: 'off', title: 'AUTONOMOUS SCANNER — MT5 DISCONNECTED', sub: `${scanned} · Last closed-bar cycle shown as stale` };
  if (meta.engine_state === 'SYNCING') return { tone: 'warn', title: 'AUTONOMOUS SCANNER — SYNCING', sub: `${scanned} · Completing history` };
  if (meta.stale) return { tone: 'warn', title: 'AUTONOMOUS SCANNER — STALE', sub: `${scanned} · Scanner cycle overdue` };
  return { tone: 'live', title: 'AUTONOMOUS SCANNER — ACTIVE', sub: `${scanned} · Closed-bar synchronized` };
}

export function ScannerHeader({ meta, apiError }: { meta: ScannerMeta | null; apiError: boolean }) {
  const s = status(meta, apiError);
  return (
    <header className="ms-head">
      <div className="ms-head-text">
        <nav className="ms-breadcrumb" aria-label="Breadcrumb">
          Market Intelligence <span aria-hidden>›</span> <span>Market Scanner</span>
        </nav>
        <h1>Market Scanner</h1>
        <p>Autonomous multi-factor scanner that monitors all markets and classifies instruments for deeper analysis.</p>
      </div>
      <div className={`ms-status-card is-${s.tone}`} role="status">
        <span className="ms-status-icon" aria-hidden>
          <Radar size={22} />
        </span>
        <div className="ms-status-main">
          <strong>
            <i className="ms-pulse" aria-hidden />
            {s.title}
          </strong>
          <span>{s.sub}</span>
        </div>
        <div className="ms-status-cycle">
          <span>Last completed cycle</span>
          <strong>{utcDateTime(meta?.last_cycle_at)}</strong>
          <small>{meta?.last_cycle_at ? ageText(meta.last_cycle_at) : '—'}</small>
        </div>
      </div>
    </header>
  );
}

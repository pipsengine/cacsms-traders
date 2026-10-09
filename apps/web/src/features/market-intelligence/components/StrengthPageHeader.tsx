import { BarChart3, CalendarDays } from 'lucide-react';
import type { MatrixMeta } from '../types';

export function utcParts(iso: string) {
  const d = new Date(iso);
  const date = new Intl.DateTimeFormat('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(d);
  const time = new Intl.DateTimeFormat('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    timeZone: 'UTC',
  }).format(d);
  return { date, time: `${time} (UTC+0)` };
}

type LiveStatus = { tone: 'live' | 'warn' | 'off'; title: string; sub: string };

function liveStatus(meta: MatrixMeta | null, apiError: boolean): LiveStatus {
  if (apiError) return { tone: 'off', title: 'API UNAVAILABLE', sub: 'Showing last received calculation' };
  if (!meta) return { tone: 'warn', title: 'MARKET DATA UNAVAILABLE', sub: 'Awaiting provider diagnostics' };
  if (!meta.provider_connected) {
    if (meta.error_code === 'CTRADER_APP_INACTIVE') return { tone: 'off', title: 'MARKET DATA UNAVAILABLE', sub: 'cTrader provider authorization unavailable' };
    const syncLike = ['SYNCING', 'STARTING', 'BACKFILLING', 'VALIDATING', 'CALCULATING', 'INCOMPLETE_BASKET', 'DISCOVERING_SYMBOLS'].includes(
      meta.engine_state || '',
    );
    if (syncLike || (meta.pairs_loaded ?? 0) > 0) {
      return {
        tone: 'warn',
        title: meta.engine_state || 'SYNCING',
        sub: `${meta.pairs_loaded ?? 0}/${meta.pairs_total ?? 28} pairs in repository`,
      };
    }
    return { tone: 'off', title: 'MARKET DATA UNAVAILABLE', sub: meta.provider_status === 'AUTHORIZATION REQUIRED' ? 'cTrader authorization required' : (meta.error_code || meta.provider_status || 'Connect a provider in System Control') };
  }
  if (meta.stale_reason === 'ENGINE_STALLED') {
    return { tone: 'warn', title: 'STALE DATA', sub: 'Strength engine not refreshing' };
  }
  if (meta.live_data) {
    const basis = meta.closed_bar_only ? 'Closed bars only' : 'Live price (EarnForex)';
    return { tone: 'live', title: 'LIVE DATA', sub: `${meta.active_provider || "Market data"} Connected • ${basis}` };
  }
  return { tone: 'warn', title: meta.engine_state || 'SYNCING', sub: `${meta.active_provider || 'Market data'}: completing basket history` };
}

export function StrengthPageHeader({ meta, apiError = false }: { meta: MatrixMeta | null; apiError?: boolean }) {
  const calc = meta?.last_calculated_at ? utcParts(meta.last_calculated_at) : null;
  const status = liveStatus(meta, apiError);

  return (
    <header className="si-page-head">
      <nav className="si-breadcrumb" aria-label="Breadcrumb">
        Market Intelligence <span aria-hidden>›</span> <span>Strength Intelligence</span>
      </nav>
      <div className="si-title-row">
        <div className="si-title-block">
          <div className="si-title-icon" aria-hidden>
            <BarChart3 size={22} />
          </div>
          <div>
            <h1>Strength Intelligence</h1>
            <p>
              Relative currency strength, historical dynamics and pair relationships — analysis only, no trade
              signals.
            </p>
          </div>
        </div>
        <div className="si-head-status">
          <div className="si-head-box si-head-box--time" title="Last calculation time">
            <CalendarDays size={18} aria-hidden />
            <div>
              <strong>{calc?.date ?? 'Awaiting calculation'}</strong>
              <span>{calc?.time ?? '—'}</span>
            </div>
          </div>
          <div className={`si-head-box si-head-box--live is-${status.tone}`} role="status">
            <i className="si-live-dot" aria-hidden />
            <div>
              <strong>{status.title}</strong>
              <span>{status.sub}</span>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}

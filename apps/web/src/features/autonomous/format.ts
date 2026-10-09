import type { Metrics, StageSummary } from './types';

export const STATUS_TONE: Record<string, string> = {
  RUNNING: 'ok',
  NORMAL: 'ok',
  CONNECTED: 'ok',
  OK: 'ok',
  Sent: 'ok',
  SENT: 'ok',
  WAITING: 'wait',
  PENDING: 'muted',
  IDLE: 'muted',
  STARTING: 'muted',
  UNKNOWN: 'muted',
  DEGRADED: 'warn',
  WARN: 'warn',
  STALE: 'warn',
  STALLED: 'warn',
  SYNCHRONIZING: 'warn',
  DATA_READY: 'ok',
  OFFLINE: 'bad',
  BLOCKED: 'bad',
  HALTED: 'bad',
  HALT: 'bad',
  CRITICAL: 'bad',
  ERROR: 'bad',
  FAILED: 'bad',
  DISCONNECTED: 'bad',
  QUEUED: 'info',
  VALIDATED: 'info',
  SENDING: 'info',
  RETRY_PENDING: 'warn',
  DETECTED: 'muted',
  SUPPRESSED: 'muted',
};

export const tone = (status: string | null | undefined) => STATUS_TONE[status ?? ''] ?? 'muted';

export const pretty = (v: string | null | undefined) =>
  v ? v.replaceAll('_', ' ').toLowerCase().replace(/(^|\s)\S/g, (s) => s.toUpperCase()) : '—';

export function num(m: Metrics | undefined, key: string): number | null {
  const v = m?.[key];
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

export function rec(m: Metrics | undefined, key: string): Record<string, number> {
  const v = m?.[key];
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, number>) : {};
}

export function str(m: Metrics | undefined, key: string): string | null {
  const v = m?.[key];
  return typeof v === 'string' && v ? v : null;
}

export function list<T>(d: Record<string, unknown> | undefined, key: string): T[] {
  const v = d?.[key];
  return Array.isArray(v) ? (v as T[]) : [];
}

const n0 = (v: number | null | undefined) => (v == null ? '0' : String(v));

/** Two compact lines for a stage card, read from the metrics the backend persisted for that stage. */
export function stageLines(s: StageSummary): [string, string] {
  const m = s.metrics;
  switch (s.key) {
    case 'MARKET_DATA': {
      const f = rec(m, 'freshness');
      return [`${s.processed} / ${s.active} symbols`, `${n0(f.STALE)} stale · ${s.errors} excluded`];
    }
    case 'INTELLIGENCE':
      return [`${s.processed} / 28 pairs`, str(m, 'strongest') ? `${str(m, 'strongest')} strongest · ${str(m, 'weakest')} weakest` : 'Awaiting strength'];
    case 'SCANNER': {
      const c = rec(m, 'counts');
      return [`${n0(c.HIGH_INSPECTION)} high interest`, `${n0(c.WATCHING)} watching · ${n0(c.NEUTRAL)} neutral`];
    }
    case 'STRUCTURE':
      return [`${n0(num(m, 'trending'))} trending`, `${n0(num(m, 'bos_24h'))} BOS · ${n0(num(m, 'choch_24h'))} CHoCH (24h)`];
    case 'CHANNEL':
      return [`${n0(num(m, 'active_channels'))} active`, `${n0(num(m, 'touches_today'))} touches · ${n0(num(m, 'breaks_today'))} breaks`];
    case 'OPPORTUNITY': {
      const t = rec(m, 'by_type');
      const parts = Object.entries(t).map(([k, v]) => `${v} ${TYPE_SHORT[k] ?? k}`);
      return [`${s.active} waiting for zone`, parts.length ? parts.join(' · ') : `${n0(num(m, 'created_today'))} created today`];
    }
    case 'CONFIRMATION':
      return [`${s.waiting} awaiting reaction`, `${s.active} awaiting confirmation`];
    case 'RISK':
      return [`${n0(num(m, 'authorised_today'))} authorised`, `${n0(num(m, 'deferred'))} deferred · ${n0(num(m, 'rejected_today'))} rejected`];
    case 'EXECUTION':
      return [`${n0(num(m, 'orders_submitted'))} orders`, 'Analysis only'];
    case 'MANAGEMENT':
      return [`${n0(num(m, 'open_positions'))} open positions`, `${n0(num(m, 'shadow_plans_tracked'))} shadow plans`];
    case 'LEARNING': {
      const hr = num(m, 'hit_rate');
      return [`${n0(num(m, 'closed_30d'))} closed (30d)`, hr == null ? 'No resolved outcomes' : `${hr}% hit rate`];
    }
    default:
      return [`${s.processed} processed`, `${s.waiting} waiting`];
  }
}

export const TYPE_SHORT: Record<string, string> = {
  P1_RETRACEMENT: 'P1',
  P2_BREAKOUT_RETEST: 'P2',
  CONTINUATION: 'Cont',
  TIT: 'TiT',
};

export function utc(iso: string | null | undefined, withDate = false) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const time = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'UTC' }).format(d);
  if (!withDate) return time;
  const date = new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', timeZone: 'UTC' }).format(d);
  return `${date} ${time}`;
}

export function utcSeconds(iso: string | null | undefined) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false, timeZone: 'UTC' }).format(d);
}

/** e.g. "07 Oct 10:24:36" (UTC). */
export function utcFull(iso: string | null | undefined) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const date = new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', timeZone: 'UTC' }).format(d);
  return `${date} ${utcSeconds(iso)}`;
}

export function duration(fromIso: string | null | undefined, now = Date.now()) {
  if (!fromIso) return '—';
  const s = Math.max(0, Math.round((now - new Date(fromIso).getTime()) / 1000));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
  return `${Math.floor(s / 86400)}d ${Math.floor((s % 86400) / 3600)}h`;
}

export function until(iso: string | null | undefined, now = Date.now()) {
  if (!iso) return '—';
  const s = Math.round((new Date(iso).getTime() - now) / 1000);
  if (s <= 0) return 'due';
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
}

export function price(v: number | null | undefined, digits: number) {
  if (v == null || !Number.isFinite(v)) return '—';
  return v.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export const ALERT_LABEL: Record<string, string> = {
  CHANNEL_TOUCH: 'Channel Touch',
  CHANNEL_BREAK: 'Channel Break',
  BREAK_RETEST_CONTINUATION: 'Break & Retest',
  TIT_DETECTED: 'TiT Detected',
};

export const CHANNEL_STATE_TONE: Record<string, string> = {
  FORMING: 'muted',
  ACTIVE: 'ok',
  MATURE: 'ok',
  TOUCHED: 'info',
  BREAKING: 'warn',
  BROKEN: 'warn',
  RETESTING: 'purple',
  CONTINUING: 'ok',
  INVALIDATED: 'bad',
  EXPIRED: 'muted',
};

export const OPP_STATE_TONE: Record<string, string> = {
  WAITING_FOR_ZONE: 'wait',
  AWAITING_REACTION: 'info',
  REACTION_CONFIRMED: 'info',
  RISK_REVIEW: 'purple',
  RISK_DEFERRED: 'warn',
  RISK_APPROVED: 'ok',
  RISK_REJECTED: 'bad',
  EXECUTION_BLOCKED_ANALYSIS_ONLY: 'slate',
  INVALIDATED: 'bad',
  EXPIRED: 'muted',
  COMPLETED: 'ok',
};

import type { ScannerRow } from './types';

export function fmtPrice(v: number | null | undefined, digits = 5) {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  return v.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function fmtPct(v: number | null | undefined, dp = 2) {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  return `${v > 0 ? '+' : ''}${v.toFixed(dp)}%`;
}

export function fmtSigned(v: number | null | undefined, dp = 1) {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  return `${v > 0 ? '+' : ''}${v.toFixed(dp)}`;
}

export function tone(v: number | null | undefined) {
  if (v === null || v === undefined || v === 0) return 'flat';
  return v > 0 ? 'up' : 'down';
}

export function utcTime(iso: string | null | undefined) {
  if (!iso) return '—';
  return new Intl.DateTimeFormat('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    timeZone: 'UTC',
  }).format(new Date(iso));
}

export function utcDateTime(iso: string | null | undefined) {
  if (!iso) return '—';
  const d = new Date(iso);
  const date = new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(d);
  return `${date}, ${utcTime(iso)} UTC`;
}

export function ageText(iso: string | null | undefined, now = Date.now()) {
  if (!iso) return '—';
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export function pipSize(row: Pick<ScannerRow, 'symbol' | 'quote' | 'digits'>) {
  if (row.symbol === 'XAUUSD') return 0.1;
  return row.quote === 'JPY' ? 0.01 : 0.0001;
}

export function priceDigits(row: Pick<ScannerRow, 'digits' | 'symbol' | 'quote'>) {
  return row.digits ?? (row.symbol === 'XAUUSD' ? 2 : row.quote === 'JPY' ? 3 : 5);
}

export const STATUS_CLASS: Record<string, string> = {
  HIGH_INSPECTION: 'is-high',
  WATCHING: 'is-watch',
  NEUTRAL: 'is-neutral',
  EXCLUDED: 'is-excluded',
};

export const CHANNEL_CLASS: Record<string, string> = {
  ABOVE: 'is-upper',
  NEAR_UPPER: 'is-upper',
  UPPER_ZONE: 'is-upper-soft',
  MID: 'is-mid',
  LOWER_ZONE: 'is-lower-soft',
  NEAR_LOWER: 'is-lower',
  BELOW: 'is-lower',
};

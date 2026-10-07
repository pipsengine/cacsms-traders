const LAGOS = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Africa/Lagos',
  day: '2-digit',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});

export function fmtTime(value?: string | null): string {
  if (!value) return '—';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? '—' : `${LAGOS.format(d)} WAT`;
}

export function fmtPrice(value: number | null | undefined, symbol: string): string {
  if (value == null || !Number.isFinite(value)) return '—';
  const dp = symbol.startsWith('XAU') ? 2 : symbol.endsWith('JPY') ? 3 : 5;
  return value.toLocaleString('en-US', { minimumFractionDigits: dp, maximumFractionDigits: dp });
}

export function providerLabel(p: string): string {
  const k = p.toLowerCase();
  return k === 'mt5' ? 'MT5' : k === 'ctrader' ? 'cTrader' : p;
}

export function statusTone(status: string): 'ok' | 'warn' | 'bad' | 'muted' {
  if (status === 'SENT') return 'ok';
  if (status === 'FAILED') return 'bad';
  if (status === 'SUPPRESSED' || status === 'DUPLICATE') return 'muted';
  return 'warn';
}

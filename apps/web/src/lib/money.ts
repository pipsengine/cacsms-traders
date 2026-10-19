/** Format a broker amount in the account currency. NGN uses the naira sign. */
export function accountMoney(value: number | null | undefined, currency: string | null | undefined, signed = false): string {
  if (value == null || !Number.isFinite(value)) return '—';
  const code = (currency || 'USD').toUpperCase();
  const sign = value < 0 ? '−' : signed && value > 0 ? '+' : '';
  const abs = Math.abs(value);
  if (code === 'NGN') {
    return `${sign}₦${abs.toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
  try {
    const formatted = new Intl.NumberFormat('en-US', {
      style: 'currency', currency: code, minimumFractionDigits: 2, maximumFractionDigits: 2,
    }).format(abs);
    return `${sign}${formatted}`;
  } catch {
    return `${sign}${code} ${abs.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
}

export function linkLabel(state: string | null | undefined): string {
  if (state === 'CONNECTED') return 'Connected';
  if (state === 'DEGRADED') return 'Degraded';
  if (state === 'DISCONNECTED') return 'Disconnected';
  return state || 'Disconnected';
}

export function executionLabel(state: string | null | undefined): string {
  if (state === 'LIVE_EXECUTION') return 'Live execution';
  if (state === 'EMERGENCY_STOP') return 'Emergency stop';
  if (state === 'SIMULATION') return 'Simulation';
  return state || 'Simulation';
}

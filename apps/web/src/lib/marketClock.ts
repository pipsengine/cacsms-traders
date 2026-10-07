/**
 * Spot FX market clock. The week runs Sunday 17:00 → Friday 17:00 New York (broker D1 rollover),
 * matching the backend trading calendar. All boundaries fall on whole New York hours.
 */

export const LAGOS_TZ = 'Africa/Lagos';
const NEW_YORK_TZ = 'America/New_York';
const HOUR = 3_600_000;
const ROLLOVER_HOUR = 17;
const HOLIDAYS = new Set(['12-25', '01-01']);

export type MarketTone = 'open' | 'caution' | 'closed';
export type MarketKey = 'OPEN' | 'ROLLOVER' | 'CLOSING' | 'OPENING' | 'CLOSED' | 'HOLIDAY';

export type MarketState = {
  key: MarketKey;
  label: string;
  tone: MarketTone;
  detail: string;
};

export type MarketStatus = MarketState & {
  next: { key: MarketKey; label: string; at: Date } | null;
};

const nyParts = new Intl.DateTimeFormat('en-US', {
  timeZone: NEW_YORK_TZ,
  hourCycle: 'h23',
  weekday: 'short',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
});
const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

function newYork(d: Date) {
  const p = Object.fromEntries(nyParts.formatToParts(d).map((x) => [x.type, x.value]));
  return { wd: WEEKDAYS.indexOf(p.weekday), hour: Number(p.hour), mmdd: `${p.month}-${p.day}` };
}

function nextDay(d: Date) {
  return newYork(new Date(d.getTime() + 24 * HOUR)).mmdd;
}

function session(d: Date) {
  const h = d.getUTCHours();
  if (h >= 12 && h < 16) return 'London / New York overlap';
  if (h >= 7 && h < 12) return 'London session';
  if (h >= 16 && h < 21) return 'New York session';
  return 'Sydney / Tokyo session';
}

export function marketState(d: Date): MarketState {
  const { wd, hour, mmdd } = newYork(d);
  const tradingDay = hour >= ROLLOVER_HOUR ? nextDay(d) : mmdd;
  const inWeek = (wd === 0 && hour >= ROLLOVER_HOUR) || (wd >= 1 && wd <= 4) || (wd === 5 && hour < ROLLOVER_HOUR);

  if (!inWeek) {
    if (wd === 0 && hour === ROLLOVER_HOUR - 1)
      return { key: 'OPENING', label: 'Opening Soon', tone: 'caution', detail: 'Weekly open within the hour' };
    return { key: 'CLOSED', label: 'Market Closed', tone: 'closed', detail: 'Weekend closure' };
  }
  if (HOLIDAYS.has(tradingDay))
    return { key: 'HOLIDAY', label: 'Market Closed', tone: 'closed', detail: 'Bank holiday' };
  if (wd === 5 && hour === ROLLOVER_HOUR - 1)
    return { key: 'CLOSING', label: 'Closing Soon', tone: 'caution', detail: 'Weekly close within the hour' };
  if (wd >= 1 && wd <= 4 && hour === ROLLOVER_HOUR)
    return { key: 'ROLLOVER', label: 'Daily Rollover', tone: 'caution', detail: 'Low liquidity · wider spreads' };
  return { key: 'OPEN', label: 'Market Open', tone: 'open', detail: session(d) };
}

const isClosed = (k: MarketKey) => k === 'CLOSED' || k === 'HOLIDAY';
const TARGET: Record<MarketKey, (k: MarketKey) => boolean> = {
  OPEN: (k) => k === 'ROLLOVER' || isClosed(k),
  ROLLOVER: (k) => k !== 'ROLLOVER',
  CLOSING: isClosed,
  OPENING: (k) => k === 'OPEN',
  CLOSED: (k) => k === 'OPEN',
  HOLIDAY: (k) => k === 'OPEN',
};

/** Current state plus the next meaningful change; scans whole hours (at most ~a week ahead). */
export function marketStatus(now: Date): MarketStatus {
  const state = marketState(now);
  let t = Math.floor(now.getTime() / HOUR) * HOUR + HOUR;
  for (let i = 0; i < 24 * 8; i++, t += HOUR) {
    const s = marketState(new Date(t));
    if (TARGET[state.key](s.key)) return { ...state, next: { key: s.key, label: s.label, at: new Date(t) } };
  }
  return { ...state, next: null };
}

export function formatCountdown(ms: number) {
  const m = Math.max(0, Math.ceil(ms / 60_000));
  const d = Math.floor(m / 1440);
  const h = Math.floor((m % 1440) / 60);
  const mm = m % 60;
  if (d) return `${d}d ${h}h`;
  if (h) return `${h}h ${String(mm).padStart(2, '0')}m`;
  return `${mm}m`;
}

export function nextChangeLabel(status: MarketStatus, now: Date) {
  if (!status.next) return '';
  const k = status.next.key;
  const verb = status.key === 'ROLLOVER' ? 'Ends' : k === 'OPEN' ? 'Opens' : k === 'ROLLOVER' ? 'Rollover' : 'Closes';
  return `${verb} in ${formatCountdown(status.next.at.getTime() - now.getTime())}`;
}

export const lagosDate = new Intl.DateTimeFormat('en-GB', {
  timeZone: LAGOS_TZ,
  weekday: 'short',
  day: '2-digit',
  month: 'short',
  year: 'numeric',
});

export const lagosTime = new Intl.DateTimeFormat('en-GB', {
  timeZone: LAGOS_TZ,
  hourCycle: 'h23',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
});

export const lagosShort = new Intl.DateTimeFormat('en-GB', {
  timeZone: LAGOS_TZ,
  hourCycle: 'h23',
  weekday: 'short',
  hour: '2-digit',
  minute: '2-digit',
});

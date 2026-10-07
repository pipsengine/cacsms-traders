import { useEffect, useMemo, useState } from 'react';
import { CalendarDays, Clock } from 'lucide-react';
import { lagosDate, lagosShort, lagosTime, marketStatus, nextChangeLabel } from '../lib/marketClock';

function useNow() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    let id: number;
    const tick = () => {
      const d = new Date();
      setNow(d);
      id = window.setTimeout(tick, 1000 - d.getMilliseconds() + 5);
    };
    id = window.setTimeout(tick, 1000 - new Date().getMilliseconds() + 5);
    return () => window.clearTimeout(id);
  }, []);
  return now;
}

export function TopBarStatus() {
  const now = useNow();
  const hourStart = Math.floor(now.getTime() / 3_600_000) * 3_600_000;
  const status = useMemo(() => marketStatus(new Date(hourStart)), [hourStart]);
  const countdown = nextChangeLabel(status, now);
  const title = status.next
    ? `${status.label} · ${status.detail}\n${status.next.label} at ${lagosShort.format(status.next.at)} WAT`
    : `${status.label} · ${status.detail}`;

  return (
    <div className="top-status">
      <div className={`top-market is-${status.tone}`} title={title} role="status" aria-live="polite">
        <i aria-hidden />
        <div>
          <b>{status.label}</b>
          <span>
            {status.detail}
            {countdown && <em> · {countdown}</em>}
          </span>
        </div>
      </div>
      <div className="top-clock top-clock--date">
        <CalendarDays aria-hidden />
        <div>
          <span>Date</span>
          <b>{lagosDate.format(now)}</b>
        </div>
      </div>
      <div className="top-clock" title="Nigeria local time (West Africa Time, UTC+1)">
        <Clock aria-hidden />
        <div>
          <span>Lagos · WAT</span>
          <b className="top-clock-time">
            <time dateTime={now.toISOString()}>{lagosTime.format(now)}</time>
            <small> WAT</small>
          </b>
        </div>
      </div>
    </div>
  );
}

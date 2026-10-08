import { useEffect, useState, type ReactNode } from 'react';
import { Activity, Gauge, Server, ShieldCheck, Users, Wifi } from 'lucide-react';
import { lagosTime } from '../../../lib/marketClock';
import { pretty, tone } from '../format';
import type { Overview } from '../types';

function Tile({ icon, label, value, state }: { icon: ReactNode; label: string; value: ReactNode; state: string }) {
  return (
    <div className={`ae-tile is-${state}`}>
      <span className="ae-tile-icon" aria-hidden>
        {icon}
      </span>
      <div>
        <span>{label}</span>
        <b>{value}</b>
      </div>
    </div>
  );
}

/** Ticks the server clock locally between polls, anchored to the last server_time the API returned. */
function useServerClock(serverIso: string | undefined) {
  const [offset, setOffset] = useState(0);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (serverIso) setOffset(new Date(serverIso).getTime() - Date.now());
  }, [serverIso]);
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);
  return serverIso ? new Date(now + offset).toISOString() : null;
}

const watDate = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Africa/Lagos',
  weekday: 'long',
  day: 'numeric',
  month: 'long',
  year: 'numeric',
});

export function StatusRibbon({ data, error }: { data: Overview | null; error: string }) {
  const r = data?.ribbon;
  const clock = useServerClock(r?.server_time);
  const when = clock ? new Date(clock) : null;
  const system = error && !data ? 'ERROR' : r?.system_status ?? 'STARTING';
  const connected = r?.provider_connection === 'CONNECTED';
  return (
    <header className="ae-head">
      <div className="ae-title">
        <div className="ae-title-row">
          <h1>Autonomous Trading Engine</h1>
          <span className={`ae-pill is-${tone(system)}`}>
            <i aria-hidden />
            {system}
          </span>
        </div>
        <p>End-to-end autonomous processing from market data to position management and control.</p>
      </div>
      <div className="ae-ribbon" aria-label="Global engine status">
        <Tile icon={<Activity size={16} />} label="System Status" value={pretty(system)} state={tone(system)} />
        <Tile icon={<ShieldCheck size={16} />} label="Safety Status" value={pretty(r?.safety_status ?? 'UNKNOWN')} state={tone(r?.safety_status)} />
        <Tile
          icon={<Gauge size={16} />}
          label="Operating Mode"
          value={<span className="ae-mode">{(r?.operating_mode ?? '—').replaceAll('_', ' ')}</span>}
          state="info"
        />
        <Tile icon={<Server size={16} />} label="Active Provider" value={(r?.provider_label ?? 'None').toUpperCase()} state={r?.provider ? 'info' : 'bad'} />
        <Tile icon={<Wifi size={16} />} label="Connections" value={connected ? 'Healthy' : 'Offline'} state={connected ? 'ok' : 'bad'} />
        <Tile
          icon={<Users size={16} />}
          label="Workers"
          value={r ? `${r.workers_online} / ${r.workers_total} online` : '—'}
          state={!r || !r.workers_total ? 'muted' : r.workers_online === r.workers_total ? 'ok' : r.workers_online ? 'warn' : 'bad'}
        />
      </div>
      <div className="ae-clock" title="West Africa Time (UTC+1)">
        <b>{when ? watDate.format(when) : '—'}</b>
        <span>
          {when ? lagosTime.format(when) : '—'}
          <small> WAT</small>
        </span>
      </div>
    </header>
  );
}

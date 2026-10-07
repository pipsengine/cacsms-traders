import { useEffect, useState, type ReactNode } from 'react';
import { Activity, Clock, Cpu, Gauge, History, Server, ShieldCheck, Users, Wifi } from 'lucide-react';
import { pretty, tone, utc, utcFull } from '../format';
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

export function StatusRibbon({ data, error }: { data: Overview | null; error: string }) {
  const r = data?.ribbon;
  const clock = useServerClock(r?.server_time);
  const system = error && !data ? 'ERROR' : r?.system_status ?? 'STARTING';
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
        <p>End-to-end autonomous processing from market data to position management and learning. Monitoring only — stages advance on backend evidence.</p>
      </div>
      <div className="ae-ribbon" aria-label="Global engine status">
        <Tile icon={<Activity size={18} />} label="System Status" value={pretty(system)} state={tone(system)} />
        <Tile icon={<ShieldCheck size={18} />} label="Safety Status" value={pretty(r?.safety_status ?? 'UNKNOWN')} state={tone(r?.safety_status)} />
        <Tile
          icon={<Gauge size={18} />}
          label="Operating Mode"
          value={<span className="ae-mode">{(r?.operating_mode ?? '—').replaceAll('_', ' ')}</span>}
          state={r?.operating_mode === 'ANALYSIS_ONLY' ? 'info' : tone(r?.operating_mode)}
        />
        <Tile icon={<Server size={18} />} label="Active Provider" value={r?.provider_label ?? 'None'} state={r?.provider ? 'info' : 'bad'} />
        <Tile icon={<Wifi size={18} />} label="Provider Connection" value={pretty(r?.provider_connection ?? 'DISCONNECTED')} state={tone(r?.provider_connection)} />
        <Tile
          icon={<Users size={18} />}
          label="Workers"
          value={r ? `${r.workers_online} / ${r.workers_total} online` : '—'}
          state={!r || !r.workers_total ? 'muted' : r.workers_online === r.workers_total ? 'ok' : r.workers_online ? 'warn' : 'bad'}
        />
        <Tile icon={<Clock size={18} />} label="Server Time (UTC)" value={utcFull(clock)} state="muted" />
        <Tile
          icon={<History size={18} />}
          label="Last Successful Cycle"
          value={r?.last_successful_cycle ? `${utc(r.last_successful_cycle, true)} UTC` : 'None yet'}
          state={r?.last_successful_cycle ? 'ok' : 'muted'}
        />
        {r ? (
          <span className="ae-cadence" title={`Engine ${r.engine_version}`}>
            <Cpu size={13} /> {r.cadence === 'WORKER' ? 'Background worker' : 'On-demand cycles'}
            {r.last_cycle_origin ? ` · last cycle: ${pretty(r.last_cycle_origin)}` : ''}
          </span>
        ) : null}
      </div>
    </header>
  );
}

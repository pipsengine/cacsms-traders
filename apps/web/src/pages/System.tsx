import React from 'react';
import { PauseCircle, ShieldAlert } from 'lucide-react';
import { Card, Notice, PageHeader, Status } from '../components/Ui';
import { get, put } from '../lib/api';

const MODES = ['ANALYSIS_ONLY', 'SHADOW', 'DEMO_AUTONOMOUS', 'LIVE_AUTONOMOUS', 'PAUSED', 'EMERGENCY_STOP'];

export function System({
  mode,
  onChanged,
  isPlatformAdmin,
}: {
  mode: string;
  onChanged: () => void;
  isPlatformAdmin: boolean;
}) {
  const [current, setCurrent] = React.useState(mode);

  React.useEffect(() => {
    setCurrent(mode);
    get<{ mode: string }>('/system/mode')
      .then((r) => setCurrent(r.mode))
      .catch(() => {});
  }, [mode]);

  async function selectMode(next: string) {
    if (!isPlatformAdmin) return;
    const reason = window.prompt('Reason for mode change (audited)') ?? 'Operator change';
    const res = await put<{ mode: string }>('/system/mode', { mode: next, reason });
    setCurrent(res.mode);
    onChanged();
  }

  return (
    <>
      <PageHeader title="System Control" subtitle="Global operating state and hard platform safety controls." />
      <Notice title="Current foundation mode" text={`${current.replaceAll('_', ' ')} — trading engines are not installed in this build.`} />
      <div className="two-col">
        <Card>
          <div className="card-title">
            <div>
              <h2>Operating mode</h2>
              <p>System-wide runtime authority.</p>
            </div>
            <Status value={current} />
          </div>
          <div className="mode-list">
            {MODES.map((m) => (
              <button
                type="button"
                className={m === current ? 'mode active' : 'mode'}
                key={m}
                disabled={!isPlatformAdmin}
                onClick={() => selectMode(m)}
              >
                <span>{m.replaceAll('_', ' ')}</span>
                <small>{m === current ? 'Current mode' : 'Requires platform administrator'}</small>
              </button>
            ))}
          </div>
        </Card>
        <Card>
          <div className="card-title">
            <div>
              <h2>Emergency controls</h2>
              <p>Hard controls remain independent of AI decisions.</p>
            </div>
          </div>
          <button type="button" className="danger-btn" disabled={!isPlatformAdmin} onClick={() => selectMode('EMERGENCY_STOP')}>
            <ShieldAlert />
            Emergency Stop
          </button>
          <button type="button" className="secondary full" disabled={!isPlatformAdmin} onClick={() => selectMode('PAUSED')}>
            <PauseCircle />
            Pause New Trading
          </button>
          <p className="muted">Mode changes are persisted and written to the audit trail when authorized.</p>
        </Card>
      </div>
    </>
  );
}

import type { ReactNode } from 'react';
import { Activity, ChevronRight, Database, Layers, Radar, ScanSearch } from 'lucide-react';
import { utcTime } from '../format';
import type { ScannerCounts, ScannerMeta } from '../types';

type StepTone = 'ok' | 'warn' | 'off' | 'idle';
type Step = { n: number; icon: ReactNode; title: string; value: string; status: string; tone: StepTone; active?: boolean };

export function ScannerPipeline({ meta, counts }: { meta: ScannerMeta | null; counts: ScannerCounts | null }) {
  const connected = !!meta?.mt5_connected;
  const high = counts?.HIGH_INSPECTION ?? 0;
  const strengthTone: StepTone = !meta?.strength_as_of ? 'idle' : meta.strength_live ? 'ok' : 'warn';
  const steps: Step[] = [
    {
      n: 1,
      icon: <Database size={18} />,
      title: 'Market Data',
      value: 'MT5 Live Feed',
      status: !meta ? 'Checking…' : connected ? 'Connected' : 'Disconnected',
      tone: !meta ? 'idle' : connected ? 'ok' : 'off',
    },
    {
      n: 2,
      icon: <Activity size={18} />,
      title: 'Strength Intelligence',
      value: `${meta?.currencies ?? 8} Currencies`,
      status: meta?.strength_as_of
        ? `${meta.strength_live ? 'Updated' : 'Stale since'} ${utcTime(meta.strength_as_of)} UTC`
        : 'Awaiting calculation',
      tone: strengthTone,
    },
    {
      n: 3,
      icon: <Radar size={18} />,
      title: 'Market Scanner',
      value: `${meta?.instruments_scanned ?? 0} Instruments`,
      status: meta?.cycle_id ? 'Classified & Ranked' : 'First cycle pending',
      tone: meta?.cycle_id ? (meta.stale ? 'warn' : 'ok') : 'idle',
      active: true,
    },
    {
      n: 4,
      icon: <ScanSearch size={18} />,
      title: 'Deep Inspection',
      value: `${high} instrument${high === 1 ? '' : 's'}`,
      status: high ? 'Queued for inspection' : 'No candidates',
      tone: high ? 'warn' : 'idle',
    },
    {
      n: 5,
      icon: <Layers size={18} />,
      title: 'Downstream Engines',
      value: 'Structure · Channel · Opportunities',
      status: 'Continuous analysis',
      tone: meta?.cycle_id ? 'ok' : 'idle',
    },
  ];

  return (
    <section className="ms-pipeline" aria-label="Analysis pipeline">
      {steps.map((s, i) => (
        <div key={s.n} className="ms-pipe-cell">
          <div className={`ms-pipe-step ${s.active ? 'is-active' : ''}`}>
            <span className="ms-pipe-num">{s.n}</span>
            <span className="ms-pipe-icon" aria-hidden>
              {s.icon}
            </span>
            <div className="ms-pipe-text">
              <strong>{s.title}</strong>
              <span>{s.value}</span>
              <small className={`is-${s.tone}`}>
                <i aria-hidden />
                {s.status}
              </small>
            </div>
          </div>
          {i < steps.length - 1 ? <ChevronRight className="ms-pipe-arrow" size={18} aria-hidden /> : null}
        </div>
      ))}
    </section>
  );
}

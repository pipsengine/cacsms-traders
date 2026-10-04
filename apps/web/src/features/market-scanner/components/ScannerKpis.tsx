import type { ReactNode } from 'react';
import { Ban, Eye, Globe2, Minus, Zap } from 'lucide-react';
import type { ScannerCounts, ScannerMeta } from '../types';

type Kpi = { key: string; icon: ReactNode; label: string; value: number | string; sub: string; cls: string };

export function ScannerKpis({ meta, counts }: { meta: ScannerMeta | null; counts: ScannerCounts | null }) {
  const scanned = meta?.instruments_scanned ?? 0;
  const total = meta?.instruments_total ?? 0;
  const pct = (n: number) => (total ? `${((n / total) * 100).toFixed(1)}%` : '—');
  const c = counts ?? { HIGH_INSPECTION: 0, WATCHING: 0, NEUTRAL: 0, EXCLUDED: 0 };
  const kpis: Kpi[] = [
    {
      key: 'scanned',
      icon: <Globe2 size={20} />,
      label: 'Instruments Scanned',
      value: scanned,
      sub: meta ? `${meta.fx_pairs} FX + XAUUSD` : '—',
      cls: 'is-total',
    },
    { key: 'high', icon: <Zap size={20} />, label: 'High Inspection', value: c.HIGH_INSPECTION, sub: pct(c.HIGH_INSPECTION), cls: 'is-high' },
    { key: 'watch', icon: <Eye size={20} />, label: 'Watching', value: c.WATCHING, sub: pct(c.WATCHING), cls: 'is-watch' },
    { key: 'neutral', icon: <Minus size={20} />, label: 'Neutral', value: c.NEUTRAL, sub: pct(c.NEUTRAL), cls: 'is-neutral' },
    { key: 'excluded', icon: <Ban size={20} />, label: 'Excluded', value: c.EXCLUDED, sub: pct(c.EXCLUDED), cls: 'is-excluded' },
  ];
  return (
    <section className="ms-kpis" aria-label="Scanner summary">
      {kpis.map((k) => (
        <div key={k.key} className={`ms-kpi ${k.cls}`}>
          <span className="ms-kpi-icon" aria-hidden>
            {k.icon}
          </span>
          <div>
            <span className="ms-kpi-label">{k.label}</span>
            <strong>{meta ? k.value : '—'}</strong>
            <small>{k.sub}</small>
          </div>
        </div>
      ))}
    </section>
  );
}

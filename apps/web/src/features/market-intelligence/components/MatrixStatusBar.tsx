import { CheckCircle2, Clock, Database, Layers } from 'lucide-react';
import type { MatrixMeta } from '../types';
import { utcParts } from './StrengthPageHeader';

export function MatrixStatusBar({ meta }: { meta: MatrixMeta }) {
  const closed = meta.closed_bar_only;
  const calc = meta.last_calculated_at ? utcParts(meta.last_calculated_at) : null;
  const ts = calc ? `${calc.date}, ${calc.time}` : '—';
  const loaded = meta.pairs_loaded ?? 0;
  const total = meta.pairs_total ?? 28;

  return (
    <footer className="si-matrix-footer" role="status">
      <span className="si-footer-item">
        <CheckCircle2 size={14} className="ok" aria-hidden />
        {closed ? (
          <>
            Closed bars only: <strong>Yes</strong>
          </>
        ) : (
          <>
            Basis: <strong>Current price vs previous close (EarnForex)</strong>
          </>
        )}
      </span>
      <span className="si-footer-item">
        <Clock size={14} aria-hidden />
        Last calculated: <strong>{ts}</strong>
      </span>
      <span className="si-footer-item">
        <Database size={14} aria-hidden />
        Source: <strong>MT5 ({meta.mt5_server || 'MetaTrader 5'})</strong>
      </span>
      <span className={`si-footer-item ${loaded >= total ? 'mi-ok' : 'mi-warn'}`}>
        <Layers size={14} aria-hidden />
        <strong>
          {loaded}/{total}
        </strong>{' '}
        pairs loaded
      </span>
    </footer>
  );
}

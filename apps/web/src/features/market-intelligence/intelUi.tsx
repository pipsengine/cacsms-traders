import { History } from 'lucide-react';
import type { Coverage, HistoryPeriod } from './types';
import { fmtUtc } from './components/TimeSeriesChart';

export const SI_CURRENCIES = ['USD', 'EUR', 'GBP', 'JPY', 'CHF', 'CAD', 'AUD', 'NZD'] as const;
export const HISTORY_PERIODS: HistoryPeriod[] = ['24H', '7D', '1M', '3M', '6M', 'YTD'];

export const CURRENCY_COLORS: Record<string, string> = {
  USD: '#2563eb',
  EUR: '#7c3aed',
  GBP: '#db2777',
  JPY: '#dc2626',
  CHF: '#ea580c',
  CAD: '#ca8a04',
  AUD: '#16a34a',
  NZD: '#0891b2',
};

export type BadgeTone = 'pos' | 'neg' | 'neu' | 'info' | 'warn' | 'strong' | 'muted';

const TONES: Record<string, BadgeTone> = {
  STRENGTHENING: 'pos',
  WEAKENING: 'neg',
  STABLE: 'neu',
  ACCELERATING: 'info',
  DECELERATING: 'warn',
  INSUFFICIENT: 'muted',
  NO_HISTORY: 'muted',
  STRONG_DIVERGENCE: 'strong',
  DIVERGENCE: 'info',
  MODERATE: 'warn',
  BALANCED: 'neu',
  EXPANDING: 'info',
  CONTRACTING: 'warn',
  REVERSING: 'neg',
  ALIGNED: 'pos',
  PARTIAL: 'warn',
  CONFLICTED: 'neg',
  NEUTRAL: 'neu',
  EXPANDING_DIVERGENCE: 'info',
  CONTRACTING_DIVERGENCE: 'warn',
  CONVERGENCE: 'warn',
  EQUILIBRIUM: 'neu',
  REVERSAL: 'neg',
  PERSISTENT_DIVERGENCE: 'strong',
  STABLE_DIVERGENCE: 'neu',
  AGREE: 'pos',
  DISAGREE: 'neg',
  INCONCLUSIVE: 'muted',
  PERSISTENT: 'strong',
  DEVELOPING: 'warn',
  UNSTABLE: 'neg',
  WIDENING: 'info',
  NARROWING: 'warn',
  FLAT: 'neu',
};

export function IntelBadge({ k, label, title }: { k: string; label: string; title?: string }) {
  return (
    <span className={`si-badge si-badge--${TONES[k] ?? 'neu'}`} title={title}>
      {label}
    </span>
  );
}

export function signed(v: number | null | undefined, digits = 1) {
  if (v === null || v === undefined) return '—';
  return `${v > 0 ? '+' : ''}${v.toFixed(digits)}`;
}

export function ageText(minutes: number | null | undefined) {
  if (minutes === null || minutes === undefined) return null;
  if (minutes < 90) return `${Math.round(minutes)} min`;
  if (minutes < 48 * 60) return `${(minutes / 60).toFixed(1)} h`;
  return `${(minutes / 1440).toFixed(1)} days`;
}

export function PeriodPills({ value, onChange }: { value: HistoryPeriod; onChange: (p: HistoryPeriod) => void }) {
  return (
    <div className="si-pills" role="tablist" aria-label="Period">
      {HISTORY_PERIODS.map((p) => (
        <button
          key={p}
          type="button"
          role="tab"
          aria-selected={p === value}
          className={p === value ? 'active' : ''}
          onClick={() => onChange(p)}
        >
          {p}
        </button>
      ))}
    </div>
  );
}

export function CoverageNotice({ coverage, period }: { coverage: Coverage; period: HistoryPeriod }) {
  if (coverage.complete) return null;
  return (
    <div className="si-banner si-banner--info" role="status">
      <History size={14} />
      <span>
        {coverage.first_available
          ? `Incomplete history — persisted snapshots begin ${fmtUtc(coverage.first_available)}, covering ${coverage.pct.toFixed(0)}% of the ${period} window. Missing time is left empty, not estimated.`
          : `No persisted strength history yet for the ${period} window.`}
      </span>
    </div>
  );
}

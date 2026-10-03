import { Minus, TrendingDown, TrendingUp } from 'lucide-react';
import type { CurrencySummary } from '../types';
import { CurrencyFlag } from './CurrencyFlag';
import { StrengthSparkline } from './StrengthSparkline';

function signed(n: number) {
  return `${n > 0 ? '+' : ''}${n.toFixed(1)}`;
}

export function CurrencyStrengthStrip({ cards, stale = false }: { cards: CurrencySummary[]; stale?: boolean }) {
  if (!cards.length) return null;
  return (
    <div className={`si-currency-strip ${stale ? 'is-stale' : ''}`} role="list" aria-label="Currency strength summary">
      {cards.map((c) => {
        const tone = c.classification.tone;
        const DeltaIcon = c.change > 0 ? TrendingUp : c.change < 0 ? TrendingDown : Minus;
        const deltaDir = c.change > 0 ? 'up' : c.change < 0 ? 'down' : 'flat';
        return (
          <article key={c.currency} className={`si-currency-card si-currency-card--${tone}`} role="listitem">
            <div className="si-currency-card-head">
              <CurrencyFlag code={c.currency} size={22} />
              <strong>{c.currency}</strong>
              <span className="si-currency-rank">#{c.rank}</span>
            </div>
            <div className="si-currency-score-row">
              <span className="si-currency-score">{c.score.toFixed(1)}</span>
              <span className="si-currency-score-label">AVG</span>
            </div>
            <span className={`si-currency-pill si-currency-pill--${tone}`}>{c.classification.label}</span>
            <StrengthSparkline points={c.sparkline} tone={tone} />
            <div className={`si-currency-delta ${deltaDir}`}>
              <DeltaIcon size={12} aria-hidden />
              <span>
                {signed(c.change)} ({signed(c.change_pct)}%)
              </span>
            </div>
          </article>
        );
      })}
    </div>
  );
}

import type { AvgRankRow } from '../types';
import { strengthTone } from './StrengthCell';

export function AvgStrengthRanking({ rows }: { rows: AvgRankRow[] }) {
  const sorted = [...rows].sort((a, b) => a.rank - b.rank);
  return (
    <section className="mi-card mi-avg-card">
      <header>
        <div>
          <span className="mi-eyebrow">Aggregate view</span>
          <h2>Multi-timeframe average strength</h2>
        </div>
        <span className="mi-note">Ranked by AVG · strongest to weakest</span>
      </header>
      <ol className="mi-avg-list">
        {sorted.map((r) => {
          const tone = strengthTone(r.value);
          return (
            <li key={r.currency}>
              <span className="mi-avg-rank">{r.rank}</span>
              <strong>{r.currency}</strong>
              <span className="mi-avg-val" style={{ color: tone.fg, background: tone.bg }}>
                {r.value >= 0 ? '+' : ''}
                {r.value.toFixed(4)}
              </span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

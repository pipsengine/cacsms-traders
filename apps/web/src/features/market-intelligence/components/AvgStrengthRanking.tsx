import { Trophy } from 'lucide-react';
import type { AvgRankRow } from '../types';
import { TONE_BAR } from '../strengthHeatmap';
import { CurrencyFlag } from './CurrencyFlag';

export function AvgStrengthRanking({ rows }: { rows: AvgRankRow[] }) {
  return (
    <section className="mi-avg-panel">
      <header className="si-card-head">
        <span className="si-icon-block" aria-hidden>
          <Trophy size={16} />
        </span>
        <div>
          <h3>Multi-Timeframe Average Strength</h3>
          <p>Currencies ranked by overall strength (AVG).</p>
        </div>
      </header>
      <table className="mi-avg-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Currency</th>
            <th>AVG</th>
            <th>Strength</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.currency}>
              <td className="mi-avg-rank">{r.rank}</td>
              <td>
                <span className="mi-avg-currency">
                  <CurrencyFlag code={r.currency} />
                  {r.currency}
                </span>
              </td>
              <td>{r.score === null ? '—' : <strong>{r.score.toFixed(1)}</strong>}</td>
              <td>
                {r.score === null || !r.classification ? null : (
                  <div className="mi-strength-bar" title={r.classification.label}>
                    <i
                      style={{
                        width: `${Math.max(4, Math.min(100, r.score))}%`,
                        background: TONE_BAR[r.classification.tone],
                      }}
                    />
                  </div>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

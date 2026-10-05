import { ArrowDown, ArrowUp } from 'lucide-react';
import type { MatrixCurrencyRow } from '../types';
import { heatmapStyle } from '../strengthHeatmap';
import { CurrencyFlag } from './CurrencyFlag';

export const MATRIX_TFS = ['YTD', 'Q', 'MN', 'W', 'D1', 'H8', 'H1', 'M15', 'M5', 'M1', 'AVG'] as const;

const CURRENCIES = ['USD', 'JPY', 'CHF', 'EUR', 'GBP', 'CAD', 'AUD', 'NZD'] as const;

export const CURRENCY_FILTER_OPTIONS = ['ALL', ...CURRENCIES] as const;

export type SortDir = 'desc' | 'asc';
export type ValueMode = 'score' | 'raw';

function formatRaw(v: number) {
  return `${v > 0 ? '+' : ''}${v.toFixed(4)}`;
}

function MatrixCell({
  score,
  raw,
  quality,
  avg,
  mode,
}: {
  score: number | undefined;
  raw: number | undefined;
  quality?: string;
  avg: boolean;
  mode: ValueMode;
}) {
  if (score === undefined || quality === 'MISSING' || quality === 'INVALID') {
    return (
      <span className="mi-heat-cell mi-heat-empty" title="No provider history for this timeframe">
        —
      </span>
    );
  }
  const rawText = raw === undefined ? '' : formatRaw(raw);
  return (
    <span
      className={`mi-heat-cell ${avg ? 'mi-heat-avg' : ''} ${quality === 'PARTIAL' ? 'mi-heat-partial' : ''} ${
        mode === 'raw' ? 'mi-heat-raw' : ''
      }`}
      style={avg ? undefined : heatmapStyle(score)}
      title={mode === 'raw' ? `Score ${score.toFixed(1)}` : `% change ${rawText}`}
    >
      {mode === 'raw' && raw !== undefined ? rawText : score.toFixed(1)}
    </span>
  );
}

export function StrengthMatrixTable({
  matrix,
  sortBy,
  sortDir,
  onSortBy,
  currencyFilter,
  valueMode,
}: {
  matrix: MatrixCurrencyRow[];
  sortBy: string;
  sortDir: SortDir;
  onSortBy: (tf: string) => void;
  currencyFilter: string;
  valueMode: ValueMode;
}) {
  const filtered = currencyFilter === 'ALL' ? matrix : matrix.filter((r) => r.currency === currencyFilter);
  const key = (r: MatrixCurrencyRow) =>
    r.scores[sortBy] === undefined ? undefined : valueMode === 'raw' ? r.values[sortBy] : r.scores[sortBy];
  const rows = [...filtered].sort((a, b) => {
    const av = key(a);
    const bv = key(b);
    if (av === undefined && bv === undefined) return a.currency.localeCompare(b.currency);
    if (av === undefined) return 1;
    if (bv === undefined) return -1;
    return sortDir === 'desc' ? bv - av : av - bv;
  });

  return (
    <div className="mi-table-wrap mi-matrix-heat-wrap">
      <table className="mi-table matrix mi-matrix-heat">
        <thead>
          <tr>
            <th className="mi-col-currency">Currency</th>
            {MATRIX_TFS.map((tf) => (
              <th key={tf} className={tf === 'AVG' ? 'mi-col-avg' : undefined}>
                <button
                  type="button"
                  className={`mi-th-sort ${sortBy === tf ? 'active' : ''}`}
                  onClick={() => onSortBy(tf)}
                  aria-label={`Sort by ${tf}`}
                  aria-sort={sortBy === tf ? (sortDir === 'desc' ? 'descending' : 'ascending') : undefined}
                >
                  {tf}
                  {sortBy === tf ? (
                    sortDir === 'desc' ? (
                      <ArrowDown size={11} aria-hidden />
                    ) : (
                      <ArrowUp size={11} aria-hidden />
                    )
                  ) : null}
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.currency}>
              <td className="mi-currency-cell">
                <CurrencyFlag code={row.currency} />
                <b>{row.currency}</b>
              </td>
              {MATRIX_TFS.map((tf) => (
                <td key={tf} className={tf === 'AVG' ? 'mi-col-avg' : undefined}>
                  <MatrixCell
                    score={row.scores[tf]}
                    raw={row.values[tf]}
                    quality={row.quality[tf]}
                    avg={tf === 'AVG'}
                    mode={valueMode}
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

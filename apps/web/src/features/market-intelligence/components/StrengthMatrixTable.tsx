import type { MatrixCurrencyRow, MatrixMeta } from '../types';
import { StrengthCell } from './StrengthCell';

export const MATRIX_TFS = ['YTD', 'Q', 'MN', 'W1', 'D1', 'H8', 'H1', 'M15', 'M5', 'M1', 'AVG'] as const;

export function StrengthMatrixTable({
  matrix,
  meta,
  sortBy,
  onSortBy,
}: {
  matrix: MatrixCurrencyRow[];
  meta: MatrixMeta;
  sortBy: string;
  onSortBy: (tf: string) => void;
}) {
  const strongest = meta.currency_order[0];
  const weakest = meta.currency_order[meta.currency_order.length - 1];

  return (
    <div className="mi-table-wrap">
      <table className="mi-table matrix mi-matrix-csm">
        <thead>
          <tr>
            <th>Currency</th>
            {MATRIX_TFS.map((tf) => (
              <th key={tf}>
                <button
                  type="button"
                  className={`mi-th-sort ${sortBy === tf ? 'active' : ''}`}
                  onClick={() => onSortBy(tf)}
                  title={sortBy === tf ? `Sorted by ${tf}` : `Sort by ${tf}`}
                >
                  {tf}
                  {sortBy === tf ? '*' : ''}
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.map((row, idx) => (
            <tr key={row.currency} className={idx === 0 || idx === matrix.length - 1 ? 'mi-extreme' : ''}>
              <td>
                <b>{row.currency}</b>
                {row.currency === strongest && <small className="mi-tag strong">Strongest</small>}
                {row.currency === weakest && <small className="mi-tag weak">Weakest</small>}
              </td>
              {MATRIX_TFS.map((tf) => (
                <td key={tf}>
                  <StrengthCell value={row.values[tf]} quality={row.quality[tf]} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

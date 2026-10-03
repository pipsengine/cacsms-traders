import type { MatrixMeta } from '../types';

export function MatrixStatusBar({
  meta,
  loading,
  onRefresh,
}: {
  meta: MatrixMeta | null;
  loading: boolean;
  onRefresh: () => void;
}) {
  const closed = meta?.closed_bar_only ?? true;
  const ts = meta?.last_calculated_at ? new Date(meta.last_calculated_at).toLocaleString() : '—';
  return (
    <div className="mi-status-bar" role="status">
      <span>
        <i className={`mi-dot ${meta?.historical_ok ? 'ok' : 'warn'}`} /> Closed bars only: {closed ? 'yes' : 'no'}
      </span>
      <span>Last calculated: {ts}</span>
      <span>Source: {meta?.data_source ?? 'MT5'}</span>
      <span>
        MT5:{' '}
        <b className={meta?.mt5_connected ? 'mi-ok' : 'mi-warn'}>
          {meta?.mt5_connected ? 'Connected' : 'Disconnected'}
        </b>
      </span>
      {meta?.stale && <span className="mi-warn">Stale data</span>}
      {!meta?.historical_ok && meta?.missing_history?.length ? (
        <span className="mi-warn">Missing history ({meta.missing_history.length})</span>
      ) : null}
      <button type="button" className="mi-refresh-btn" disabled={loading} onClick={onRefresh}>
        {loading ? 'Refreshing…' : 'Recalculate matrix'}
      </button>
    </div>
  );
}

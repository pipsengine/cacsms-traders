import type { ReactNode } from 'react';
import { AlertTriangle, Loader2, PlugZap, RefreshCw } from 'lucide-react';
import type { MatrixMeta } from '../types';
import { ErrorState } from './ErrorState';
import { LoadingSkeleton } from './LoadingSkeleton';

type BannerMeta = Pick<
  MatrixMeta,
  | 'pairs_loaded'
  | 'pairs_total'
  | 'missing_pairs'
  | 'engine_state'
  | 'stale_reason'
  | 'engine_error'
  | 'historical_ok'
  | 'missing_history'
>;

/** Blocking state shown instead of a panel when no calculation is available yet. */
export function MatrixBlockingState({
  loading,
  error,
  onRetry,
  label = 'strength matrix',
  meta,
}: {
  meta?: MatrixMeta | null;
  loading: boolean;
  error: string;
  onRetry: () => void;
  label?: string;
}) {
  if (error) return <ErrorState message={error} onRetry={onRetry} />;
  if (meta && meta.engine_state !== "SYNCING" && meta.engine_state !== "READY") return (
    <div className="si-state" role="status">
      <strong>MARKET DATA UNAVAILABLE</strong>
      <p>{meta.error_code === 'CTRADER_APP_INACTIVE' ? 'cTrader provider authorization unavailable' : meta.provider_status === "AUTHORIZATION REQUIRED" ? "cTrader authorization required" : (meta.engine_error || meta.error_code || meta.engine_state)}</p>
      <p>{meta.pairs_loaded ?? 0}/{meta.pairs_total ?? 28} pairs loaded{meta.missing_pairs?.length ? ` - missing ${meta.missing_pairs.join(", ")}` : ""}</p>
      <a href="#/system-control/mt5">System Control: Market &amp; Trading Connections</a>
    </div>
  );
  return (
    <div className="si-state si-state--calc">
      <LoadingSkeleton />
      <p>
        <Loader2 size={14} className="si-spin" aria-hidden />
        {loading ? `Loading ${label}…` : 'Calculating currency strength from synchronized closed bars…'}
      </p>
    </div>
  );
}

/** Non-blocking banners shown above a panel that is available but degraded. */
export function MatrixStatusBanners({
  meta,
  error,
  hasScores,
  onRetry,
}: {
  meta: BannerMeta;
  error: string;
  hasScores: boolean;
  onRetry: () => void;
}) {
  const banners: { key: string; tone: 'warn' | 'off' | 'info'; icon: ReactNode; text: string; retry?: boolean }[] = [];
  const loaded = meta.pairs_loaded ?? 0;
  const total = meta.pairs_total ?? 28;
  const missingPairs = meta.missing_pairs ?? [];
  const syncing = meta.engine_state === 'SYNCING' || meta.engine_state === 'STARTING';

  if (error) {
    banners.push({
      key: 'api',
      tone: 'off',
      icon: <AlertTriangle size={14} />,
      text: 'API request failed — showing the last received calculation.',
      retry: true,
    });
  }
  if (meta.stale_reason === 'PROVIDER_DISCONNECTED') {
    banners.push({
      key: 'provider',
      tone: 'off',
      icon: <PlugZap size={14} />,
      text: 'Market data disconnected — values below are the last valid calculation and are stale. Reconnect in System Control.',
    });
  } else if (meta.stale_reason === 'ENGINE_STALLED') {
    banners.push({
      key: 'stale',
      tone: 'warn',
      icon: <AlertTriangle size={14} />,
      text: `Stale data — the strength engine has not refreshed recently${meta.engine_error ? ` (${meta.engine_error})` : ''}.`,
    });
  }
  if (meta.engine_state === 'ERROR' && meta.engine_error && meta.stale_reason !== 'ENGINE_STALLED') {
    banners.push({ key: 'err', tone: 'warn', icon: <AlertTriangle size={14} />, text: `Engine error: ${meta.engine_error}` });
  }
  if (syncing) {
    banners.push({
      key: 'sync',
      tone: 'info',
      icon: <RefreshCw size={14} className="si-spin" />,
      text: 'Syncing closed-bar history from the active provider — calculation updates automatically.',
    });
  }
  if (loaded < total) {
    const list = missingPairs.slice(0, 10).join(', ');
    banners.push({
      key: 'basket',
      tone: 'warn',
      icon: <AlertTriangle size={14} />,
      text: `Incomplete basket: ${loaded}/${total} pairs loaded${list ? ` — missing ${list}${missingPairs.length > 10 ? '…' : ''}` : ''}.`,
    });
  } else if (!meta.historical_ok && meta.missing_history.length) {
    const tfs = Array.from(new Set(meta.missing_history.map((m) => m.timeframe))).join(', ');
    banners.push({
      key: 'hist',
      tone: 'info',
      icon: <AlertTriangle size={14} />,
      text: `Missing history on ${tfs} — affected cells are shown as “—”.`,
    });
  }
  if (!hasScores && !syncing) {
    banners.push({
      key: 'empty',
      tone: 'info',
      icon: <AlertTriangle size={14} />,
      text: 'No strength history available yet — scores appear once closed bars are stored.',
    });
  }

  if (!banners.length) return null;
  return (
    <div className="si-banners">
      {banners.map((b) => (
        <div key={b.key} className={`si-banner si-banner--${b.tone}`} role="status">
          {b.icon}
          <span>{b.text}</span>
          {b.retry ? (
            <button type="button" onClick={onRetry}>
              Retry
            </button>
          ) : null}
        </div>
      ))}
    </div>
  );
}

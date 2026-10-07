import { useMemo, type ReactNode } from 'react';
import { InstrumentIcon } from '../../market-scanner/components/InstrumentIcon';
import { StructureChart } from '../../market-structure/components/StructureChart';
import { buildOverlay, futureBarsFor, legendFor, type GroupKey, type OverlayMode, DEFAULT_GROUPS } from '../overlay';
import type { Outlook, VCandle } from '../types';
import { CANDLE_LIMIT, TFS, type OutlookTf } from './shared';

export type CandleState = { candles: VCandle[]; loading: boolean; error: string | null };

export function OutlookChart({
  o,
  tf,
  onTf,
  candles,
  title,
  mode,
  height,
  groups = DEFAULT_GROUPS,
  onPick,
  selected,
  footer,
}: {
  o: Outlook;
  tf: OutlookTf;
  onTf: (t: OutlookTf) => void;
  candles: CandleState;
  title: string;
  mode: OverlayMode;
  height: number;
  groups?: GroupKey[];
  onPick?: (id: string) => void;
  selected?: string | null;
  footer?: ReactNode;
}) {
  const framed = useMemo(() => candles.candles.slice(-CANDLE_LIMIT[tf]), [candles.candles, tf]);
  const overlay = useMemo(() => buildOverlay(o, tf, framed, groups, mode), [o, tf, framed, groups, mode]);
  const future = useMemo(() => futureBarsFor(o, tf, framed), [o, tf, framed]);
  return (
    <div className="mao-chart-wrap">
      <StructureChart
        symbol={o.symbol}
        title={title}
        tf={tf}
        candles={candles.candles}
        digits={o.digits}
        lastPrice={o.price}
        height={height}
        loading={candles.loading}
        error={candles.error ?? undefined}
        overlay={overlay}
        futureBars={future}
        zoomable
        defaultSpan={CANDLE_LIMIT[tf]}
        onPick={onPick}
        selected={selected}
        legend={legendFor(mode)}
        className="mao-chart"
        heading={
          <strong>
            <InstrumentIcon base={o.symbol.slice(0, 3)} quote={o.symbol.slice(3, 6)} size="sm" /> {o.symbol} – {title}
          </strong>
        }
        actions={
          <select className="mao-tf-select" value={tf} onChange={(e) => onTf(e.target.value as OutlookTf)} aria-label="Chart timeframe">
            {TFS.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        }
      />
      {footer}
    </div>
  );
}

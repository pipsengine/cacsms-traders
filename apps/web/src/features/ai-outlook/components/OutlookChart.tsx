import { useMemo, type ReactNode } from 'react';
import { InstrumentIcon } from '../../market-scanner/components/InstrumentIcon';
import { StructureChart } from '../../market-structure/components/StructureChart';
import type { LiveState } from '../../market-structure/live';
import { buildOverlay, futureBarsFor, legendFor, type GroupKey, type OverlayMode, DEFAULT_GROUPS } from '../overlay';
import type { Outlook, VCandle } from '../types';
import { SchPane } from './SchPane';
import { CANDLE_LIMIT, GOLD_TFS, TFS, type OutlookTf } from './shared';

/** Closed candles plus the live forming bar; ``price`` is the latest tick (null when the feed has no quote). */
export type CandleState = { candles: VCandle[]; loading: boolean; error: string | null; price?: number | null; live?: LiveState; forming?: boolean };

export const barLabel = (c: CandleState) => (c.forming ? 'forming bar · live' : undefined);

export function LivePill({ live }: { live?: LiveState }) {
  if (!live) return null;
  return (
    <span className={`mao-live is-${live.tone}`} title={live.title}>
      <i />
      {live.label}
    </span>
  );
}

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
  tfs,
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
  tfs?: readonly OutlookTf[];
}) {
  const choices = tfs ?? (o.horizon === 'H8' ? GOLD_TFS : TFS);
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
        lastPrice={candles.price ?? candles.candles.at(-1)?.c ?? o.price}
        barLabel={barLabel(candles)}
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
            <InstrumentIcon base={o.symbol.slice(0, 3)} quote={o.symbol.slice(3, 6)} size="sm" /> {o.symbol} – {title} <LivePill live={candles.live} />
          </strong>
        }
        actions={
          <select className="mao-tf-select" value={tf} onChange={(e) => onTf(e.target.value as OutlookTf)} aria-label="Chart timeframe">
            {choices.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        }
      />
      {tf === 'W' && o.horizon === 'WEEKLY' && o.sch?.series?.length ? <SchPane series={o.sch.series} /> : null}
      {footer}
    </div>
  );
}

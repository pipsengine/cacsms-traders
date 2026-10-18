import { useEffect, useRef } from 'react';
import { createChart, type UTCTimestamp } from 'lightweight-charts';
import type { Candle } from './types';

export function AtrPane({ candles }: { candles: Candle[] }) {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!host.current || candles.length < 20) return;
    const period = 14;
    const atr: number[] = [];
    for (let i = 0; i < candles.length; i++) {
      if (i === 0) {
        atr.push(candles[i].high - candles[i].low);
        continue;
      }
      const c = candles[i];
      const p = candles[i - 1];
      const tr = Math.max(c.high - c.low, Math.abs(c.high - p.close), Math.abs(c.low - p.close));
      if (i < period) {
        atr.push((atr[i - 1] * i + tr) / (i + 1));
      } else {
        atr.push((atr[i - 1] * (period - 1) + tr) / period);
      }
    }
    const chart = createChart(host.current, {
      width: host.current.clientWidth,
      height: 72,
      layout: { background: { color: '#fafcff' }, textColor: '#94a3b8', fontSize: 10 },
      grid: { vertLines: { visible: false }, horzLines: { color: '#eef2f8' } },
      rightPriceScale: { borderVisible: false },
      timeScale: { visible: false },
      handleScroll: false,
      handleScale: false,
    });
    const line = chart.addLineSeries({ color: '#0d9488', lineWidth: 2, priceLineVisible: false });
    line.setData(candles.map((c, i) => ({ time: c.time as UTCTimestamp, value: atr[i] })));
    chart.timeScale().fitContent();
    const ro = new ResizeObserver(() => {
      if (host.current) chart.applyOptions({ width: host.current.clientWidth });
    });
    ro.observe(host.current);
    return () => {
      ro.disconnect();
      chart.remove();
    };
  }, [candles]);

  if (candles.length < 20) return <div className="aca-rsi-empty">ATR (14) — need more bars</div>;
  return (
    <div className="aca-rsi-wrap">
      <div className="aca-rsi-label">ATR (14)</div>
      <div className="aca-rsi-host" ref={host} style={{ height: 72 }} />
    </div>
  );
}

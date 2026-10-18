import { useEffect, useRef } from 'react';
import { createChart, type UTCTimestamp } from 'lightweight-charts';
import type { Candle } from './types';

export function RsiPane({ candles }: { candles: Candle[] }) {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!host.current || candles.length < 16) return;
    const chart = createChart(host.current, {
      width: host.current.clientWidth,
      height: 96,
      layout: { background: { color: '#fafcff' }, textColor: '#94a3b8', fontSize: 10 },
      grid: { vertLines: { visible: false }, horzLines: { color: '#eef2f8' } },
      rightPriceScale: { borderVisible: false },
      timeScale: { visible: false },
      handleScroll: false,
      handleScale: false,
    });
    const line = chart.addLineSeries({ color: '#7c3aed', lineWidth: 2, priceLineVisible: false, lastValueVisible: true });
    const period = 14;
    const rsi: { time: UTCTimestamp; value: number }[] = [];
    for (let i = period; i < candles.length; i++) {
      let gain = 0;
      let loss = 0;
      for (let j = i - period + 1; j <= i; j++) {
        const d = candles[j].close - candles[j - 1].close;
        if (d >= 0) gain += d;
        else loss -= d;
      }
      const rs = loss === 0 ? 100 : gain / loss;
      const v = 100 - 100 / (1 + rs);
      rsi.push({ time: candles[i].time as UTCTimestamp, value: v });
    }
    line.setData(rsi);
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

  if (candles.length < 16) {
    return <div className="aca-rsi-empty">RSI (14) — need more closed bars</div>;
  }
  return (
    <div className="aca-rsi-wrap">
      <div className="aca-rsi-label">RSI (14)</div>
      <div className="aca-rsi-host" ref={host} />
    </div>
  );
}

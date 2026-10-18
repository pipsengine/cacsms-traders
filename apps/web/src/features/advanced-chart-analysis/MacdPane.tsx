import { useEffect, useRef } from 'react';
import { createChart, type UTCTimestamp } from 'lightweight-charts';
import type { Candle } from './types';
import { emaSeries } from './chartMath';

export function MacdPane({ candles }: { candles: Candle[] }) {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!host.current || candles.length < 30) return;
    const chart = createChart(host.current, {
      width: host.current.clientWidth,
      height: 88,
      layout: { background: { color: '#fafcff' }, textColor: '#94a3b8', fontSize: 10 },
      grid: { vertLines: { visible: false }, horzLines: { color: '#eef2f8' } },
      rightPriceScale: { borderVisible: false },
      timeScale: { visible: false },
      handleScroll: false,
      handleScale: false,
    });
    const closes = candles.map((c) => c.close);
    const ema12 = emaSeries(candles, 12).map((x) => x.value);
    const ema26 = emaSeries(candles, 26).map((x) => x.value);
    const macd = closes.map((_, i) => ema12[i] - ema26[i]);
    const signal = emaSeries(
      macd.map((v, i) => ({ ...candles[i], close: v })),
      9,
    ).map((x) => x.value);
    const hist = chart.addHistogramSeries({ priceFormat: { type: 'price', precision: 5, minMove: 0.00001 } });
    hist.setData(
      candles.map((c, i) => ({
        time: c.time as UTCTimestamp,
        value: macd[i] - signal[i],
        color: macd[i] >= signal[i] ? '#86efac' : '#fca5a5',
      })),
    );
    const macdLine = chart.addLineSeries({ color: '#2563eb', lineWidth: 1, priceLineVisible: false });
    macdLine.setData(candles.map((c, i) => ({ time: c.time as UTCTimestamp, value: macd[i] })));
    const sigLine = chart.addLineSeries({ color: '#f97316', lineWidth: 1, priceLineVisible: false });
    sigLine.setData(candles.map((c, i) => ({ time: c.time as UTCTimestamp, value: signal[i] })));
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

  if (candles.length < 30) return <div className="aca-rsi-empty">MACD — need more bars</div>;
  return (
    <div className="aca-rsi-wrap">
      <div className="aca-rsi-label">MACD (12, 26, 9)</div>
      <div className="aca-rsi-host" ref={host} style={{ height: 88 }} />
    </div>
  );
}

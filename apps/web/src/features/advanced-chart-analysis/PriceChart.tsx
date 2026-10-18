import { useEffect, useRef, useState } from 'react';

import {

  createChart,

  CrosshairMode,

  LineStyle,

  type IChartApi,

  type ISeriesApi,

  type MouseEventParams,

  type UTCTimestamp,

} from 'lightweight-charts';

import { fibPrices, snapToOhlc, supertrend } from './chartMath';

import type { Candle, Drawing, Overlay } from './types';



type Props = {

  candles: Candle[];

  drawings: Drawing[];

  overlays: Overlay[];

  tool: string;

  symbol: string;

  timeframe: string;

  onDrawing: (d: Drawing) => void;

  showVolume: boolean;

  showEMA: boolean;

  showSupertrend: boolean;

  snapEnabled: boolean;

};



function linePriceAt(p1: { time: number; price: number }, p2: { time: number; price: number }, time: number): number {

  if (p1.time === p2.time) return p1.price;

  const t = (time - p1.time) / (p2.time - p1.time);

  return p1.price + (p2.price - p1.price) * t;

}



export function PriceChart({

  candles,

  drawings,

  overlays,

  tool,

  symbol,

  timeframe,

  onDrawing,

  showVolume,

  showEMA,

  showSupertrend,

  snapEnabled,

}: Props) {

  const host = useRef<HTMLDivElement>(null);

  const chart = useRef<IChartApi | null>(null);

  const series = useRef<ISeriesApi<'Candlestick'> | null>(null);

  const toolRef = useRef(tool);

  const onDrawingRef = useRef(onDrawing);

  const candlesRef = useRef(candles);

  const snapRef = useRef(snapEnabled);

  const [revision, setRevision] = useState(0);

  const [pending, setPending] = useState<{ time: number; price: number }[]>([]);

  const [hover, setHover] = useState<{ time: number; price: number } | null>(null);
  const fitChartNext = useRef(true);



  toolRef.current = tool;

  onDrawingRef.current = onDrawing;

  candlesRef.current = candles;

  snapRef.current = snapEnabled;



  useEffect(() => {

    setPending([]);

  }, [tool, symbol, timeframe]);

  useEffect(() => {

    fitChartNext.current = true;

  }, [symbol, timeframe]);



  useEffect(() => {

    if (!host.current) return;

    const measure = () => {
      if (!host.current) return { w: 0, h: 280 };
      const rect = host.current.getBoundingClientRect();
      return {
        w: Math.max(host.current.clientWidth, rect.width),
        h: Math.max(host.current.clientHeight, rect.height, 280),
      };
    };

    const { w: initW, h: initH } = measure();

    const c = createChart(host.current, {

      width: initW,

      height: initH,

      layout: { background: { color: '#ffffff' }, textColor: '#64748b', fontSize: 11 },

      grid: { vertLines: { color: '#edf2f8' }, horzLines: { color: '#edf2f8' } },

      rightPriceScale: { borderColor: '#e2e8f0', minimumWidth: 72, autoScale: true },

      timeScale: { borderColor: '#e2e8f0', timeVisible: true, secondsVisible: false },

      crosshair: { mode: CrosshairMode.Normal },

      handleScroll: true,

      handleScale: true,

    });

    chart.current = c;

    const s = c.addCandlestickSeries({

      upColor: '#10b981',

      downColor: '#ef4444',

      borderVisible: false,

      wickUpColor: '#10b981',

      wickDownColor: '#ef4444',

    });

    series.current = s;

    const resize = new ResizeObserver(() => {

      if (!host.current) return;
      const { w, h } = measure();
      c.applyOptions({ width: w, height: h });

      setRevision((x) => x + 1);

    });

    resize.observe(host.current);

    const pickPoint = (p: MouseEventParams) => {

      if (p.time == null || !p.point || !series.current) return null;

      const price = series.current.coordinateToPrice(p.point.y);

      if (price === null) return null;

      let point = { time: Number(p.time as number), price: Number(price) };

      if (snapRef.current) point = snapToOhlc(candlesRef.current, point.time, point.price);

      return point;

    };

    const click = (p: MouseEventParams) => {

      const point = pickPoint(p);

      if (!point) return;

      const t = toolRef.current;

      if (t === 'cursor') return;

      if (t === 'horizontal' || t === 'text') {

        onDrawingRef.current({

          id: crypto.randomUUID(),

          symbol,

          timeframe,

          kind: t,

          points: [point],

          color: t === 'horizontal' ? '#2563eb' : '#334155',

          label: t === 'text' ? 'Note' : '',

        });

        return;

      }

      if (t === 'channel') {

        setPending((old) => {

          const next = [...old, point];

          if (next.length < 3) return next;

          onDrawingRef.current({

            id: crypto.randomUUID(),

            symbol,

            timeframe,

            kind: 'channel',

            points: next,

            color: '#7c3aed',

          });

          return [];

        });

        return;

      }

      setPending((old) => {

        if (old.length === 0) return [point];

        onDrawingRef.current({

          id: crypto.randomUUID(),

          symbol,

          timeframe,

          kind: t as Drawing['kind'],

          points: [old[0], point],

          color: t === 'fibonacci' ? '#0d9488' : '#2563eb',

        });

        return [];

      });

    };

    const move = (p: MouseEventParams) => {

      const point = pickPoint(p);

      if (point) setHover(point);

    };

    c.subscribeClick(click);

    c.subscribeCrosshairMove(move);

    return () => {

      resize.disconnect();

      c.unsubscribeClick(click);

      c.unsubscribeCrosshairMove(move);

      c.remove();

      chart.current = null;

      series.current = null;

    };

  }, [symbol, timeframe]);



  useEffect(() => {

    if (!chart.current || !series.current) return;

    const sorted = [...candles].sort((a, b) => a.time - b.time);

    series.current.setData(

      sorted.map((c) => ({

        time: c.time as UTCTimestamp,

        open: c.open,

        high: c.high,

        low: c.low,

        close: c.close,

      })),

    );

    if (fitChartNext.current && sorted.length > 0) {

      chart.current.timeScale().fitContent();

      fitChartNext.current = false;

    }

    setRevision((x) => x + 1);

  }, [candles]);



  useEffect(() => {

    if (!chart.current || !series.current) return;

    const levels = overlays.filter((o) => o.kind === 'level');

    const lines = levels.map((o, index) =>

        series.current!.createPriceLine({

          price: o.price,

          color: o.color,

          lineWidth: 1,

          lineStyle: LineStyle.Dashed,

          axisLabelVisible: index < 6,

          title: (o.label || '').slice(0, 18),

        }),

      );

    return () => {

      for (const l of lines) {

        try {

          series.current?.removePriceLine(l);

        } catch {

          /* removed with series */

        }

      }

    };

  }, [overlays]);



  useEffect(() => {

    if (!chart.current || !candles.length) return;

    const c = chart.current;

    const aux: ISeriesApi<'Histogram' | 'Line'>[] = [];

    if (showVolume) {

      const v = c.addHistogramSeries({

        priceScaleId: 'vol',

        priceFormat: { type: 'volume' },

        lastValueVisible: false,

        priceLineVisible: false,

      });

      c.priceScale('vol').applyOptions({ scaleMargins: { top: 0.83, bottom: 0 } });

      v.setData(

        candles.map((x) => ({

          time: x.time as UTCTimestamp,

          value: x.volume,

          color: x.close >= x.open ? '#a7ead8' : '#fecaca',

        })),

      );

      aux.push(v);

    }

    if (showEMA) {

      for (const period of [50, 200]) {

        const ls = c.addLineSeries({

          color: period === 50 ? '#2563eb' : '#f97316',

          lineWidth: 2,

          priceLineVisible: false,

          lastValueVisible: false,

        });

        let ema = 0;

        const k = 2 / (period + 1);

        ls.setData(

          candles.map((x, i) => {

            ema = i === 0 ? x.close : ema + (x.close - ema) * k;

            return { time: x.time as UTCTimestamp, value: ema };

          }),

        );

        aux.push(ls);

      }

    }

    if (showSupertrend) {

      const st = supertrend(candles, 10, 3);

      const up = c.addLineSeries({ color: '#10b981', lineWidth: 2, priceLineVisible: false, lastValueVisible: false });

      const down = c.addLineSeries({ color: '#ef4444', lineWidth: 2, priceLineVisible: false, lastValueVisible: false });

      up.setData(st.filter((x) => x.up).map((x) => ({ time: x.time as UTCTimestamp, value: x.value })));

      down.setData(st.filter((x) => !x.up).map((x) => ({ time: x.time as UTCTimestamp, value: x.value })));

      aux.push(up, down);

    }

    return () => {

      for (const s of aux) {

        try {

          c.removeSeries(s);

        } catch {

          /* noop */

        }

      }

    };

  }, [candles, showVolume, showEMA, showSupertrend]);



  const toXY = (p: { time: number; price: number }) => {

    const x = chart.current?.timeScale().timeToCoordinate(p.time as UTCTimestamp);

    const y = series.current?.priceToCoordinate(p.price);

    return x === null || x === undefined || y === null || y === undefined ? null : { x, y };

  };



  const renderFib = (d: Drawing) => {

    if (d.points.length < 2) return null;

    const a = toXY(d.points[0]);

    const b = toXY(d.points[1]);

    if (!a || !b) return null;

    const levels = fibPrices(d.points[0].price, d.points[1].price);

    const xLeft = Math.min(a.x, b.x);

    const xRight = Math.max(a.x, b.x);

    return (

      <g key={d.id}>

        {levels.map(({ level, price }) => {

          const y = series.current?.priceToCoordinate(price);

          if (y == null) return null;

          return (

            <g key={level}>

              <line x1={xLeft} x2="100%" y1={y} y2={y} stroke={d.color} strokeWidth="1" strokeDasharray="4 3" opacity="0.85" />

              <text x={xLeft + 4} y={y - 3} fontSize="10" fill={d.color}>

                {(level * 100).toFixed(1)}% · {price.toFixed(5)}

              </text>

            </g>

          );

        })}

        <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={d.color} strokeWidth="1" opacity="0.35" />

      </g>

    );

  };



  const renderChannel = (d: Drawing) => {

    if (d.points.length < 3) return null;

    const [p0, p1, p2] = d.points;

    const a = toXY(p0);

    const b = toXY(p1);

    const c = toXY(p2);

    if (!a || !b || !c) return null;

    const baseAtC = linePriceAt(p0, p1, p2.time);

    const offset = p2.price - baseAtC;

    const y0 = a.y;

    const y1 = b.y;

    const y0p = series.current?.priceToCoordinate(p0.price + offset);

    const y1p = series.current?.priceToCoordinate(p1.price + offset);

    if (y0p == null || y1p == null) return null;

    return (

      <g key={d.id}>

        <line x1={a.x} y1={y0} x2={b.x} y2={y1} stroke={d.color} strokeWidth="2" />

        <line x1={a.x} y1={y0p} x2={b.x} y2={y1p} stroke={d.color} strokeWidth="2" strokeDasharray="6 4" />

        <polygon

          points={`${a.x},${y0} ${b.x},${y1} ${b.x},${y1p} ${a.x},${y0p}`}

          fill={d.color}

          fillOpacity="0.08"

          stroke="none"

        />

      </g>

    );

  };



  const renderChannelBand = (d: Drawing) => {
    if (d.points.length < 4) return null;
    const pts = d.points.slice(0, 4).map(toXY);
    if (pts.some((p) => !p)) return null;
    const [u0, u1, l1, l0] = pts as { x: number; y: number }[];
    return (
      <polygon
        key={d.id}
        points={`${u0.x},${u0.y} ${u1.x},${u1.y} ${l1.x},${l1.y} ${l0.x},${l0.y}`}
        fill={d.color}
        fillOpacity={d.id.includes('fs-ch-w-') || d.id.includes('fs-ch-d1') || d.id.includes('fs-ch-mn') ? '0.06' : '0.12'}
        stroke="none"
      />
    );
  };

  const render = (d: Drawing) => {

    if (d.id.endsWith('-band')) return renderChannelBand(d);

    if (d.kind === 'fibonacci') return renderFib(d);

    if (d.kind === 'channel') return renderChannel(d);

    const a = toXY(d.points[0]);

    if (!a) return null;

    const b = d.points[1] ? toXY(d.points[1]) : null;

    if (d.kind === 'horizontal')

      return <line key={d.id} x1="0" x2="100%" y1={a.y} y2={a.y} stroke={d.color} strokeDasharray="5 4" strokeWidth="1.5" />;

    if (d.kind === 'text')

      return (

        <text key={d.id} x={a.x} y={a.y} fill={d.color} fontSize="13">

          {d.label || 'Note'}

        </text>

      );

    if (!b) return null;

    if (d.kind === 'rectangle')

      return (

        <rect

          key={d.id}

          x={Math.min(a.x, b.x)}

          y={Math.min(a.y, b.y)}

          width={Math.abs(a.x - b.x)}

          height={Math.abs(a.y - b.y)}

          fill={d.color}

          fillOpacity=".10"

          stroke={d.color}

          strokeWidth="1.5"

        />

      );

    const width = d.id.startsWith('fs-ch-') ? (d.id.includes('-mid') ? 1.5 : 2.5) : 2;
    const dash = d.id.includes('-mid') ? '6 4' : undefined;
    return (
      <line
        key={d.id}
        x1={a.x}
        y1={a.y}
        x2={b.x}
        y2={b.y}
        stroke={d.color}
        strokeWidth={width}
        strokeDasharray={dash}
        opacity={d.id.includes('fs-ch-w-') || d.id.includes('fs-ch-d1') || d.id.includes('fs-ch-mn') ? 0.65 : 1}
      />
    );

  };



  const previewDrawing = (): Drawing | null => {

    if (!hover || pending.length === 0) return null;

    const t = tool;

    if (t === 'channel') {

      if (pending.length === 1) {

        return { id: 'preview', symbol, timeframe, kind: 'trendline', points: [pending[0], hover], color: '#c4b5fd' };

      }

      if (pending.length === 2) {

        return { id: 'preview', symbol, timeframe, kind: 'channel', points: [pending[0], pending[1], hover], color: '#c4b5fd' };

      }

    }

    return { id: 'preview', symbol, timeframe, kind: t as Drawing['kind'], points: [pending[0], hover], color: '#93c5fd' };

  };



  const hint =

    pending.length === 0

      ? null

      : tool === 'channel'

        ? pending.length === 1

          ? 'Click second anchor for channel baseline'

          : 'Click third point to set channel width'

        : 'Click second point to finish · switch tool to cancel';



  return (

    <div className="chart-host" ref={host}>

      <svg className="chart-overlay" key={revision} width="100%" height="100%">

        {overlays

          .filter((o) => o.kind === 'zone' && o.price2 !== undefined)

          .map((o) => {

            const y = series.current?.priceToCoordinate(o.price);

            const y2 = series.current?.priceToCoordinate(o.price2!);

            return y == null || y2 == null ? null : (

              <g key={o.id}>

                <rect x="0" y={Math.min(y, y2)} width="100%" height={Math.abs(y - y2)} fill={o.color} fillOpacity=".10" />

                <text x="12" y={Math.min(y, y2) - 4} fontSize="11" fill={o.color}>

                  {o.label}

                </text>

              </g>

            );

          })}

        {drawings.map(render)}

        {previewDrawing() && render(previewDrawing()!)}

      </svg>

      {hint && <div className="chart-hint">{hint}</div>}

    </div>

  );

}



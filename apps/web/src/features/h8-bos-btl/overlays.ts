import type { ChartOverlays } from './components/BreakChart';
import type { H8BosBtlDetail, Point } from './types';

export const DIR_COLOR = { Bearish: '#ef4444', Bullish: '#10b981', Neutral: '#64748b' } as const;
const BOS_COLOR = '#2563eb';
const MUTED = '#94a3b8';

function zone(d: H8BosBtlDetail, from: string): ChartOverlays['zones'] {
  const ev = d.event;
  if (!ev) return [];
  const bear = ev.direction === 'Bearish';
  return [
    {
      lo: ev.retest[0],
      hi: ev.retest[1],
      from,
      color: bear ? 'rgba(244,63,94,0.08)' : 'rgba(16,185,129,0.08)',
      stroke: bear ? '#fb7185' : '#34d399',
      label: 'Retest Zone',
    },
  ];
}

function invalidation(d: H8BosBtlDetail, from?: string): ChartOverlays['hlines'] {
  return d.event ? [{ price: d.event.invalidation, from, color: MUTED, label: 'Invalidation' }] : [];
}

export function weeklyOverlays(d: H8BosBtlDetail): ChartOverlays {
  const w = d.weekly;
  const first = d.candles.W[0]?.t ?? '';
  const markers = (w.fractals ?? [])
    .filter((f) => f.t >= first)
    .map((f) => ({ t: f.t, price: f.price, kind: f.kind, color: f.kind === 'HIGH' ? '#ef4444' : '#22c55e' }));
  const hlines: ChartOverlays['hlines'] = [];
  if (w.active_high != null) hlines.push({ price: w.active_high, color: '#f87171', dash: '2 4', label: 'Fractal High' });
  if (w.active_low != null) hlines.push({ price: w.active_low, color: '#4ade80', dash: '2 4', label: 'Fractal Low' });
  return { markers, hlines };
}

export function h8Overlays(d: H8BosBtlDetail): ChartOverlays {
  const ev = d.event;
  const h8 = d.h8;
  const lines: ChartOverlays['lines'] = [];
  const hlines: ChartOverlays['hlines'] = [];
  const labels: ChartOverlays['labels'] = [];
  const markers = h8.swings.map((s) => ({ t: s.t, price: s.price, kind: s.kind, color: s.kind === 'HIGH' ? '#f97316' : '#0ea5e9' }));
  if (h8.channel) {
    const col = h8.channel.broken && ev ? DIR_COLOR[ev.direction] : '#64748b';
    lines.push({ pts: h8.channel.upper, color: col, width: 1.5 });
    lines.push({ pts: h8.channel.lower, color: col, width: 1.5 });
    const top = h8.channel.upper[0];
    labels.push({ t: top[0], price: top[1], text: 'Channel High', above: true, color: '#475569' });
  }
  const btlAbove = ev?.btl && ev.bos ? ev.btl.level >= ev.bos.level : ev?.direction === 'Bullish';
  if (ev?.btl) {
    const p = ev.btl;
    if (p.line) lines.push({ pts: [p.line[0], [p.at, p.level] as Point], color: DIR_COLOR[ev.direction], width: 2.2 });
    labels.push({ t: p.bar_open, price: p.level, text: 'BTL (Trend Line Break)', above: !!btlAbove, color: DIR_COLOR[ev.direction], boxed: true });
  }
  if (ev?.bos) {
    const p = ev.bos;
    hlines.push({ price: p.level, from: p.swing?.t, color: BOS_COLOR, label: 'BOS' });
    labels.push({
      t: p.bar_open,
      price: p.level,
      text: `BOS (Swing ${ev.direction === 'Bearish' ? 'Low' : 'High'} Break)`,
      above: ev.btl ? !btlAbove : ev.direction === 'Bearish',
      color: BOS_COLOR,
      boxed: true,
    });
  }
  if (d.developing) {
    hlines.push({ price: d.developing.level, color: '#f59e0b', label: `Developing ${d.developing.event}` });
  }
  if (!ev && !d.developing) {
    const p = h8.pending;
    if (p.swing_high != null) hlines.push({ price: p.swing_high, color: MUTED, label: 'Swing High' });
    if (p.swing_low != null) hlines.push({ price: p.swing_low, color: MUTED, label: 'Swing Low' });
  }
  return {
    lines,
    hlines: [...hlines, ...(invalidation(d, ev?.bar_open) ?? [])],
    zones: ev ? zone(d, ev.bar_open) : [],
    markers,
    labels,
  };
}

export function h1Overlays(d: H8BosBtlDetail): ChartOverlays {
  const seq = new Set((d.h1.sequence ?? []).map((s) => s.t + s.label));
  const labels = d.h1.labels.map((l) => ({
    t: l.t,
    price: l.price,
    text: l.label,
    above: l.kind === 'HIGH',
    color: seq.has(l.t + l.label) ? DIR_COLOR[d.direction] : '#1e3a8a',
  }));
  for (const s of d.h1.sequence ?? []) {
    if (!d.h1.labels.some((l) => l.t === s.t && l.label === s.label)) {
      labels.push({ t: s.t, price: s.price, text: s.label, above: s.label === 'LH' || s.label === 'HH', color: DIR_COLOR[d.direction] });
    }
  }
  return {
    labels,
    zones: d.event ? zone(d, d.event.at) : [],
    hlines: invalidation(d, d.event?.at),
  };
}

export function m30Overlays(d: H8BosBtlDetail): ChartOverlays {
  const ev = d.event;
  const labels = d.m30.markers.map((m) => ({
    t: m.t,
    price: m.price,
    text: m.label,
    above: ev?.direction === 'Bearish' ? m.label === 'Retest' : m.label !== 'Retest',
    color: ev ? DIR_COLOR[ev.direction] : '#475569',
    boxed: true,
  }));
  return { labels, zones: ev ? zone(d, ev.at) : [], hlines: invalidation(d, ev?.at) };
}

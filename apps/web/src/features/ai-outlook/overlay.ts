import { fmtPrice } from '../market-scanner/format';
import type { ChartOverlay, OverlayTone } from '../market-structure/components/StructureChart';
import type { Annotation, Outlook, TimePoint, VCandle } from './types';

export const ANNOTATION_GROUPS = [
  { key: 'channel', label: 'Channel (Current TF)' },
  { key: 'htf', label: 'Higher Timeframe Channels' },
  { key: 'sr', label: 'Support & Resistance' },
  { key: 'erz', label: 'Expected Reaction Zone (ERZ)' },
  { key: 'bos', label: 'BOS / CHoCH' },
  { key: 'liquidity', label: 'Liquidity Areas' },
  { key: 'fractal', label: 'Fractals' },
  { key: 'structure', label: 'Swing Structure' },
  { key: 'breakout', label: 'Breakouts & Retests' },
  { key: 'path', label: 'Expected Path' },
  { key: 'targets', label: 'Targets' },
  { key: 'invalidation', label: 'Invalidation' },
] as const;
export type GroupKey = (typeof ANNOTATION_GROUPS)[number]['key'];
export const DEFAULT_GROUPS: GroupKey[] = ['channel', 'htf', 'sr', 'erz', 'bos', 'liquidity', 'fractal', 'path', 'targets', 'invalidation'];

const TF_MS: Record<string, number> = { M30: 18e5, H1: 36e5, H8: 288e5, D1: 864e5, W: 6048e5, MN: 2.6e9, Q: 7.9e9, HY: 1.58e10, Y: 3.16e10, YTD: 864e5 };
const ANN_TF: Record<string, string> = { M30: 'H1' };

const tone = (t: string): OverlayTone => (['res', 'sup', 'mid', 'blue', 'red', 'green', 'amber', 'purple', 'gray'].includes(t) ? (t as OverlayTone) : 'blue');

export function futureBarsFor(o: Outlook | null, tf: string, candles: VCandle[]) {
  if (!o || !candles.length) return 0;
  const last = Date.parse(candles[candles.length - 1].t);
  const end = Math.max(...o.expected_path.map(([t]) => Date.parse(t)));
  const bars = Math.ceil((end - last) / (TF_MS[tf] ?? 864e5)) + 2;
  // The projection area also hosts the target / ERZ / level tags so they never cover price action.
  return Math.max(4, Math.round(candles.length * 0.22), Math.min(Math.round(candles.length * 0.32), bars));
}

function frame(candles: VCandle[], o: Outlook) {
  const lo = Math.min(...candles.map((c) => c.l), o.price);
  const hi = Math.max(...candles.map((c) => c.h), o.price);
  const pad = (hi - lo) * 0.3;
  return (p: number | null | undefined) => p != null && p >= lo - pad && p <= hi + pad;
}

function forTf(a: Annotation, tf: string) {
  return a.tf === '*' || a.tf === (ANN_TF[tf] ?? tf);
}

/** Chart text stays short so it fits beside price action; the full wording is in the annotation detail. */
function liquidityLabel(label: string) {
  const side = /buy-side/i.test(label) ? 'BSL' : /sell-side/i.test(label) ? 'SSL' : null;
  if (!side) return `$ ${label}`;
  const tf = label.match(/^(\w+)\s/)?.[1];
  return `$ ${tf ? `${tf} ` : ''}${side}`;
}

const nearestPathTime = (path: TimePoint[], price: number) =>
  path.reduce((best, p) => (Math.abs(p[1] - price) < Math.abs(best[1] - price) ? p : best), path[path.length - 1])[0];

export type OverlayMode = 'outlook' | 'scenarios' | 'levels' | 'chart';

export function buildOverlay(o: Outlook, tf: string, candles: VCandle[], groups: Iterable<GroupKey>, mode: OverlayMode): ChartOverlay {
  const on = new Set(groups);
  const ov: Required<Pick<ChartOverlay, 'bands' | 'lines' | 'levels' | 'zones' | 'markers' | 'tags' | 'paths'>> = {
    bands: [], lines: [], levels: [], zones: [], markers: [], tags: [], paths: [],
  };
  if (!candles.length) return ov;
  const dp = o.digits;
  const inView = frame(candles, o);
  const up = o.expected_direction !== 'BEARISH';
  const ann = o.chart_annotations.filter((a) => forTf(a, tf));
  const lastT = candles[candles.length - 1].t;
  const startT = candles[Math.max(0, candles.length - Math.round(candles.length * 0.45))].t;
  const perSide = mode === 'chart' ? 3 : mode === 'scenarios' ? 1 : 2;
  const srKeep = new Set<string>();
  for (const side of [1, -1]) {
    ann
      .filter((a) => ['htf_boundary', 'support', 'resistance'].includes(a.type) && a.price != null && Math.sign(a.price - o.price) === side && inView(a.price))
      .sort((x, y) => Math.abs(x.price! - o.price) - Math.abs(y.price! - o.price))
      .slice(0, perSide)
      .forEach((a) => srKeep.add(a.id));
  }

  for (const a of ann) {
    if (!on.has(a.group as GroupKey)) continue;
    switch (a.type) {
      case 'channel':
        if (a.lines) {
          const t = a.tone === 'red' ? 'red' : 'blue';
          ov.bands.push({ upper: a.lines.upper, lower: a.lines.lower, tone: t === 'red' ? 'purple' : 'blue' });
          ov.lines.push({ from: a.lines.upper[0], to: a.lines.upper[1], tone: t });
          ov.lines.push({ from: a.lines.lower[0], to: a.lines.lower[1], tone: t });
          ov.lines.push({ from: a.lines.mid[0], to: a.lines.mid[1], tone: t, dashed: true, width: 1 });
        }
        break;
      case 'htf_boundary':
      case 'support':
      case 'resistance':
        if (mode !== 'levels' && srKeep.has(a.id)) {
          ov.levels.push({ price: a.price!, tone: tone(a.tone), id: a.id, from: startT });
          ov.tags.push({ price: a.price!, title: a.label, value: fmtPrice(a.price, dp), tone: a.tone === 'res' ? 'res' : a.tone === 'sup' ? 'sup' : 'blue', place: 'center', at: lastT, id: a.id });
        }
        break;
      case 'liquidity':
        if (inView(a.price)) ov.levels.push({ price: a.price!, tone: 'purple', label: liquidityLabel(a.label), id: a.id, from: startT });
        break;
      case 'fractal':
        if (a.at && inView(a.price))
          ov.markers.push({ at: a.at, price: a.price!, shape: a.side === 'HIGH' ? 'down' : 'up', tone: a.side === 'HIGH' ? 'red' : 'green', muted: a.status === 'INVALIDATED', id: a.id });
        break;
      case 'swing':
        if (a.at && inView(a.price)) ov.markers.push({ at: a.at, price: a.price!, shape: 'text', tone: tone(a.tone), label: a.label, below: a.side === 'LOW', id: a.id });
        break;
      case 'bos':
      case 'choch':
        if (a.at && inView(a.price)) {
          if (a.from) ov.lines.push({ from: [a.from, a.price!], to: [a.at, a.price!], tone: a.failed ? 'gray' : tone(a.tone), dashed: true, width: 1.2 });
          ov.markers.push({ at: a.at, price: a.price!, shape: 'text', tone: a.failed ? 'gray' : tone(a.tone), label: a.label, below: a.dir === 'DOWN', id: a.id });
        }
        break;
      case 'breakout':
      case 'retest':
        if (a.at && inView(a.price)) ov.markers.push({ at: a.at, price: a.price!, shape: a.type === 'breakout' ? 'diamond' : 'dot', tone: a.type === 'breakout' ? 'blue' : 'amber', id: a.id });
        break;
      case 'erz':
        if (mode !== 'levels') {
          ov.zones.push({ lo: a.lo!, hi: a.hi!, tone: up ? 'sup' : 'res', from: startT, id: a.id });
          ov.tags.push({ price: (a.lo! + a.hi!) / 2, title: 'Expected Reaction Zone (ERZ)', value: `${fmtPrice(a.lo, dp)} – ${fmtPrice(a.hi, dp)}`, tone: up ? 'sup' : 'res', place: up ? 'below' : 'above', at: o.expected_path[1]?.[0] ?? lastT, id: a.id });
        }
        break;
      case 'target':
        if (mode === 'outlook' || mode === 'chart' || mode === 'levels')
          ov.tags.push({ price: a.price!, title: a.label, value: fmtPrice(a.price, dp), tone: 'res', place: up ? 'above' : 'below', at: nearestPathTime(o.expected_path, a.price!), id: a.id });
        break;
      case 'invalidation':
        if (mode !== 'scenarios') {
          ov.levels.push({ price: a.price!, tone: 'red', id: a.id, from: startT });
          if (mode === 'levels') ov.tags.push({ price: a.price!, title: 'Invalidation', value: fmtPrice(a.price, dp), tone: 'res', place: up ? 'below' : 'above', at: o.alternative_scenario.path[1]?.[0], id: a.id });
        }
        break;
      case 'path': {
        const alt = !!a.dashed;
        if (!a.points || (alt && mode !== 'scenarios' && mode !== 'chart')) break;
        const t: OverlayTone = mode === 'scenarios' ? ((alt ? !up : up) ? 'green' : 'red') : alt ? 'red' : 'blue';
        ov.paths.push({ points: a.points, tone: t, dashed: mode === 'scenarios' || alt, id: a.id });
        break;
      }
    }
  }

  if (mode === 'scenarios') {
    const p = o.primary_scenario;
    const al = o.alternative_scenario;
    const r = o.range_scenario;
    const pEnd = p.path[p.path.length - 1];
    const aEnd = al.path[al.path.length - 1];
    if (pEnd && on.has('targets'))
      ov.tags.push({ at: pEnd[0], price: pEnd[1], title: `${p.direction} Scenario (${p.probability.toFixed(0)}%)`, value: (p.targets ?? []).map((t) => fmtPrice(t.price, dp)).join(' – '), tone: up ? 'sup' : 'res', place: up ? 'above' : 'below' });
    if (aEnd && on.has('targets'))
      ov.tags.push({ at: aEnd[0], price: aEnd[1], title: `${al.direction} Scenario (${al.probability.toFixed(0)}%)`, value: (al.targets ?? []).map((t) => fmtPrice(t.price, dp)).join(' – '), tone: up ? 'res' : 'sup', place: up ? 'below' : 'above' });
    if (r.range && on.has('erz')) {
      const [lo, hi] = r.range;
      if (inView(lo) || inView(hi)) {
        ov.zones.push({ lo, hi, tone: 'blue', from: lastT });
        ov.tags.push({ at: r.path[2]?.[0] ?? lastT, price: (lo + hi) / 2, title: `Consolidation (${r.probability.toFixed(0)}%)`, value: `${fmtPrice(lo, dp)} – ${fmtPrice(hi, dp)}`, tone: 'blue', place: 'center' });
      }
    }
  }

  if (mode === 'levels') {
    for (const lv of o.key_levels) {
      if (lv.importance !== 'High' || !inView(lv.price) || Math.abs(lv.distance_atr ?? 99) > 3) continue;
      ov.levels.push({ price: lv.price, tone: lv.type === 'Resistance' ? 'res' : 'sup', dashed: false });
    }
    ov.zones.push({ lo: o.erz.lo, hi: o.erz.hi, tone: up ? 'sup' : 'res', from: startT });
    ov.tags.push({ price: o.erz.mid, title: 'Expected Range (ERZ)', value: o.erz.label, tone: up ? 'sup' : 'res', place: 'center', at: o.expected_path[1]?.[0] ?? lastT });
    for (const z of o.key_zones.filter((x) => x.zone.startsWith('Target'))) if (inView(z.from) && inView(z.to)) ov.zones.push({ lo: z.from, hi: z.to, tone: up ? 'res' : 'sup', from: startT });
  }
  ov.tags = declutter(ov.tags, candles, o, tf);
  return ov;
}

const PRIORITY = /Target|ERZ|Reaction|Scenario|Consolidation|Invalidation|Objective/;

function declutter(tags: NonNullable<ChartOverlay['tags']>, candles: VCandle[], o: Outlook, tf: string) {
  const lo = Math.min(...candles.map((c) => c.l), o.price);
  const hi = Math.max(...candles.map((c) => c.h), o.price);
  const gap = (hi - lo) * 0.055;
  const near = (TF_MS[tf] ?? 864e5) * Math.max(6, candles.length * 0.12);
  const ranked = [...tags].sort((a, b) => Number(!PRIORITY.test(a.title)) - Number(!PRIORITY.test(b.title)));
  const kept: typeof tags = [];
  for (const t of ranked) {
    const ta = Date.parse(t.at ?? candles[candles.length - 1].t);
    const clash = kept.some((k) => Math.abs(k.price - t.price) < gap && Math.abs(Date.parse(k.at ?? candles[candles.length - 1].t) - ta) < near);
    if (!clash) kept.push(t);
  }
  return kept;
}

export const legendFor = (mode: OverlayMode) =>
  mode === 'scenarios'
    ? [
        { label: 'Bullish move', swatch: 'is-bull-line' },
        { label: 'Bearish move', swatch: 'is-bear-line' },
        { label: 'Consolidation', swatch: 'is-chan' },
        { label: 'ERZ', swatch: 'is-range' },
      ]
    : [
        { label: 'Bullish move', swatch: 'is-bull-line' },
        { label: 'Bearish move', swatch: 'is-bear-line' },
        { label: 'Channel', swatch: 'is-chan' },
        { label: 'ERZ', swatch: 'is-range' },
        { label: 'Fractal High', swatch: 'is-fh' },
        { label: 'Fractal Low', swatch: 'is-fl' },
        { label: 'Buy / sell-side liquidity ($ BSL / SSL)', swatch: 'is-liq' },
        { label: 'Invalidation', swatch: 'is-last' },
      ];

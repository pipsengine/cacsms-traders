import { fmtPrice } from '../../market-scanner/format';
import type { ChartOverlay } from '../../market-structure/components/StructureChart';
import type { ChannelLines, ChannelTf } from '../types';

export const CHANNEL_TFS: ChannelTf[] = ['Y', 'YTD', 'HY', 'Q', 'MN', 'W', 'D1', 'H8', 'H1'];
export const TF_NAMES: Record<ChannelTf, string> = {
  Y: 'Yearly (Y)',
  YTD: 'YTD',
  HY: 'Half-Year (HY)',
  Q: 'Quarterly (Q)',
  MN: 'Monthly (MN)',
  W: 'Weekly (W)',
  D1: 'Daily (D1)',
  H8: 'H8',
  H1: 'H1',
};
export const CHANNEL_BARS: Record<ChannelTf, number> = { Y: 30, YTD: 300, HY: 50, Q: 80, MN: 120, W: 110, D1: 120, H8: 120, H1: 120 };

export function channelOverlay(lines: ChannelLines | null | undefined, digits: number, labels = true, tone: 'blue' | 'purple' = 'blue'): ChartOverlay {
  if (!lines) return {};
  return {
    bands: [{ upper: lines.upper, lower: lines.lower, tone }],
    lines: [
      { from: lines.upper[0], to: lines.upper[1], tone },
      { from: lines.lower[0], to: lines.lower[1], tone },
      { from: lines.mid[0], to: lines.mid[1], tone, dashed: true, width: 1 },
    ],
    tags: labels
      ? [
          { price: lines.upper[1][1], title: 'Channel Resistance', value: fmtPrice(lines.upper[1][1], digits), tone: 'res', place: 'above' },
          { price: lines.lower[1][1], title: 'Channel Support', value: fmtPrice(lines.lower[1][1], digits), tone: 'sup', place: 'below' },
        ]
      : [],
  };
}

export const dirTone = (k?: string | null) => (k === 'UPTREND' ? 'is-up' : k === 'DOWNTREND' ? 'is-down' : 'is-amber');
export const kpiTone = (k?: string | null) => (k === 'UPTREND' ? 'is-green' : k === 'DOWNTREND' ? 'is-red' : 'is-amber') as 'is-green' | 'is-red' | 'is-amber';
export const signed = (v: number | null | undefined, dp = 1, unit = '') =>
  v == null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(dp)}${unit}`;

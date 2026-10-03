import type { StrengthTone } from './types';

type RGB = [number, number, number];
const GREEN_LIGHT: RGB = [187, 247, 208];
const GREEN_STRONG: RGB = [22, 163, 74];
const RED_LIGHT: RGB = [254, 202, 202];
const RED_STRONG: RGB = [220, 38, 38];

function mix(a: RGB, b: RGB, t: number) {
  return a.map((v, k) => Math.round(v + (b[k] - v) * t)).join(',');
}

/**
 * Backend 0–100 score → cell colour. Scores are anchored at EarnForex raw 0 (= 50), so like the
 * MQL5 matrix any positive value is green and any negative value is red; intensity shows magnitude.
 */
export function heatmapStyle(score: number): { background: string; color: string } {
  const s = Math.max(0, Math.min(100, score));
  if (s === 50) return { background: '#f8fafc', color: '#0f172a' };
  const t = Math.abs(s - 50) / 50;
  const [light, strong] = s > 50 ? [GREEN_LIGHT, GREEN_STRONG] : [RED_LIGHT, RED_STRONG];
  return { background: `rgb(${mix(light, strong, t)})`, color: t >= 0.6 ? '#ffffff' : '#0f172a' };
}

export const TONE_BAR: Record<StrengthTone, string> = {
  positive: '#22c55e',
  neutral: '#94a3b8',
  negative: '#ef4444',
};

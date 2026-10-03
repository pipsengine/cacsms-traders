import type { StrengthTone } from '../types';

const TONE_COLORS: Record<StrengthTone, { stroke: string; fill: string }> = {
  positive: { stroke: '#16a34a', fill: 'rgba(22,163,74,0.12)' },
  neutral: { stroke: '#64748b', fill: 'rgba(100,116,139,0.12)' },
  negative: { stroke: '#dc2626', fill: 'rgba(220,38,38,0.12)' },
};

export function StrengthSparkline({ points, tone }: { points: number[]; tone: StrengthTone }) {
  const w = 120;
  const h = 36;
  const pad = 2;
  if (points.length < 2) {
    return (
      <svg className="si-spark si-spark--empty" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-hidden>
        <line x1={pad} x2={w - pad} y1={h / 2} y2={h / 2} stroke="#cbd5e1" strokeWidth="1.5" strokeDasharray="4 4" />
      </svg>
    );
  }
  const lo = Math.min(...points);
  const hi = Math.max(...points);
  const span = hi - lo || 1;
  const coords = points.map((v, i) => {
    const x = pad + (i / (points.length - 1)) * (w - pad * 2);
    const y = h - pad - ((v - lo) / span) * (h - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const { stroke, fill } = TONE_COLORS[tone];
  const line = coords.join(' ');
  const area = `${pad},${h - pad} ${line} ${w - pad},${h - pad}`;
  return (
    <svg className="si-spark" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-hidden>
      <polygon points={area} fill={fill} />
      <polyline points={line} fill="none" stroke={stroke} strokeWidth="1.8" strokeLinejoin="round" />
    </svg>
  );
}

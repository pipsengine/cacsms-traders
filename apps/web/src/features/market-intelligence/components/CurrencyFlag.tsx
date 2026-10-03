import type { ReactNode } from 'react';

function UnionJack({ w = 30, h = 20 }: { w?: number; h?: number }) {
  return (
    <g>
      <rect width={w} height={h} fill="#012169" />
      <path d={`M0,0 L${w},${h} M${w},0 L0,${h}`} stroke="#fff" strokeWidth={h * 0.2} />
      <path d={`M0,0 L${w},${h} M${w},0 L0,${h}`} stroke="#C8102E" strokeWidth={h * 0.08} />
      <path d={`M${w / 2},0 V${h} M0,${h / 2} H${w}`} stroke="#fff" strokeWidth={h * 0.33} />
      <path d={`M${w / 2},0 V${h} M0,${h / 2} H${w}`} stroke="#C8102E" strokeWidth={h * 0.2} />
    </g>
  );
}

function Star({ cx, cy, r, fill }: { cx: number; cy: number; r: number; fill: string }) {
  const pts = Array.from({ length: 10 }, (_, i) => {
    const a = (Math.PI / 5) * i - Math.PI / 2;
    const rr = i % 2 === 0 ? r : r * 0.45;
    return `${(cx + rr * Math.cos(a)).toFixed(2)},${(cy + rr * Math.sin(a)).toFixed(2)}`;
  }).join(' ');
  return <polygon points={pts} fill={fill} />;
}

const FLAGS: Record<string, ReactNode> = {
  USD: (
    <g>
      <rect width="30" height="20" fill="#fff" />
      {[0, 2, 4, 6, 8, 10, 12].map((i) => (
        <rect key={i} y={(i * 20) / 13} width="30" height={20 / 13} fill="#B22234" />
      ))}
      <rect width="13" height={(20 * 7) / 13} fill="#3C3B6E" />
    </g>
  ),
  EUR: (
    <g>
      <rect width="30" height="20" fill="#003399" />
      {Array.from({ length: 12 }, (_, i) => {
        const a = (Math.PI / 6) * i;
        return <Star key={i} cx={15 + 6 * Math.cos(a)} cy={10 + 6 * Math.sin(a)} r={1.1} fill="#FFCC00" />;
      })}
    </g>
  ),
  GBP: <UnionJack />,
  JPY: (
    <g>
      <rect width="30" height="20" fill="#fff" />
      <circle cx="15" cy="10" r="6" fill="#BC002D" />
    </g>
  ),
  CHF: (
    <g>
      <rect width="30" height="20" fill="#D52B1E" />
      <rect x="13" y="4" width="4" height="12" fill="#fff" />
      <rect x="9" y="8" width="12" height="4" fill="#fff" />
    </g>
  ),
  CAD: (
    <g>
      <rect width="30" height="20" fill="#fff" />
      <rect width="7.5" height="20" fill="#D52B1E" />
      <rect x="22.5" width="7.5" height="20" fill="#D52B1E" />
      <path d="M15,4 L16.4,7.4 L18.6,6.6 L17.8,10.4 L19.6,10 L18.8,12.2 L15.5,12.6 L15.5,16 L14.5,16 L14.5,12.6 L11.2,12.2 L10.4,10 L12.2,10.4 L11.4,6.6 L13.6,7.4 Z" fill="#D52B1E" />
    </g>
  ),
  AUD: (
    <g>
      <rect width="30" height="20" fill="#012169" />
      <svg width="15" height="10" viewBox="0 0 30 20">
        <UnionJack />
      </svg>
      <Star cx={7.5} cy={15} r={2.2} fill="#fff" />
      <Star cx={22.5} cy={4} r={1.2} fill="#fff" />
      <Star cx={19} cy={9} r={1.2} fill="#fff" />
      <Star cx={25.5} cy={8} r={1.2} fill="#fff" />
      <Star cx={22.5} cy={16} r={1.3} fill="#fff" />
    </g>
  ),
  NZD: (
    <g>
      <rect width="30" height="20" fill="#012169" />
      <svg width="15" height="10" viewBox="0 0 30 20">
        <UnionJack />
      </svg>
      <Star cx={22.5} cy={4.5} r={1.4} fill="#C8102E" />
      <Star cx={19} cy={9.5} r={1.4} fill="#C8102E" />
      <Star cx={25.5} cy={8.5} r={1.4} fill="#C8102E" />
      <Star cx={22.5} cy={15.5} r={1.6} fill="#C8102E" />
    </g>
  ),
};

export function CurrencyFlag({ code, size = 20 }: { code: string; size?: number }) {
  const flag = FLAGS[code];
  const height = Math.round((size * 2) / 3);
  return (
    <svg
      className="mi-flag-svg"
      width={size}
      height={height}
      viewBox="0 0 30 20"
      role="img"
      aria-label={`${code} flag`}
    >
      {flag ?? <rect width="30" height="20" fill="#e2e8f0" />}
    </svg>
  );
}

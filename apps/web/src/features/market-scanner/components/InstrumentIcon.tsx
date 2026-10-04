import { CurrencyFlag } from '../../market-intelligence/components/CurrencyFlag';

function GoldCoin({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" role="img" aria-label="Gold">
      <defs>
        <linearGradient id="ms-gold" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#FCE7A2" />
          <stop offset="0.5" stopColor="#E5B53B" />
          <stop offset="1" stopColor="#B7860F" />
        </linearGradient>
      </defs>
      <circle cx="16" cy="16" r="15" fill="url(#ms-gold)" stroke="#A97A0B" strokeWidth="1" />
      <circle cx="16" cy="16" r="11.5" fill="none" stroke="#FFF4C7" strokeOpacity="0.7" strokeWidth="1" />
      <text x="16" y="20.5" textAnchor="middle" fontSize="12" fontWeight="800" fill="#6B4A00" fontFamily="Inter, sans-serif">
        Au
      </text>
    </svg>
  );
}

/** Overlapping base/quote flags, or a gold coin for XAU. */
export function InstrumentIcon({ base, quote, size = 'md' }: { base: string; quote: string; size?: 'sm' | 'md' | 'lg' }) {
  const px = size === 'lg' ? 40 : size === 'sm' ? 22 : 28;
  if (base === 'XAU') {
    return (
      <span className={`ms-inst-icon ms-inst-icon--${size}`} aria-hidden>
        <GoldCoin size={px} />
      </span>
    );
  }
  const flag = Math.round(px * 0.72);
  const flagH = Math.round((flag * 2) / 3);
  return (
    <span
      className={`ms-inst-icon ms-inst-icon--pair ms-inst-icon--${size}`}
      style={{ width: Math.round(flag * 1.4), height: Math.round(flagH * 1.6) }}
      aria-hidden
    >
      <span className="ms-flag ms-flag--base">
        <CurrencyFlag code={base} size={flag} />
      </span>
      <span className="ms-flag ms-flag--quote">
        <CurrencyFlag code={quote} size={flag} />
      </span>
    </span>
  );
}

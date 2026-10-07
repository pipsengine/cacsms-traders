"""Market Scanner analytics on closed candles: structure, channel position, volatility, inspection score.

Pure functions over ``Bar`` tuples so they are testable without MT5. Outputs describe market condition
and inspection priority only; nothing here produces trade direction.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from .scanner_config import ScannerSettings


@dataclass(frozen=True)
class Bar:
    t: datetime
    o: float
    h: float
    l: float
    c: float
    v: float = 0.0


def _kl(key: str, label: str, **extra) -> dict:
    return {"key": key, "label": label, **extra}


INSUFFICIENT = _kl("INSUFFICIENT", "Insufficient data")


def pivots(bars: list[Bar], n: int) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    """Fractal swing highs/lows confirmed by ``n`` closed bars on each side."""
    highs: list[tuple[int, float]] = []
    lows: list[tuple[int, float]] = []
    for i in range(n, len(bars) - n):
        win = bars[i - n : i + n + 1]
        h, l = bars[i].h, bars[i].l
        if h == max(b.h for b in win) and all(b.h < h for b in bars[i + 1 : i + n + 1]):
            highs.append((i, h))
        if l == min(b.l for b in win) and all(b.l > l for b in bars[i + 1 : i + n + 1]):
            lows.append((i, l))
    return highs, lows


def market_structure(bars: list[Bar], n: int = 2) -> dict:
    """HH+HL → bullish, LH+LL → bearish, otherwise range; plus the latest structural event."""
    highs, lows = pivots(bars, n)
    if len(highs) < 2 or len(lows) < 2:
        return dict(INSUFFICIENT)
    (_, ph), (hi_i, lh) = highs[-2], highs[-1]
    (_, pl), (lo_i, ll) = lows[-2], lows[-1]
    hh, hl = lh > ph, ll > pl
    if hh and hl:
        key, label = "BULLISH", "Bullish"
    elif not hh and not hl:
        key, label = "BEARISH", "Bearish"
    else:
        key, label = "RANGE", "Range"
    close = bars[-1].c
    event = None
    if close > lh:
        event = _kl("BREAK_UP", "Break above last swing high")
    elif close < ll:
        event = _kl("BREAK_DOWN", "Break below last swing low")
    elif key == "BULLISH" and hi_i > lo_i:
        event = _kl("PULLBACK", "Pullback from swing high")
    elif key == "BEARISH" and lo_i > hi_i:
        event = _kl("PULLBACK", "Pullback from swing low")
    return _kl(
        key,
        label,
        swing_high=lh,
        prev_swing_high=ph,
        swing_low=ll,
        prev_swing_low=pl,
        swing_high_at=bars[hi_i].t.isoformat(),
        swing_low_at=bars[lo_i].t.isoformat(),
        event=event,
    )


CHANNEL_ZONES = (
    (0.8, "NEAR_UPPER", "Near Upper"),
    (0.6, "UPPER_ZONE", "Upper Zone"),
    (0.4, "MID", "Mid Channel"),
    (0.2, "LOWER_ZONE", "Lower Zone"),
    (0.0, "NEAR_LOWER", "Near Lower"),
)


def channel_zone(position: float) -> tuple[str, str]:
    if position > 1.0:
        return "ABOVE", "Above Channel"
    for lower, key, label in CHANNEL_ZONES:
        if position >= lower:
            return key, label
    return "BELOW", "Below Channel"


def regression_channel(bars: list[Bar], period: int, width_sd: float, price: float | None = None) -> dict:
    """Linear-regression channel on closes (±width_sd residual σ) and where price sits inside it."""
    if len(bars) < period:
        return dict(INSUFFICIENT)
    ys = [b.c for b in bars[-period:]]
    n = len(ys)
    mx = (n - 1) / 2
    my = sum(ys) / n
    var = sum((x - mx) ** 2 for x in range(n))
    slope = sum((x - mx) * (y - my) for x, y in enumerate(ys)) / var
    intercept = my - slope * mx
    resid = [y - (intercept + slope * x) for x, y in enumerate(ys)]
    sd = math.sqrt(sum(r * r for r in resid) / n)
    mid = intercept + slope * (n - 1)
    upper, lower = mid + width_sd * sd, mid - width_sd * sd
    px = price if price is not None else ys[-1]
    position = 0.5 if upper == lower else (px - lower) / (upper - lower)
    key, label = channel_zone(position)
    slope_pct = slope / mid * 100.0 if mid else 0.0
    direction = "ASCENDING" if slope_pct > 0.02 else "DESCENDING" if slope_pct < -0.02 else "FLAT"
    return _kl(
        key,
        label,
        upper=upper,
        mid=mid,
        lower=lower,
        position=round(position, 3),
        slope_pct_per_bar=round(slope_pct, 4),
        direction=direction,
        period=period,
    )


def true_ranges(bars: list[Bar]) -> list[float]:
    return [max(b.h - b.l, abs(b.h - p.c), abs(b.l - p.c)) for p, b in zip(bars, bars[1:])]


def wilder_atr(tr: list[float], n: int) -> list[float]:
    if len(tr) < n:
        return []
    out = [sum(tr[:n]) / n]
    for x in tr[n:]:
        out.append((out[-1] * (n - 1) + x) / n)
    return out


def volatility(bars: list[Bar], period: int, baseline: int, low: float, high: float) -> dict:
    """ATR(period) regime vs the mean true range of the last ``baseline`` bars, plus its 5-bar trend."""
    tr = true_ranges(bars)
    atr = wilder_atr(tr, period)
    if len(atr) < 6 or len(tr) < baseline:
        return dict(INSUFFICIENT)
    base = sum(tr[-baseline:]) / baseline
    ratio = atr[-1] / base if base else 1.0
    if ratio >= high:
        key, label = "HIGH", "High"
    elif ratio <= low:
        key, label = "LOW", "Low"
    else:
        key, label = "NORMAL", "Normal"
    change = atr[-1] / atr[-6] - 1.0 if atr[-6] else 0.0
    trend = "EXPANDING" if change > 0.05 else "CONTRACTING" if change < -0.05 else "STABLE"
    return _kl(key, label, atr=atr[-1], ratio=round(ratio, 3), trend=trend, atr_change_pct=round(change * 100, 1))


def structure_agrees(structure_key: str, differential: float | None) -> bool | None:
    if differential is None or structure_key not in ("BULLISH", "BEARISH"):
        return None
    return (structure_key == "BULLISH") == (differential > 0)


def inspection_score(
    s: ScannerSettings,
    *,
    abs_differential: float | None,
    structure_key: str,
    agrees: bool | None,
    channel_position: float | None,
    vol_key: str,
    alignment_pct: float | None,
) -> dict:
    """Weighted 0–100 inspection priority; unavailable components are dropped and weights renormalized."""
    parts: dict[str, tuple[float, float | None]] = {
        "strength": (s.w_strength, None if abs_differential is None else min(1.0, abs_differential / s.strength_full_scale)),
        "structure": (
            s.w_structure,
            None
            if structure_key == "INSUFFICIENT"
            else 0.3 if structure_key == "RANGE" else 1.0 if agrees else 0.6,
        ),
        "channel": (s.w_channel, None if channel_position is None else min(1.0, abs(channel_position - 0.5) * 2)),
        "volatility": (s.w_volatility, {"HIGH": 1.0, "NORMAL": 0.6, "LOW": 0.25}.get(vol_key)),
        "alignment": (s.w_alignment, None if alignment_pct is None else alignment_pct / 100.0),
    }
    avail = {k: (w, v) for k, (w, v) in parts.items() if v is not None and w > 0}
    total_w = sum(w for w, _ in avail.values())
    score = round(sum(w * v for w, v in avail.values()) / total_w * 100) if total_w else 0
    return {
        "score": int(score),
        "components": {k: (None if v is None else round(v * 100)) for k, (_, v) in parts.items()},
    }


def status_for(score: int, s: ScannerSettings) -> dict:
    if score >= s.high_inspection:
        return _kl("HIGH_INSPECTION", "High Inspection")
    if score >= s.watching:
        return _kl("WATCHING", "Watching")
    return _kl("NEUTRAL", "Neutral")


def session_for(t: datetime) -> str:
    """FX session by UTC hour (Sydney/Tokyo → Asian, London, New York, London/NY overlap)."""
    if t.weekday() == 5 or (t.weekday() == 6 and t.hour < 21) or (t.weekday() == 4 and t.hour >= 21):
        return "Closed (weekend)"
    h = t.hour
    if 12 <= h < 16:
        return "London / New York"
    if 7 <= h < 12:
        return "London"
    if 16 <= h < 21:
        return "New York"
    return "Asian"


def reasons(
    *,
    base: str,
    quote: str,
    differential: float | None,
    quote_only_score: float | None,
    structure: dict,
    structure_tf: str,
    channel: dict,
    vol: dict,
    alignment: dict | None,
) -> list[str]:
    """Descriptive reasons ordered by importance (no trade language)."""
    out: list[str] = []
    if differential is not None:
        strong, weak = (base, quote) if differential >= 0 else (quote, base)
        a = abs(differential)
        if a >= 18:
            out.append(f"{strong} strength vs {weak} weakness ({a:.0f} pts)")
        elif a >= 8:
            out.append(f"{strong} stronger than {weak} ({a:.0f} pts)")
        else:
            out.append(f"{base}/{quote} strength balanced ({a:.0f} pts)")
    elif quote_only_score is not None:
        out.append(f"{quote} strength {quote_only_score:.0f}/100 ({base} not in currency basket)")
    if structure["key"] in ("BULLISH", "BEARISH", "RANGE"):
        text = f"{structure_tf} {structure['label'].lower()} structure"
        if structure.get("event"):
            text += f" — {structure['event']['label'].lower()}"
        out.append(text)
    ck = channel.get("key")
    if ck in ("NEAR_UPPER", "ABOVE"):
        out.append("Price near upper channel boundary" if ck == "NEAR_UPPER" else "Price above regression channel")
    elif ck in ("NEAR_LOWER", "BELOW"):
        out.append("Price near lower channel boundary" if ck == "NEAR_LOWER" else "Price below regression channel")
    elif ck == "MID":
        out.append("Price at channel equilibrium")
    elif ck in ("UPPER_ZONE", "LOWER_ZONE"):
        out.append(f"Price in {channel['label'].lower()} of channel")
    vk = vol.get("key")
    if vk == "HIGH":
        out.append(f"Volatility above normal (ATR ×{vol['ratio']:.2f})")
    elif vk == "LOW":
        out.append(f"Volatility compressed (ATR ×{vol['ratio']:.2f})")
    if alignment and alignment.get("total"):
        out.append(f"{alignment['aligned']}/{alignment['total']} strength timeframes aligned")
    return out

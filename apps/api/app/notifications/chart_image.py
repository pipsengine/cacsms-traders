"""Daily outlook chart for the analysis email.

Drawn on the server from stored candles and the published plan. The picture describes market structure only —
it never shows an order, a position, or a fill.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

_FONTS = Path(__file__).with_name("fonts")
_CACHE: dict[tuple[str, int], ImageFont.ImageFont] = {}

W, H = 1280, 800
PLOT = (32, 132, 1104, 688)  # left, top, right, bottom
BULL = (11, 183, 124)
BEAR = (240, 68, 68)
INK = (16, 32, 61)
MUTED = (104, 119, 141)
GRID = (232, 237, 244)
BLUE = (33, 104, 238)
BLUE_SOFT = (78, 131, 239)
RED = (239, 63, 73)
AMBER = (217, 119, 6)


def _font(weight: str, size: int) -> ImageFont.ImageFont:
    key = (weight, size)
    if key not in _CACHE:
        path = _FONTS / ("Roboto-Medium.ttf" if weight == "medium" else "Roboto-Regular.ttf")
        _CACHE[key] = ImageFont.truetype(str(path), size) if path.exists() else ImageFont.load_default(size)
    return _CACHE[key]


def _ts(value) -> datetime:
    if isinstance(value, datetime):
        t = value
    else:
        t = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _px(value: float, digits: int) -> str:
    return f"{value:,.{digits}f}"


def _ticks(lo: float, hi: float, count: int = 5) -> list[float]:
    span = hi - lo or 1.0
    raw = span / count
    mag = 10 ** math.floor(math.log10(raw))
    step = next((m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw - 1e-12), raw)
    out, v = [], math.ceil(lo / step) * step
    while v <= hi + step * 1e-6 and len(out) < 8:
        if lo <= v <= hi:
            out.append(v)
        v += step
    return out


def _median_gap(times: list[datetime]) -> float:
    gaps = sorted((b - a).total_seconds() for a, b in zip(times, times[1:]) if b > a)
    return gaps[len(gaps) // 2] if gaps else 86400.0


def _spread(items: list[tuple[float, str, tuple]], gap: float, lo: float, hi: float) -> list[tuple[float, str, tuple]]:
    """Push labels apart so neighbouring pills do not sit on top of each other."""
    if not items:
        return []
    ordered = sorted(items, key=lambda it: it[0])
    ys = [it[0] for it in ordered]
    for i in range(1, len(ys)):
        if ys[i] - ys[i - 1] < gap:
            ys[i] = ys[i - 1] + gap
    if ys[-1] > hi:
        ys = [y - (ys[-1] - hi) for y in ys]
    if ys[0] < lo:
        ys = [y + (lo - ys[0]) for y in ys]
        if ys[-1] > hi:
            ys[-1] = hi
    return [(ys[i], ordered[i][1], ordered[i][2]) for i in range(len(ordered))]


def _clip(p, q, box):
    """Cohen–Sutherland clip of a segment to the plot, or None when it misses the plot."""
    x0, y0, x1, y1 = box
    left, right, bottom, top = 1, 2, 4, 8

    def code(x, y):
        c = 0
        if x < x0:
            c |= left
        elif x > x1:
            c |= right
        if y > y1:
            c |= bottom
        elif y < y0:
            c |= top
        return c

    ax, ay = p
    bx, by = q
    ca, cb = code(ax, ay), code(bx, by)
    for _ in range(12):
        if not (ca | cb):
            return (ax, ay), (bx, by)
        if ca & cb:
            return None
        c = ca or cb
        if c & top:
            x, y = ax + (bx - ax) * (y0 - ay) / (by - ay or 1e-9), y0
        elif c & bottom:
            x, y = ax + (bx - ax) * (y1 - ay) / (by - ay or 1e-9), y1
        elif c & right:
            x, y = x1, ay + (by - ay) * (x1 - ax) / (bx - ax or 1e-9)
        else:
            x, y = x0, ay + (by - ay) * (x0 - ax) / (bx - ax or 1e-9)
        if c == ca:
            ax, ay, ca = x, y, code(x, y)
        else:
            bx, by, cb = x, y, code(x, y)
    return None


def _dashed(draw: ImageDraw.ImageDraw, p1, p2, fill, width: int, dash: int = 10, gap: int = 7) -> None:
    x1, y1 = p1
    x2, y2 = p2
    dx, dy = x2 - x1, y2 - y1
    dist = math.hypot(dx, dy)
    if dist < 1:
        return
    ux, uy = dx / dist, dy / dist
    pos = 0.0
    while pos < dist:
        end = min(dist, pos + dash)
        draw.line([(x1 + ux * pos, y1 + uy * pos), (x1 + ux * end, y1 + uy * end)], fill=fill, width=width)
        pos = end + gap


def _arrow(draw: ImageDraw.ImageDraw, tip, back, fill, size: int = 14) -> None:
    ang = math.atan2(tip[1] - back[1], tip[0] - back[0])
    left = (tip[0] + size * math.cos(ang + 2.55), tip[1] + size * math.sin(ang + 2.55))
    right = (tip[0] + size * math.cos(ang - 2.55), tip[1] + size * math.sin(ang - 2.55))
    draw.polygon([tip, left, right], fill=fill)


def _pill(draw: ImageDraw.ImageDraw, x: float, y: float, text: str, font, fg, bg, border=None) -> float:
    tw = font.getlength(text)
    h, pad = 32, 14
    box = (x, y - h / 2, x + tw + pad * 2, y + h / 2)
    draw.rounded_rectangle(box, radius=8, fill=bg, outline=border, width=2 if border else 0)
    draw.text((x + pad, y), text, font=font, fill=fg, anchor="lm")
    return tw + pad * 2


def render_outlook_chart(
    symbol: str,
    candles: list[dict],
    *,
    digits: int = 5,
    direction: str | None = None,
    confidence: float | None = None,
    rank: int | None = None,
    erz: tuple[float, float] | None = None,
    targets: list[float] | None = None,
    invalidation: float | None = None,
    channel: dict | None = None,
    path: list | None = None,
) -> bytes:
    """PNG of the daily chart for one qualified outlook. ``candles`` are ``{t,o,h,l,c}``, oldest first."""
    bars = [c for c in candles if c.get("t") is not None and all(c.get(k) is not None for k in ("o", "h", "l", "c"))][-72:]
    if len(bars) < 8:
        raise ValueError("not enough candles for a chart")
    up = (direction or "").upper() != "BEARISH"
    targets = [float(p) for p in (targets or []) if p is not None][:3]
    times = [_ts(c["t"]) for c in bars]
    gap = _median_gap(times)

    parsed_path: list[tuple[datetime, float]] = []
    for pt in path or []:
        try:
            parsed_path.append((_ts(pt[0]), float(pt[1])))
        except (TypeError, ValueError, IndexError):
            continue
    future = any(t > times[-1] for t, _ in parsed_path)

    def seg(line):
        try:
            a, b = line[0], line[1]
            return (_ts(a[0]), float(a[1])), (_ts(b[0]), float(b[1]))
        except (TypeError, ValueError, IndexError):
            return None

    upper = seg((channel or {}).get("upper"))
    mid = seg((channel or {}).get("mid"))
    lower = seg((channel or {}).get("lower"))
    ch_edge = BLUE if up else RED
    ch_mid = BLUE_SOFT if up else (167, 139, 250)
    ch_fill = (36, 108, 240, 20) if up else (124, 58, 237, 22)

    lo = min(float(c["l"]) for c in bars)
    hi = max(float(c["h"]) for c in bars)
    extras = list(targets)
    if erz:
        extras.extend(erz)
    if invalidation is not None:
        extras.append(float(invalidation))
    for line in (upper, mid, lower):
        if line:
            extras.extend(p for _, p in line)
    extras.extend(p for _, p in parsed_path)
    span = max(hi - lo, abs(hi) * 0.002, 1e-6)
    # A far level is still the plan, but it must not flatten the candles into a strip.
    band = span * 1.8
    extras = [p for p in extras if lo - band <= p <= hi + band]
    if extras:
        lo, hi = min(lo, min(extras)), max(hi, max(extras))
    pad = max(hi - lo, span) * 0.1
    lo, hi = lo - pad, hi + pad

    left, top, right, bottom = PLOT
    plot_w = right - left
    candle_w = plot_w * (0.78 if future else 0.96)
    step = candle_w / len(bars)

    def x_at(i: float) -> float:
        return left + (i + 0.5) * step

    def x_time(t: datetime) -> float:
        if t <= times[0]:
            return x_at(0) - (times[0] - t).total_seconds() / gap * step
        if t >= times[-1]:
            return x_at(len(times) - 1) + (t - times[-1]).total_seconds() / gap * step
        i = 0
        while i + 1 < len(times) and times[i + 1] < t:
            i += 1
        span_s = max(1.0, (times[i + 1] - times[i]).total_seconds())
        return x_at(i) + (t - times[i]).total_seconds() / span_s * step

    def y_at(price: float) -> float:
        return top + (hi - price) / (hi - lo) * (bottom - top)

    img = Image.new("RGBA", (W, H), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)
    title_f, body_f, small_f, axis_f = _font("medium", 32), _font("regular", 22), _font("medium", 20), _font("regular", 20)

    head = f"#{rank}   {symbol}" if rank else symbol
    draw.text((32, 36), head, font=title_f, fill=INK, anchor="lm")
    cursor = 32 + title_f.getlength(head) + 16
    if direction:
        word = direction.replace("_", " ").title()
        fg, bg, edge = ((8, 122, 80), (231, 249, 240), (62, 201, 141)) if up else ((180, 35, 24), (255, 240, 242), (255, 104, 119))
        cursor += _pill(draw, cursor, 36, word, small_f, fg, bg, edge) + 12
    if confidence is not None:
        draw.text((cursor, 36), f"{float(confidence):.0f}% confidence", font=body_f, fill=MUTED, anchor="lm")
    badge = "D1"
    bw = small_f.getlength(badge)
    draw.rounded_rectangle((W - 32 - bw - 28, 20, W - 32, 52), radius=8, fill=(234, 242, 255))
    draw.text((W - 32 - 14, 36), badge, font=small_f, fill=(29, 99, 223), anchor="rm")

    last = bars[-1]
    ohlc = (("O", float(last["o"]), INK), ("H", float(last["h"]), INK), ("L", float(last["l"]), INK),
            ("C", float(last["c"]), BULL if float(last["c"]) >= float(last["o"]) else BEAR))
    ox = 32
    for i, (name, value, color) in enumerate(ohlc):
        label = f"{name}  {_px(value, digits)}"
        draw.text((ox, 92), label, font=body_f, fill=color, anchor="lm")
        ox += body_f.getlength(label) + 28
    draw.line((32, 112, W - 32, 112), fill=GRID, width=2)

    if future:
        draw.rectangle((left + candle_w, top, right, bottom), fill=(248, 250, 253, 255))
        _dashed(draw, (left + candle_w, top), (left + candle_w, bottom), (213, 222, 234, 255), 2, 4, 6)

    for price in _ticks(lo, hi):
        y = y_at(price)
        draw.line((left, y, right, y), fill=GRID, width=2)
        draw.text((right + 14, y), _px(price, digits), font=axis_f, fill=MUTED, anchor="lm")

    zone = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    zd = ImageDraw.Draw(zone)
    if upper and lower:
        pts = []
        for line in (upper, lower):
            (t1, p1), (t2, p2) = line
            pts.append((x_time(t1), y_at(p1), x_time(t2), y_at(p2)))
        (x1, y1, x2, y2), (a1, b1, a2, b2) = pts
        zd.polygon([(x1, y1), (x2, y2), (a2, b2), (a1, b1)], fill=ch_fill)
    if erz:
        zlo, zhi = min(erz), max(erz)
        fill = (31, 185, 120, 56) if up else (255, 102, 121, 52)
        edge = (25, 169, 110, 180) if up else (255, 90, 107, 180)
        zd.rectangle((left, y_at(zhi), right, y_at(zlo)), fill=fill, outline=edge, width=2)
    cover = Image.new("L", (W, H), 0)
    ImageDraw.Draw(cover).rectangle((left, top, right, bottom), fill=255)
    zr, zg, zb, za = zone.split()
    zone = Image.merge("RGBA", (zr, zg, zb, ImageChops.multiply(za, cover)))
    img.alpha_composite(zone)
    draw = ImageDraw.Draw(img)
    plot_box = (left, top, right, bottom)

    def stroke(line, fill, width, dashed=False):
        if not line:
            return
        (t1, p1), (t2, p2) = line
        seg = _clip((x_time(t1), y_at(p1)), (x_time(t2), y_at(p2)), plot_box)
        if not seg:
            return
        if dashed:
            _dashed(draw, seg[0], seg[1], fill, width)
        else:
            draw.line(seg, fill=fill, width=width)

    stroke(upper, ch_edge, 3)
    stroke(lower, ch_edge, 3)
    stroke(mid, ch_mid, 2, dashed=True)

    if len(parsed_path) >= 2:
        xy = [(x_time(t), y_at(p)) for t, p in parsed_path]
        visible = []
        for a, b in zip(xy, xy[1:]):
            seg = _clip(a, b, plot_box)
            if not seg:
                continue
            visible.append(seg)
            draw.line(seg, fill=BLUE, width=3)
        if visible:
            _arrow(draw, visible[-1][1], visible[-1][0], BLUE)
        for x, y in xy:
            if left <= x <= right and top <= y <= bottom:
                draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=BLUE)

    def in_view(price: float) -> bool:
        return lo <= price <= hi

    level_labels: list[tuple[float, str, tuple]] = []
    if invalidation is not None and in_view(float(invalidation)):
        y = y_at(float(invalidation))
        _dashed(draw, (left, y), (right, y), RED, 2, 8, 6)
        level_labels.append((y, f"Invalidation  {_px(float(invalidation), digits)}", RED))
    for i, price in enumerate(targets, start=1):
        if not in_view(price):
            continue
        y = y_at(price)
        _dashed(draw, (left, y), (right, y), AMBER, 2, 8, 6)
        level_labels.append((y, f"Target {i}  {_px(price, digits)}", AMBER))
    if erz and (in_view(erz[0]) or in_view(erz[1])):
        level_labels.append((y_at(min(hi, max(lo, sum(erz) / 2))), f"ERZ  {_px(min(erz), digits)} to {_px(max(erz), digits)}", (8, 122, 80) if up else (180, 35, 24)))

    body = max(2.0, min(18.0, step * 0.62))
    for i, c in enumerate(bars):
        o, h, l, cl = float(c["o"]), float(c["h"]), float(c["l"]), float(c["c"])
        color = BULL if cl >= o else BEAR
        x = x_at(i)
        draw.line((x, y_at(h), x, y_at(l)), fill=color, width=2)
        y0, y1 = y_at(max(o, cl)), y_at(min(o, cl))
        draw.rectangle((x - body / 2, y0, x + body / 2, max(y1, y0 + 2)), fill=color)

    y_last = y_at(float(last["c"]))
    _dashed(draw, (left, y_last), (right, y_last), INK, 2, 2, 5)
    level_labels.append((y_last, f"Last  {_px(float(last['c']), digits)}", INK))

    placed = _spread(level_labels, 38, top + 20, bottom - 20)
    pill_f = _font("medium", 18)
    for y, text, color in placed:
        tw = pill_f.getlength(text)
        x = right - tw - 36
        bg = (255, 255, 255, 230)
        draw.rounded_rectangle((x - 8, y - 15, x + tw + 8, y + 15), radius=6, fill=bg, outline=color, width=2)
        draw.text((x, y), text, font=pill_f, fill=color, anchor="lm")

    # Date axis: a label when the month changes, plus the latest bar.
    marks: list[tuple[int, str, bool]] = []
    prev = None
    for i, t in enumerate(times):
        if prev is None or t.month != prev.month or t.year != prev.year:
            marks.append((i, t.strftime("%Y") if t.month == 1 and (prev is None or t.year != prev.year) else t.strftime("%b"), True))
        prev = t
    marks.append((len(times) - 1, times[-1].strftime("%d %b"), False))
    last_x = -1e9
    for i, text, strong in marks:
        x = x_at(i)
        if x - last_x < 72:
            continue
        draw.text((x, bottom + 22), text, font=axis_f, fill=INK if strong else MUTED, anchor="mt")
        last_x = x

    legend = [("Bullish", BULL), ("Bearish", BEAR)]
    if upper:
        legend.append(("Channel", ch_edge))
    if erz:
        legend.append(("ERZ", (8, 122, 80) if up else (180, 35, 24)))
    if targets:
        legend.append(("Target", AMBER))
    if invalidation is not None:
        legend.append(("Invalidation", RED))
    if parsed_path:
        legend.append(("Expected path", BLUE))
    lx = 32
    ly = H - 36
    for name, color in legend:
        draw.rounded_rectangle((lx, ly - 8, lx + 18, ly + 8), radius=3, fill=color)
        draw.text((lx + 26, ly), name, font=body_f, fill=MUTED, anchor="lm")
        lx += 26 + body_f.getlength(name) + 28
    draw.text((W - 32, ly), "Analysis only", font=body_f, fill=MUTED, anchor="rm")

    out = Image.new("RGB", (W, H), (255, 255, 255))
    out.paste(img, mask=img.split()[-1])
    buf = BytesIO()
    out.save(buf, format="PNG", optimize=True)
    return buf.getvalue()

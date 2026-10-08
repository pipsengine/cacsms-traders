"""Build the daily chart images attached to an AI Analysis Complete email.

Charts are best-effort. A missing candle history or a drawing failure leaves that symbol out and never blocks the email.
"""
from __future__ import annotations

import logging

from .chart_image import render_outlook_chart

log = logging.getLogger("cacsms.notifications")
_CACHE: dict[str, list[tuple[str, bytes, str]]] = {}


def _digits(symbol: str, given) -> int:
    if given is not None:
        try:
            return int(given)
        except (TypeError, ValueError):
            pass
    return 2 if symbol.startswith("XAU") else 3 if symbol.endswith("JPY") else 5


def _pair(values) -> tuple[float, float] | None:
    if not values or len(values) < 2 or values[0] is None or values[1] is None:
        return None
    try:
        lo, hi = float(values[0]), float(values[1])
    except (TypeError, ValueError):
        return None
    return (min(lo, hi), max(lo, hi))


def _candles(rows) -> list[dict]:
    out = []
    for r in rows:
        t = r[0]
        out.append({"t": t.isoformat() if hasattr(t, "isoformat") else str(t), "o": float(r[2]), "h": float(r[3]), "l": float(r[4]), "c": float(r[5])})
    return out


def _overlay(outlook: dict | None) -> tuple[dict | None, list | None]:
    ann = (outlook or {}).get("chart_annotations") or []
    channel = next((a.get("lines") for a in ann if a.get("type") == "channel" and a.get("tf") == "D1" and a.get("lines")), None)
    path = next((a.get("points") for a in ann if a.get("type") == "path" and not a.get("dashed") and a.get("points")), None)
    return channel, path


def _outlooks(conn, run_id, symbols: list[str]) -> dict:
    if not run_id:
        return {}
    try:
        from ..market.outlook.store import OutlookRepository
        from ..market.strength_intel_store import active_scope

        store = OutlookRepository(conn, active_scope(conn))
    except Exception:
        log.warning("Outlook annotations were not loaded for the email chart", exc_info=True)
        return {}
    found = {}
    for sym in symbols:
        try:
            found[sym] = store.outlook(run_id, sym)
        except Exception:
            log.warning("Annotations for %s were not loaded", sym, exc_info=True)
    return found


def _build(run_id, opportunities: list[dict]) -> list[tuple[str, bytes, str]]:
    from ..core.database import db
    from ..market.repository import MarketRepository

    images = []
    with db() as conn:
        repo = MarketRepository(conn)
        stored = _outlooks(conn, run_id, [o["symbol"] for o in opportunities])
        for o in opportunities:
            sym = o["symbol"]
            try:
                candles = _candles(repo.candles(sym, "D1", 100))
                if len(candles) < 8:
                    continue
                channel, path = _overlay(stored.get(sym))
                png = render_outlook_chart(
                    sym, candles, digits=_digits(sym, o.get("digits")), direction=o.get("direction"),
                    confidence=o.get("confidence"), rank=o.get("rank"), erz=_pair(o.get("erz")),
                    targets=[p for p in (o.get("targets") or []) if p is not None],
                    invalidation=o.get("invalidation"), channel=channel, path=path)
            except Exception:
                log.warning("D1 chart for %s was left out of the email", sym, exc_info=True)
                continue
            images.append((f"chart-{sym}", png, sym))
    return images


def chart_images(event: dict) -> list[tuple[str, bytes, str]]:
    """`(content-id, png, symbol)` for each qualified opportunity that has daily candles."""
    if event.get("event_type") != "AI_OUTLOOK_PUBLISHED":
        return []
    meta = event.get("metadata") or {}
    opportunities = [o for o in (meta.get("opportunities") or []) if o.get("symbol")]
    if not opportunities:
        return []
    key = str(event.get("id") or "")
    if key and key in _CACHE:
        return _CACHE[key]
    try:
        images = _build(meta.get("run_id"), opportunities)
    except Exception:
        log.warning("Outlook charts could not be built", exc_info=True)
        return []
    if key:
        if len(_CACHE) > 16:
            _CACHE.clear()
        _CACHE[key] = images
    return images

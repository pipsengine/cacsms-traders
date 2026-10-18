"""Map persisted intelligence into chart overlays (observed vs projected labels)."""
from __future__ import annotations

import json
from ..market.outlook.store import OutlookRepository
from ..market.strength_intel_store import active_scope


def _level(oid: str, price: float, label: str, source: str, *, confirmed: bool, color: str = "#2563eb") -> dict:
    return {
        "id": oid,
        "kind": "level",
        "price": price,
        "label": label,
        "color": color,
        "source": source,
        "confirmed": confirmed,
        "timeframe": "*",
    }


def _zone(oid: str, lo: float, hi: float, label: str, source: str, *, confirmed: bool, color: str = "#93c5fd") -> dict:
    return {
        "id": oid,
        "kind": "zone",
        "price": min(lo, hi),
        "price2": max(lo, hi),
        "label": label,
        "color": color,
        "source": source,
        "confirmed": confirmed,
        "timeframe": "*",
    }


def _annotation_overlay(ann: dict, idx: int) -> dict | None:
    price = ann.get("price")
    if price is None:
        return None
    projected = bool(ann.get("dashed")) or ann.get("type") in ("alt_path", "scenario")
    confirmed = not projected and ann.get("type") not in ("scenario", "alt_path")
    label = str(ann.get("label") or ann.get("type") or "Level")
    if projected:
        label = f"[Projected] {label}"
    tone = ann.get("tone") or ann.get("group")
    color = {"red": "#ef4444", "green": "#10b981", "blue": "#2563eb"}.get(str(tone), "#64748b")
    source = "ai" if ann.get("group") in ("invalidation", "targets", "erz") or ann.get("source") else "levels"
    if ann.get("type") == "channel" or ann.get("group") == "channel":
        source = "channel"
    if ann.get("type") in ("structure", "bos", "choch", "btl"):
        source = "structure"
    kind = ann.get("type")
    if kind == "channel" and ann.get("upper") is not None and ann.get("lower") is not None:
        return _zone(f"ann-{idx}", float(ann["lower"]), float(ann["upper"]), label, source, confirmed=confirmed, color=color)
    return _level(f"ann-{idx}", float(price), label, source, confirmed=confirmed, color=color)


def overlays_for(conn, symbol: str, timeframe: str) -> list[dict]:
    sym = symbol.upper()
    scope = active_scope(conn)
    store = OutlookRepository(conn, scope)
    out: list[dict] = []
    run = store.latest_published("DAILY")
    if run:
        outlook = store.outlook(run["id"], sym)
        if outlook:
            for i, ann in enumerate(outlook.get("chart_annotations") or []):
                if not isinstance(ann, dict):
                    continue
                tf = str(ann.get("tf") or "*")
                if tf not in ("*", timeframe, timeframe.upper()):
                    continue
                row = _annotation_overlay(ann, i)
                if row:
                    row["timeframe"] = tf
                    out.append(row)
            inv = outlook.get("invalidation") or {}
            if inv.get("price") is not None:
                out.append(_level("inv", float(inv["price"]), "[Observed] Invalidation", "ai", confirmed=True, color="#ef4444"))
            for i, tgt in enumerate(outlook.get("targets") or []):
                if tgt.get("price") is not None:
                    out.append(
                        _level(
                            f"tgt-{i}",
                            float(tgt["price"]),
                            f"[Observed] Target {i + 1}",
                            "ai",
                            confirmed=bool(tgt.get("confirmed")),
                            color="#10b981",
                        )
                    )
    # Market structure snapshot (range boundaries) when available
    row = conn.execute(
        "SELECT range_high, range_low, details_json FROM mi_range_structure_snapshot "
        "WHERE tenant_id=? AND trading_account_id=? AND symbol=? ORDER BY as_of DESC LIMIT 1",
        (*scope, sym),
    ).fetchone()
    if row:
        hi = row[0] if isinstance(row, tuple) else row["range_high"]
        lo = row[1] if isinstance(row, tuple) else row["range_low"]
        if hi is not None and lo is not None:
            out.append(_zone("rs-range", float(lo), float(hi), "Range structure", "structure", confirmed=True))
    return out

"""Autonomous Market Scanner engine.

Background thread on the shared MT5 session: keeps XAUUSD candles ingested (the 28 FX pairs are
already maintained by the Strength Engine), re-analyses closed candles every analysis interval,
refreshes live quotes every few seconds and merges both with the Strength Engine's pair intelligence.
API requests only read the cached result.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone

from ..core.database import db, execute_retry
from .ingestion_runner import MarketIngestionRunner
from .mt5_gateway import create_market_data_gateway
from .mt5_platform_status import get_mt5_market_context
from .repository import MarketRepository
from .scanner_analytics import (
    Bar,
    inspection_score,
    market_structure,
    reasons,
    regression_channel,
    session_for,
    status_for,
    structure_agrees,
    volatility,
)
from .scanner_config import (
    CHART_TIMEFRAMES,
    DISPLAY_TF,
    EXTRA_INGEST_TIMEFRAMES,
    GOLD,
    SCANNER_UNIVERSE,
    STRUCTURE_TIMEFRAMES,
    UNIVERSE_INGEST_TIMEFRAMES,
    instrument_name,
    settings,
    settings_payload,
)
from .range_structure import ltf_context, range_view, weekly_range
from .range_structure_config import range_settings, range_settings_payload
from .structure_overview import (
    EVENT_TIMEFRAMES,
    TF_DELTA,
    alignment,
    cells_for,
    current_state,
    live_events,
    overview_core,
)
from .structure_overview_config import OVERVIEW_TIMEFRAMES, REGIMES, overview_settings, overview_settings_payload
from .h8_bos_btl import h1_validation, h8_core, h8_live, m30_confirmation, weekly_core, weekly_live
from .h8_bos_btl_config import ALERT_KINDS, ALERT_PRIORITY, h8_bos_btl_settings, h8_bos_btl_settings_payload
from .trend_structure import mtf_rows, trend_core, trend_events, trend_view
from .trend_structure_config import TREND_TIMEFRAMES, trend_settings, trend_settings_payload
from .strength_engine import get_strength_engine
from .strength_intel_store import active_scope

log = logging.getLogger(__name__)

BARS = {"W1": 260, "D1": 300, "H8": 200, "H1": 200, "M30": 200}
H8BB_CHART_BARS = {"W": 72, "H8": 96, "H1": 110, "M30": 110}
INCREMENTAL_BARS = 6
REVERSAL_TIMEFRAMES = ("W", "D1", "H8")
STALE_AFTER_SECONDS = 180.0


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def load_bars(repo: MarketRepository, symbol: str, timeframe: str, limit: int) -> list[Bar]:
    out: list[Bar] = []
    for r in repo.candles(symbol, timeframe, limit):
        t = datetime.fromisoformat(r[0])
        out.append(Bar(t if t.tzinfo else t.replace(tzinfo=timezone.utc), float(r[2]), float(r[3]), float(r[4]), float(r[5])))
    return out


class MarketScannerEngine:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._state = "STARTING"
        self._error: str | None = None
        self._ctx: dict = {"mt5_connected": False}
        self._analysis: dict[str, dict] = {}
        self._quotes: dict[str, dict] = {}
        self._quote_errors: dict[str, str] = {}
        self._rows: list[dict] = []
        self._cycle_id = 0
        self._cycle_at: datetime | None = None
        self._cycle_mono = 0.0
        self._quotes_at: datetime | None = None
        self._persist_mono = 0.0
        self._gold_bootstrapped = False
        self._gold_error: str | None = None

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="market-scanner", daemon=True)
        self._thread.start()
        log.info("Market scanner started")

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as exc:
                log.exception("Market scanner tick failed")
                with self._lock:
                    self._state = "ERROR"
                    self._error = str(exc)
            self._stop.wait(settings().quote_seconds)

    def _ingest_gold(self, repo: MarketRepository, gw, *, bootstrap: bool) -> None:
        runner = MarketIngestionRunner(gw, repo, candle_count=400 if bootstrap else INCREMENTAL_BARS)

        def sync(sym: str, tf: str) -> str | None:
            try:
                return runner.sync_pair_timeframe(sym, tf).get("error")
            except Exception as exc:
                return str(exc)

        errors = []
        for tf in EXTRA_INGEST_TIMEFRAMES:
            err = sync(GOLD, tf)
            if err:
                errors.append(f"{tf}: {err}")
        self._gold_error = "; ".join(errors) or None
        for sym in SCANNER_UNIVERSE[1:]:
            for tf in UNIVERSE_INGEST_TIMEFRAMES:
                err = sync(sym, tf)
                if err:
                    log.debug("%s %s ingestion failed: %s", sym, tf, err)
        if bootstrap:
            self._gold_bootstrapped = True

    def _analyze(self, repo: MarketRepository, now: datetime, connected: bool) -> None:
        s = settings()
        out: dict[str, dict] = {}
        for sym in SCANNER_UNIVERSE:
            bars = {tf: load_bars(repo, sym, tf, n) for tf, n in BARS.items()}
            d1 = bars["D1"]
            if len(d1) < s.min_d1_bars:
                why = f"Insufficient D1 history ({len(d1)}/{s.min_d1_bars} closed bars)"
                if sym == GOLD and self._gold_error:
                    why = f"Not available from MT5 ({self._gold_error.split(';')[0]})"
                elif not d1 and not connected:
                    why = "No stored history — awaiting MT5 connection to ingest candles"
                out[sym] = {"excluded": why}
                continue
            structures = {tf: market_structure(bars[tf], s.swing_strength) for tf in STRUCTURE_TIMEFRAMES}
            primary_tf = next(
                (tf for tf in ("D1", "W1", "H8") if structures[tf]["key"] in ("BULLISH", "BEARISH")), "D1"
            )
            h1 = bars["H1"]
            rs = range_settings()
            range_core = weekly_range(bars["W1"], rs)
            out[sym] = {
                "d1": d1,
                "h1": h1,
                "range_core": range_core,
                "overview": self._overview_core(bars, range_core, rs),
                "h8bb": self._h8bb_core(bars),
                "trend": trend_core(bars, trend_settings()),
                "range_ltf": ltf_context(d1, bars["H8"], h1, rs),
                "structures": structures,
                "primary_tf": primary_tf,
                "volatility": volatility(d1, s.atr_period, s.atr_baseline, s.vol_low, s.vol_high),
                "last_close": (h1[-1].t + timedelta(hours=1), h1[-1].c) if h1 else (d1[-1].t, d1[-1].c),
            }
        with self._lock:
            self._analysis = out
            self._cycle_id += 1
            self._cycle_at = now

    def _refresh_quotes(self, gw) -> None:
        if not hasattr(gw, "symbol_snapshot"):
            return
        quotes, errors = {}, {}
        for sym in SCANNER_UNIVERSE:
            try:
                quotes[sym] = gw.symbol_snapshot(sym)
            except Exception as exc:
                errors[sym] = str(exc)
        with self._lock:
            self._quotes, self._quote_errors = quotes, errors
            self._quotes_at = datetime.now(timezone.utc)

    def _tick(self) -> None:
        s = settings()
        with db() as conn:
            ctx = get_mt5_market_context(conn)
            connected = bool(ctx.get("mt5_connected") and ctx.get("market_data_ready"))
            repo = MarketRepository(conn)
            now = datetime.now(timezone.utc)
            with self._lock:
                self._ctx = ctx
                if not self._analysis:
                    self._state = "SYNCING" if connected else "MT5_DISCONNECTED"
            gw = create_market_data_gateway() if connected else None
            due = time.monotonic() - self._cycle_mono >= s.analysis_seconds or not self._analysis
            if due:
                if gw is not None:
                    try:
                        self._ingest_gold(repo, gw, bootstrap=not self._gold_bootstrapped)
                    except Exception as exc:
                        self._gold_error = str(exc)
                        log.warning("XAUUSD ingestion failed: %s", exc)
                self._analyze(repo, now, connected)
                self._cycle_mono = time.monotonic()
            if gw is not None:
                self._refresh_quotes(gw)
            rows = self._compose(now)
            with self._lock:
                self._rows = rows
                self._state = "READY" if connected else "MT5_DISCONNECTED"
                self._error = None
            if due and time.monotonic() - self._persist_mono >= s.persist_seconds:
                self._persist(conn, rows)
                self._persist_mono = time.monotonic()

    def _compose(self, now: datetime) -> list[dict]:
        s = settings()
        intel = get_strength_engine().intelligence() or {}
        pairs = {r["pair"]: r for r in intel.get("pairs", [])}
        scores = intel.get("scores", {})
        with self._lock:
            analysis, quotes, qerr = dict(self._analysis), dict(self._quotes), dict(self._quote_errors)
        rows: list[dict] = []
        for sym in SCANNER_UNIVERSE:
            a = analysis.get(sym)
            base, quote = sym[:3], sym[3:6]
            row: dict = {"symbol": sym, "base": base, "quote": quote, "name": instrument_name(sym)}
            if a is None or "excluded" in a:
                row.update(
                    status={"key": "EXCLUDED", "label": "Excluded"},
                    score=None,
                    excluded_reason=(a or {}).get("excluded", "Awaiting first scanner cycle"),
                    reasons=[(a or {}).get("excluded", "Awaiting first scanner cycle")],
                )
                rows.append(row)
                continue
            q = quotes.get(sym)
            last_t, last_c = a["last_close"]
            price = q["bid"] if q else last_c
            price_at = q["tick_time"] if q else last_t
            ref = _close_at_or_before(a["h1"], price_at - timedelta(hours=24))
            change = None if ref is None else price - ref
            change_pct = None if not ref else change / ref * 100.0
            pr = pairs.get(sym)
            diff = pr["differential"] if pr else None
            usd_only = scores.get(quote, {}).get("AVG") if pr is None and quote in scores else None
            primary_tf = a["primary_tf"]
            structure = a["structures"][primary_tf]
            channel = regression_channel(a["d1"], s.channel_period, s.channel_width_sd, price)
            vol = a["volatility"]
            agrees = structure_agrees(structure["key"], diff)
            sc = inspection_score(
                s,
                abs_differential=None if diff is None else abs(diff),
                structure_key=structure["key"],
                agrees=agrees,
                channel_position=channel.get("position"),
                vol_key=vol["key"],
                alignment_pct=pr["alignment"]["pct"] if pr else None,
            )
            why = reasons(
                base=base,
                quote=quote,
                differential=diff,
                quote_only_score=usd_only,
                structure=structure,
                structure_tf=DISPLAY_TF[primary_tf],
                channel=channel,
                vol=vol,
                alignment=pr["alignment"] if pr else None,
            )
            row.update(
                price=price,
                price_at=_iso(price_at),
                price_live=q is not None,
                quote_error=qerr.get(sym),
                digits=q["digits"] if q else (2 if sym == GOLD else 3 if quote == "JPY" else 5),
                change_24h=change,
                change_24h_pct=None if change_pct is None else round(change_pct, 3),
                day_high=q["day_high"] if q and q["day_high"] is not None else a["d1"][-1].h,
                day_low=q["day_low"] if q and q["day_low"] is not None else a["d1"][-1].l,
                day_range_basis="CURRENT_D1" if q and q["day_high"] is not None else "LAST_CLOSED_D1",
                spread_points=q["spread_points"] if q else None,
                description=(q or {}).get("description") or None,
                strength={
                    "differential": diff,
                    "base_score": pr["base_strength"] if pr else None,
                    "quote_score": pr["quote_strength"] if pr else usd_only,
                    "relationship": pr["relationship"] if pr else None,
                    "alignment": pr["alignment"] if pr else None,
                    "base_class": pr["base_class"] if pr else None,
                    "quote_class": pr["quote_class"] if pr else None,
                },
                structure={**structure, "timeframe": DISPLAY_TF[primary_tf], "agrees_with_strength": agrees},
                channel=channel,
                volatility=vol,
                score=sc["score"],
                score_components=sc["components"],
                status=status_for(sc["score"], s),
                reasons=why,
                session=session_for(now),
            )
            rows.append(row)
        rows.sort(key=lambda r: (r["score"] is None, -(r["score"] or 0), r["symbol"]))
        for i, r in enumerate(rows):
            r["rank"] = i + 1
        return rows

    def _persist(self, conn, rows: list[dict]) -> None:
        tenant, account = active_scope(conn)
        with self._lock:
            cycle, at = self._cycle_id, self._cycle_at
        if at is None:
            return
        for r in rows:
            execute_retry(
                conn,
                """INSERT OR REPLACE INTO mi_scanner_snapshot(tenant_id,trading_account_id,cycle_id,as_of,symbol,status,
                     score,price,change_24h_pct,structure,channel,volatility,differential,reasons_json,details_json)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    tenant,
                    account,
                    cycle,
                    at.isoformat(),
                    r["symbol"],
                    r["status"]["key"],
                    r.get("score") or 0,
                    r.get("price"),
                    r.get("change_24h_pct"),
                    (r.get("structure") or {}).get("key"),
                    (r.get("channel") or {}).get("key"),
                    (r.get("volatility") or {}).get("key"),
                    (r.get("strength") or {}).get("differential"),
                    json.dumps(r.get("reasons", [])),
                    json.dumps(
                        {
                            "score_components": r.get("score_components"),
                            "structure": r.get("structure"),
                            "channel": r.get("channel"),
                            "volatility": r.get("volatility"),
                            "excluded_reason": r.get("excluded_reason"),
                        },
                        default=str,
                    ),
                ),
            )
        for row, a, view in self._range_entries():
            if not view or not view.get("available"):
                continue
            core = a["range_core"]
            execute_retry(
                conn,
                """INSERT OR REPLACE INTO mi_range_structure_snapshot(tenant_id,trading_account_id,cycle_id,as_of,symbol,
                     regime,range_state,range_high,range_low,position,developing_fractal,evidence_score,quality,
                     hypothesis,decision,details_json)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    tenant,
                    account,
                    cycle,
                    at.isoformat(),
                    row["symbol"],
                    core["regime"]["key"],
                    (core["state"] or {}).get("key"),
                    core["range_high"],
                    core["range_low"],
                    view["position"],
                    (view["developing_fractal"] or {}).get("kind"),
                    view["evidence_score"],
                    core["quality"],
                    view["summary_hypothesis"]["key"],
                    view["decision"]["key"],
                    json.dumps({"evidence": view["evidence"], "mtf": view["mtf"], "hypotheses": view["hypotheses"]}),
                ),
            )
        for r in self._overview_rows():
            if not r["available"]:
                continue
            reg = r["regimes"]
            execute_retry(
                conn,
                """INSERT OR REPLACE INTO mi_structure_overview_snapshot(tenant_id,trading_account_id,cycle_id,as_of,symbol,
                     regime_w,regime_d1,regime_h8,regime_h1,current_state,alignment_score,details_json)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    tenant,
                    account,
                    cycle,
                    at.isoformat(),
                    r["symbol"],
                    reg["W"],
                    reg["D1"],
                    reg["H8"],
                    reg["H1"],
                    r["state"]["key"],
                    r["strength"]["score"],
                    json.dumps(
                        {"cells": r["cells"], "events": [e for e in r["events"] if e["status"]["key"] != "DEVELOPING"][:10]},
                        default=str,
                    ),
                ),
            )
        for r in self._h8bb_rows():
            if not r["available"]:
                continue
            ev = r["event"] or {}
            confirmed = r["kind"] in ("BOS + BTL", "BOS", "BTL")
            execute_retry(
                conn,
                """INSERT OR REPLACE INTO mi_h8_bos_btl_snapshot(tenant_id,trading_account_id,cycle_id,as_of,symbol,
                     event_kind,confirmed,direction,event_at,bos_level,btl_level,break_strength_atr,retest_status,
                     h1_status,m30_status,analysis_id,details_json)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    tenant,
                    account,
                    cycle,
                    at.isoformat(),
                    r["symbol"],
                    r["kind"],
                    1 if confirmed else 0,
                    r["direction"],
                    ev.get("at") if confirmed else None,
                    (ev.get("bos") or {}).get("level") if confirmed else None,
                    (ev.get("btl") or {}).get("level") if confirmed else None,
                    ev.get("break_strength_atr") if confirmed else None,
                    (r["retest_status"] or {}).get("key"),
                    r["h1_status"]["key"],
                    r["m30_status"]["key"],
                    ev.get("analysis_id") if confirmed else None,
                    json.dumps(
                        {"event": ev if confirmed else None, "developing": r["developing"], "weekly": r["weekly"]},
                        default=str,
                    ),
                ),
            )
        for r in self._trend_rows(closed_only=True):
            if not r["available"]:
                continue
            v = r["_view"]
            geo = v["geometry"] or {}
            execute_retry(
                conn,
                """INSERT OR REPLACE INTO mi_trend_structure_snapshot(tenant_id,trading_account_id,cycle_id,as_of,symbol,
                     direction,trend_state,strength,age_weeks,cell_w,cell_d1,cell_h8,cell_h1,setup,pullback_depth_pct,
                     analysis_close_at,details_json)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    tenant,
                    account,
                    cycle,
                    at.isoformat(),
                    r["symbol"],
                    v["direction"],
                    v["state"]["key"],
                    v["strength"],
                    v["age_weeks"],
                    *((v["cells"].get(tf) or {}).get("key") for tf in TREND_TIMEFRAMES),
                    v["setup"]["key"],
                    geo.get("depth_pct"),
                    v["anchor"],
                    json.dumps(
                        {
                            "components": v["components"],
                            "health": v["health"],
                            "geometry": geo or None,
                            "structure_sequence": v["structure_sequence"],
                            "reversal_reasons": v["reversal_reasons"],
                            "events": r["_events"],
                        },
                        default=str,
                    ),
                ),
            )
        conn.commit()

    def meta(self) -> dict:
        with self._lock:
            ctx, state, error = dict(self._ctx), self._state, self._error
            cycle_id, cycle_at, quotes_at = self._cycle_id, self._cycle_at, self._quotes_at
            rows = list(self._rows)
        strength = get_strength_engine().engine_meta() or {}
        connected = bool(ctx.get("mt5_connected") and ctx.get("market_data_ready"))
        now = datetime.now(timezone.utc)
        stale_reason = None
        if not connected:
            stale_reason = "MT5_DISCONNECTED"
        elif cycle_at is None or (now - cycle_at).total_seconds() > max(STALE_AFTER_SECONDS, settings().analysis_seconds * 3):
            stale_reason = "SCANNER_STALLED" if cycle_at else None
        scanned = sum(1 for r in rows if r["status"]["key"] != "EXCLUDED")
        return {
            "engine_state": state,
            "engine_error": error,
            "mt5_connected": connected,
            "mt5_server": ctx.get("mt5_server"),
            "cycle_id": cycle_id,
            "last_cycle_at": _iso(cycle_at),
            "quotes_at": _iso(quotes_at),
            "instruments_total": len(SCANNER_UNIVERSE),
            "instruments_scanned": scanned,
            "fx_pairs": len(SCANNER_UNIVERSE) - 1,
            "strength_as_of": strength.get("as_of"),
            "strength_live": strength.get("live_data"),
            "strength_stale_reason": strength.get("stale_reason"),
            "currencies": 8,
            "stale": stale_reason is not None,
            "stale_reason": stale_reason,
            "closed_bar_analysis": True,
            "settings": settings_payload(),
            "analysis_only": True,
        }

    def payload(self) -> dict:
        with self._lock:
            rows = list(self._rows)
        counts = {k: sum(1 for r in rows if r["status"]["key"] == k) for k in ("HIGH_INSPECTION", "WATCHING", "NEUTRAL", "EXCLUDED")}
        return {"meta": self.meta(), "counts": counts, "rows": [_public(r) for r in rows]}

    def detail(self, symbol: str) -> dict | None:
        sym = symbol.upper()
        with self._lock:
            row = next((r for r in self._rows if r["symbol"] == sym), None)
            a = self._analysis.get(sym)
        if row is None:
            return None
        out = _public(row)
        if a and "structures" in a:
            out["structures"] = [{"timeframe": DISPLAY_TF[tf], **a["structures"][tf]} for tf in STRUCTURE_TIMEFRAMES]
        pairs = (get_strength_engine().intelligence() or {}).get("pairs", [])
        out["strength_timeframes"] = next((p["timeframes"] for p in pairs if p["pair"] == sym), None)
        return {"meta": self.meta(), "instrument": out}

    # ----- Range Structure (Market Structure → Range Structure) -----

    def _range_entries(self) -> list[tuple[dict, dict | None, dict | None]]:
        """(public row, analysis, live view) for every instrument, in universe order."""
        s = range_settings()
        with self._lock:
            rows = {r["symbol"]: r for r in self._rows}
            analysis = dict(self._analysis)
        out = []
        for sym in SCANNER_UNIVERSE:
            row, a = rows.get(sym), analysis.get(sym)
            if row is None or a is None or "range_core" not in a or row.get("price") is None:
                out.append((row or {"symbol": sym, "base": sym[:3], "quote": sym[3:6], "name": instrument_name(sym)}, None, None))
                continue
            out.append((row, a, range_view(a["range_core"], a["range_ltf"], row["price"], s)))
        return out

    @staticmethod
    def _range_row(row: dict, a: dict | None, view: dict | None) -> dict:
        sym = row["symbol"]
        base = {
            "symbol": sym,
            "base": row.get("base", sym[:3]),
            "quote": row.get("quote", sym[3:6]),
            "name": row.get("name") or instrument_name(sym),
            "asset": "Commodity" if sym == GOLD else "Forex",
            "digits": row.get("digits"),
            "price": row.get("price"),
            "price_live": row.get("price_live", False),
            "change": row.get("change_24h"),
            "change_pct": row.get("change_24h_pct"),
        }
        if a is None or view is None or not view.get("available"):
            core = (a or {}).get("range_core") or {}
            return {
                **base,
                "available": False,
                "regime": core.get("regime") or {"key": "INSUFFICIENT", "label": "Insufficient data"},
                "unavailable_reason": row.get("excluded_reason") or "Insufficient closed weekly history",
            }
        core = a["range_core"]
        mtf = {m["timeframe"]: m["structure"]["label"] for m in view["mtf"]}
        dev = view["developing_fractal"]
        return {
            **base,
            "available": True,
            "regime": core["regime"],
            "state": core["state"],
            "ranging": core["ranging"],
            "range_high": core["range_high"],
            "range_low": core["range_low"],
            "midpoint": core["midpoint"],
            "width": core["width"],
            "width_atr": core["width_atr"],
            "age_weeks": core["age_weeks"],
            "touches_high": core["touches_high"],
            "touches_low": core["touches_low"],
            "false_breakouts": core["false_breakouts"],
            "quality": core["quality"],
            "reliability": core["reliability"],
            "position": view["position"],
            "position_band": view["position_band"],
            "developing_fractal": None if dev is None else {"kind": dev["kind"], "price": dev["price"]},
            "fractal_kind": view["fractal_kind"],
            "evidence_score": view["evidence_score"],
            "mtf": {"W": mtf.get("W"), "D1": mtf.get("D1"), "H8": mtf.get("H8")},
            "hypothesis": view["summary_hypothesis"],
            "breakout_score": (view["hypotheses"] or {}).get("breakout", {}).get("score"),
            "decision": view["decision"]["key"],
        }

    def range_payload(self) -> dict:
        rows = [self._range_row(*e) for e in self._range_entries()]
        ok = [r for r in rows if r["available"]]
        ranging = [r for r in ok if r["ranging"]]
        s = range_settings()
        counts = {
            "ranging": len(ranging),
            "near_upper": sum(1 for r in ranging if r["position"] >= 100 - s.extreme_pct),
            "near_lower": sum(1 for r in ranging if r["position"] <= s.extreme_pct),
            "breakout_risk": sum(
                1
                for r in ranging
                if (r["state"] or {}).get("key") == "BREAKOUT_THREAT" or (r["breakout_score"] or 0) >= s.hypothesis_min
            ),
            "all": len(rows),
        }
        return {"meta": {**self.meta(), "range_settings": range_settings_payload()}, "counts": counts, "rows": rows}

    def range_detail(self, symbol: str) -> dict | None:
        sym = symbol.upper()
        entry = next((e for e in self._range_entries() if e[0]["symbol"] == sym), None)
        if entry is None:
            return None
        row, a, view = entry
        summary = self._range_row(row, a, view)
        if not summary["available"]:
            return {"meta": self.meta(), "summary": summary, "available": False}
        core = a["range_core"]
        ltf = a["range_ltf"]
        channels = {
            tf: {k: ltf[tf]["channel"].get(k) for k in ("key", "upper", "mid", "lower", "slope_pct_per_bar", "direction", "period")}
            for tf in ("D1", "H8")
        }
        return {
            "meta": {**self.meta(), "range_settings": range_settings_payload()},
            "available": True,
            "summary": summary,
            "range": {k: v for k, v in core.items() if k not in ("developing",)},
            "developing_candidates": core["developing"],
            "view": view,
            "channels": channels,
            "last_closed": {tf: ltf[tf]["last_close"] for tf in ("D1", "H8", "H1")},
        }

    # ----- Structure Overview (Market Structure → Structure Overview) -----

    @staticmethod
    def _overview_core(bars: dict[str, list[Bar]], range_core: dict, rs) -> dict:
        s = overview_settings()
        w1, h1 = bars["W1"], bars["H1"]
        prev_week = None
        if w1 and h1:
            since = h1[-1].t + TF_DELTA["H1"] - timedelta(hours=s.regime_change_hours)
            if w1[-1].t + TF_DELTA["W"] > since:
                prev_week = weekly_range(w1[:-1], rs)
        return overview_core(bars, range_core, prev_week, s)

    def _overview_rows(self) -> list[dict]:
        s = overview_settings()
        now = datetime.now(timezone.utc)
        out = []
        for row, a, view in self._range_entries():
            sym = row["symbol"]
            base = {
                "symbol": sym,
                "base": row.get("base", sym[:3]),
                "quote": row.get("quote", sym[3:6]),
                "name": row.get("name") or instrument_name(sym),
                "asset": "Commodity" if sym == GOLD else "Forex",
                "digits": row.get("digits"),
                "price": row.get("price"),
            }
            ov = (a or {}).get("overview")
            if not ov or ov["regimes"]["W"] is None:
                out.append({**base, "available": False, "reason": row.get("excluded_reason") or "Insufficient closed history"})
                continue
            regimes = ov["regimes"]
            cells = cells_for(regimes)
            live = view if view and view.get("available") else None
            band = (live or {}).get("position_band", {}).get("key")
            core = a["range_core"]
            events = live_events(ov, row.get("price"), now, s)
            out.append(
                {
                    **base,
                    "available": True,
                    "regime": {"key": regimes["W"], "label": REGIMES[regimes["W"]]},
                    "regimes": regimes,
                    "cells": cells,
                    "state": current_state(regimes, cells, band),
                    "strength": alignment(regimes, s),
                    "ranging": bool(core.get("ranging")),
                    "range_age_weeks": core["age_weeks"] if core.get("ranging") else None,
                    "range_state": core.get("state"),
                    "position": (live or {}).get("position"),
                    "position_band": (live or {}).get("position_band"),
                    "breakout_score": ((live or {}).get("hypotheses") or {}).get("breakout", {}).get("score"),
                    "events": events,
                    "changes": ov["changes"],
                    "anchor": ov["anchor"],
                }
            )
        return out

    def structure_overview_payload(self) -> dict:
        s = overview_settings()
        rs = range_settings()
        rows = self._overview_rows()
        ok = [r for r in rows if r["available"]]
        counts = {k.lower(): sum(1 for r in ok if r["regime"]["key"] == k) for k in REGIMES}
        mtf = {
            tf: {k.lower(): sum(1 for r in ok if r["regimes"].get(tf) == k) for k in REGIMES}
            for tf in OVERVIEW_TIMEFRAMES
        }
        by_strength = sorted(ok, key=lambda r: (-r["strength"]["score"], r["symbol"]))
        def top(rr: list[dict]) -> list[dict]:
            return [{"symbol": r["symbol"], "base": r["base"], "quote": r["quote"], "strength": r["strength"]} for r in rr]

        events = sorted(
            ({"symbol": r["symbol"], "digits": r["digits"], **e} for r in ok for e in r["events"]),
            key=lambda e: (e["at"], -EVENT_TIMEFRAMES.index(e["tf"])),
            reverse=True,
        )
        changes = sorted(({"symbol": r["symbol"], **c} for r in ok for c in r["changes"]), key=lambda c: c["at"], reverse=True)
        attention = [x for x in (self._attention(r, s) for r in ok) if x]
        attention.sort(key=lambda x: (x.pop("_rank"), x["symbol"]))
        return {
            "meta": {**self.meta(), "overview_settings": overview_settings_payload(), "data_as_of": max((r["anchor"] or "" for r in ok), default=None)},
            "counts": {"analysed": len(ok), "total": len(rows), **counts},
            "mtf": mtf,
            "strongest": top(by_strength[: s.top_n]),
            "weakest": top(list(reversed(by_strength))[: s.top_n]),
            "rows": [{k: v for k, v in r.items() if k not in ("events", "changes", "regimes", "anchor")} for r in rows],
            "events": events[:60],
            "regime_changes": changes[:60],
            "attention": attention,
            "opportunities": self._opportunities(ok, s, rs),
        }

    @staticmethod
    def _recent(e: dict, anchor: str | None, hours: float) -> bool:
        if not anchor:
            return False
        return datetime.fromisoformat(e["at"]) >= datetime.fromisoformat(anchor) - timedelta(hours=hours)

    @classmethod
    def _reversal_choch(cls, e: dict, anchor: str | None, s) -> bool:
        """A confirmed CHoCH on H8 or higher within the regime-change window."""
        return (
            e["kind"] == "CHOCH"
            and e["tf"] in REVERSAL_TIMEFRAMES
            and e["status"]["key"] in ("CONFIRMED", "RETESTING")
            and cls._recent(e, anchor, s.regime_change_hours)
        )

    def _attention(self, r: dict, s) -> dict | None:
        """Highest-priority structural reason a symbol needs a look (analysis only)."""
        sym, ev, state = r["symbol"], r["events"], r["state"]["key"]
        band = (r.get("position_band") or {}).get("key")

        def item(rank: int, reason: str, tf: str, detail: str, status: str, label: str) -> dict:
            return {"_rank": rank, "symbol": sym, "reason": reason, "tf": tf, "detail": detail, "status": {"key": status, "label": label}}

        dev = sorted((e for e in ev if e["status"]["key"] == "DEVELOPING"), key=lambda e: EVENT_TIMEFRAMES.index(e["tf"]))
        if dev:
            e = dev[0]
            return item(0, "Structure break", e["tf"], f"{e['label']} developing", "DEVELOPING", "Developing")
        if r["ranging"] and band in ("UPPER_EXTREME", "ABOVE_RANGE"):
            return item(1, "Near upper range", "W", "Price near weekly resistance", "WATCHING", "Watching")
        if r["ranging"] and band in ("LOWER_EXTREME", "BELOW_RANGE"):
            return item(1, "Near lower range", "W", "Price near weekly support", "WATCHING", "Watching")
        choch = next((e for e in ev if self._reversal_choch(e, r["anchor"], s)), None)
        if choch:
            return item(2, "Reversal candidate", choch["tf"], f"{choch['label']} detected", choch["status"]["key"], choch["status"]["label"])
        ret = next((e for e in ev if e["status"]["key"] == "RETESTING"), None)
        if ret:
            return item(3, "Retesting key level", ret["tf"], f"Retesting {ret['label']} level", "RETESTING", "Retesting")
        if state == "CONTINUATION":
            tf = next(t for t in ("H8", "H1") if (r["cells"].get(t) or {}).get("key") == "PULLBACK")
            return item(4, "Pullback in trend", tf, "Counter-move against higher-TF trend", "WATCHING", "Watching")
        score = r["strength"]["score"]
        if score >= s.strong_alignment or score <= 100 - s.strong_alignment:
            word = "Bullish" if score >= 50 else "Bearish"
            return item(5, f"{word} continuation", "MTF", f"Strong {word.lower()} alignment", "ALERT", "Alert")
        if state == "TRANSITION":
            return item(6, "Transition state", "W", "Mixed structure", "CONFIRMATION", "Confirmation")
        return None

    def _opportunities(self, ok: list[dict], s, rs) -> list[dict]:
        def is_breakout(r):
            band = (r.get("position_band") or {}).get("key")
            return r["ranging"] and (
                band in ("ABOVE_RANGE", "BELOW_RANGE")
                or (r.get("range_state") or {}).get("key") == "BREAKOUT_THREAT"
                or (r.get("breakout_score") or 0) >= rs.hypothesis_min
            )

        def is_reversal(r):
            return r["state"]["key"] == "REVERSAL" or any(self._reversal_choch(e, r["anchor"], s) for e in r["events"])

        groups = (
            ("TREND_CONTINUATION", "Trend Continuation", lambda r: r["state"]["key"] in ("TRENDING", "CONTINUATION")),
            ("BREAKOUT_WATCH", "Breakout Watch", is_breakout),
            ("REVERSAL_SETUP", "Reversal Setup", is_reversal),
            ("PULLBACK_SETUP", "Pullback Setup", lambda r: r["regime"]["key"] in ("BULLISH", "BEARISH") and any((c or {}).get("key") == "PULLBACK" for c in r["cells"].values())),
            ("CONFIRMATION_PENDING", "Confirmation Pending", lambda r: r["state"]["key"] == "TRANSITION" or any(e["status"]["key"] == "DEVELOPING" for e in r["events"])),
        )
        out = []
        for key, label, pred in groups:
            hits = sorted((r for r in ok if pred(r)), key=lambda r: -abs(r["strength"]["score"] - 50))
            out.append({"key": key, "label": label, "count": len(hits), "examples": [r["symbol"] for r in hits[:3]]})
        return out

    # ----- H8 BOS & BTL Intelligence (Market Vision → H8 BOS & BTL) -----

    @staticmethod
    def _h8bb_core(bars: dict[str, list[Bar]]) -> dict:
        s = h8_bos_btl_settings()
        h8 = h8_core(bars["H8"], s)
        event = h8.get("event")
        return {
            "weekly": weekly_core(bars["W1"], s),
            "h8": h8,
            "h1": h1_validation(bars["H1"], event, s),
            "m30": m30_confirmation(bars["M30"], event, s),
            "bars": {
                "W": bars["W1"][-H8BB_CHART_BARS["W"] :],
                "H8": bars["H8"][-H8BB_CHART_BARS["H8"] :],
                "H1": bars["H1"][-H8BB_CHART_BARS["H1"] :],
                "M30": bars["M30"][-H8BB_CHART_BARS["M30"] :],
            },
        }

    def _h8bb_rows(self) -> list[dict]:
        s = h8_bos_btl_settings()
        with self._lock:
            rows = {r["symbol"]: r for r in self._rows}
            analysis = dict(self._analysis)
        out = []
        for sym in SCANNER_UNIVERSE:
            row = rows.get(sym) or {}
            base = {
                "symbol": sym,
                "base": sym[:3],
                "quote": sym[3:6],
                "name": row.get("name") or instrument_name(sym),
                "digits": row.get("digits") or (2 if sym == GOLD else 3 if sym.endswith("JPY") else 5),
                "price": row.get("price"),
                "price_at": row.get("price_at"),
            }
            core = (analysis.get(sym) or {}).get("h8bb")
            if not core or not core["h8"].get("available"):
                reason = row.get("excluded_reason") or (core or {}).get("h8", {}).get("reason") or "Awaiting first scanner cycle"
                out.append({**base, "available": False, "reason": reason, "kind": "MONITORING", "priority": ALERT_PRIORITY["MONITORING"]})
                continue
            h8 = core["h8"]
            h8_bars = core["bars"]["H8"]
            live = h8_live(h8, h8_bars[-1] if h8_bars else None, base["price"], s)
            weekly = weekly_live(core["weekly"], base["price"])
            ev = h8["event"] if live["kind"] in ("BOS + BTL", "BOS", "BTL") else None
            dev = live["developing"]
            out.append(
                {
                    **base,
                    "available": True,
                    "kind": live["kind"],
                    "priority": ALERT_PRIORITY[live["kind"]],
                    "direction": ev["direction"] if ev else dev["direction"] if dev else h8["direction"],
                    "event": ev,
                    "developing": dev,
                    "retest_status": live["retest_status"],
                    "h8": h8,
                    "h1": core["h1"],
                    "m30": core["m30"],
                    "h1_status": core["h1"]["status"],
                    "m30_status": core["m30"]["status"],
                    "weekly": {k: v for k, v in weekly.items() if k not in ("fractals", "sch")} if weekly.get("available") else weekly,
                    "_weekly_full": weekly,
                    "_bars": core["bars"],
                }
            )
        return out

    @staticmethod
    def _h8bb_alert(r: dict) -> dict:
        ev, dev = r.get("event"), r.get("developing")
        levels = {}
        if ev:
            if ev["bos"]:
                levels["bos"] = ev["bos"]["level"]
            if ev["btl"]:
                levels["btl"] = ev["btl"]["level"]
        elif dev:
            levels[dev["event"].lower()] = dev["level"]
        proof = [p["proof"] for p in (ev["bos"], ev["btl"]) if p] if ev else ([dev["detail"]] if dev else [])
        return {
            "symbol": r["symbol"],
            "base": r["base"],
            "quote": r["quote"],
            "kind": r["kind"],
            "direction": r.get("direction"),
            "priority": r["priority"],
            "at": ev["at"] if ev else r.get("price_at") if dev else None,
            "levels": levels,
            "closed_bar_proof": proof,
            "closed_bar": bool(ev),
            "analysis_id": ev["analysis_id"] if ev else None,
            "digits": r["digits"],
        }

    def h8_bos_btl_payload(self) -> dict:
        rows = self._h8bb_rows()
        ok = [r for r in rows if r["available"]]
        counts = {k: sum(1 for r in ok if r["kind"] == k) for k in ALERT_KINDS}
        alerts = sorted(
            (self._h8bb_alert(r) for r in rows),
            key=lambda a: (a["priority"], -(datetime.fromisoformat(a["at"]).timestamp() if a["at"] else 0), a["symbol"]),
        )
        return {
            "meta": {**self.meta(), "h8bb_settings": h8_bos_btl_settings_payload()},
            "counts": {"scanned": len(ok), "total": len(rows), **counts},
            "alerts": alerts,
        }

    def h8_bos_btl_detail(self, symbol: str) -> dict | None:
        sym = symbol.upper()
        r = next((x for x in self._h8bb_rows() if x["symbol"] == sym), None)
        if r is None:
            return None
        summary = self._h8bb_alert(r)
        if not r["available"]:
            return {"meta": self.meta(), "available": False, "symbol": sym, "summary": summary, "reason": r["reason"], "name": r["name"], "digits": r["digits"]}
        h8, h1, m30, weekly = r["h8"], r["h1"], r["m30"], r["_weekly_full"]
        kind_label = {"DEVELOPING": "Developing", "MONITORING": "Monitoring"}.get(r["kind"], r["kind"])
        mtf = [
            {"tf": "W", "structure": "Fractal + SCH", "direction": weekly.get("direction"), "status": weekly.get("state")},
            {"tf": "H8", "structure": h8["structure"], "direction": r["direction"], "status": kind_label},
            {"tf": "H1", "structure": h1["structure"], "direction": h1["direction"], "status": h1["status"]["label"]},
            {"tf": "M30", "structure": m30["structure"], "direction": m30["direction"], "status": m30["status"]["label"]},
        ]

        def candles(tf: str) -> list[dict]:
            return [{"t": b.t.isoformat(), "o": b.o, "h": b.h, "l": b.l, "c": b.c} for b in r["_bars"][tf]]

        return {
            "meta": {**self.meta(), "h8bb_settings": h8_bos_btl_settings_payload()},
            "available": True,
            "symbol": sym,
            "name": r["name"],
            "digits": r["digits"],
            "price": r["price"],
            "price_at": r["price_at"],
            "summary": summary,
            "kind": r["kind"],
            "direction": r["direction"],
            "event": r["event"],
            "developing": r["developing"],
            "retest_status": r["retest_status"],
            "h8": {k: v for k, v in h8.items() if k != "event"},
            "h1": h1,
            "m30": m30,
            "weekly": weekly,
            "mtf": mtf,
            "evidence": self._h8bb_evidence(r),
            "scenarios": self._h8bb_scenarios(r),
            "candles": {tf: candles(tf) for tf in ("W", "H8", "H1", "M30")},
        }

    @staticmethod
    def _h8bb_evidence(r: dict) -> list[dict]:
        ev, dev, w, h1, m30 = r["event"], r["developing"], r["_weekly_full"], r["h1"], r["m30"]
        out = []
        if ev:
            for p in (ev["bos"], ev["btl"]):
                if p:
                    out.append({"tf": "H8", "label": f"{p['direction']} {p['kind']}", "detail": p["proof"], "confirmed": True})
            out.append({"tf": "H8", "label": "Retest", "detail": (r["retest_status"] or {}).get("label"), "confirmed": None})
        elif dev:
            out.append({"tf": "H8", "label": f"{dev['direction']} {dev['event']} developing", "detail": dev["detail"], "confirmed": False})
        else:
            out.append({"tf": "H8", "label": "No active break", "detail": "No closed H8 BOS or BTL inside the active window", "confirmed": None})
        for x in h1.get("sequence", []):
            out.append({"tf": "H1", "label": x["label"], "detail": f"Confirmed swing at {x['t'][:16].replace('T', ' ')} UTC", "confirmed": True})
        out.append({"tf": "H1", "label": "Validation", "detail": h1["status"]["label"], "confirmed": h1["status"]["key"] == "CONFIRMED"})
        for x in m30.get("markers", []):
            out.append({"tf": "M30", "label": x["label"], "detail": f"Closed M30 bar at {x['t'][:16].replace('T', ' ')} UTC", "confirmed": True})
        out.append({"tf": "M30", "label": "Confirmation", "detail": m30["status"]["label"], "confirmed": m30["status"]["key"] == "LTF_CONFIRMED"})
        if w.get("available"):
            cross = "" if w["cross_bars_ago"] is None else f", last cross {w['cross_bars_ago']} week(s) ago"
            out.append({"tf": "W", "label": f"SCH {w['direction']}", "detail": f"Fast {w['fast']} / signal {w['signal']}{cross}", "confirmed": True})
            out.append({"tf": "W", "label": "Fractal state", "detail": w.get("fractal_state") or "Undefined", "confirmed": None})
        return out

    @staticmethod
    def _h8bb_scenarios(r: dict) -> list[dict]:
        ev, dev, h8, d = r["event"], r["developing"], r["h8"], r["digits"]

        def f(x: float | None) -> str:
            return "—" if x is None else f"{x:.{d}f}"

        if ev:
            lo, hi = ev["retest"]
            bear = ev["direction"] == "Bearish"
            back = f(hi) if bear else f(lo)
            return [
                {"key": "CONTINUATION", "title": "Structure holds", "detail": f"H8 closes stay {'below' if bear else 'above'} the retest zone {f(lo)}–{f(hi)}; H1 {'LH→LL' if bear else 'HL→HH'} and M30 reaction confirm the {ev['kind']} break."},
                {"key": "RECLAIM", "title": "Level reclaimed", "detail": f"An H8 close {'above' if bear else 'below'} {back} reclaims the broken level and retires the event."},
                {"key": "INVALIDATION", "title": "Invalidation", "detail": f"An H8 close {'above' if bear else 'below'} {f(ev['invalidation'])} invalidates the {ev['direction'].lower()} structure."},
            ]
        if dev:
            return [
                {"key": "CONFIRM", "title": "Confirmation", "detail": f"An H8 close beyond {f(dev['level'])} confirms a {dev['direction'].lower()} {dev['event']}."},
                {"key": "REJECT", "title": "Rejection", "detail": f"An H8 close back inside {f(dev['level'])} leaves the level intact (wick only)."},
            ]
        p = h8["pending"]
        out = []
        if p["swing_low"] is not None:
            out.append({"key": "BOS_DOWN", "title": "Bearish BOS", "detail": f"H8 close below swing low {f(p['swing_low'])}."})
        if p["swing_high"] is not None:
            out.append({"key": "BOS_UP", "title": "Bullish BOS", "detail": f"H8 close above swing high {f(p['swing_high'])}."})
        if p["support"]:
            out.append({"key": "BTL_DOWN", "title": "Bearish BTL", "detail": f"H8 close below the rising trend line (≈{f(p['support']['level'])})."})
        if p["resistance"]:
            out.append({"key": "BTL_UP", "title": "Bullish BTL", "detail": f"H8 close above the falling trend line (≈{f(p['resistance']['level'])})."})
        return out


    # ----- Trend Structure (Market Structure → Trend Structure) -----

    def _trend_rows(self, *, closed_only: bool = False) -> list[dict]:
        """Per-instrument trend view. ``closed_only`` ignores the live quote (persistence never stores developing state)."""
        s, ovs = trend_settings(), overview_settings()
        now = datetime.now(timezone.utc)
        with self._lock:
            rows = {r["symbol"]: r for r in self._rows}
            analysis = dict(self._analysis)
        out = []
        for sym in SCANNER_UNIVERSE:
            row = rows.get(sym) or {}
            a = analysis.get(sym) or {}
            base = {
                "symbol": sym,
                "base": sym[:3],
                "quote": sym[3:6],
                "name": row.get("name") or instrument_name(sym),
                "asset": "Commodity" if sym == GOLD else "Forex",
                "digits": row.get("digits") or (2 if sym == GOLD else 3 if sym.endswith("JPY") else 5),
                "price": row.get("price"),
            }
            ov, core = a.get("overview"), a.get("trend")
            if not ov or not core or ov["regimes"].get("W") is None:
                reason = row.get("excluded_reason") or a.get("excluded") or "Insufficient closed history"
                out.append({**base, "available": False, "reason": reason})
                continue
            price = None if closed_only else base["price"]
            view = trend_view(core, ov, price, now, s, ovs)
            if not view["available"]:
                out.append({**base, "available": False, "reason": view["reason"]})
                continue
            out.append({**base, "available": True, "_view": view, "_core": core,
                        "_events": trend_events(core, ov, price, now, s, ovs)})
        return out

    @staticmethod
    def _trend_public(r: dict) -> dict:
        base = {k: v for k, v in r.items() if not k.startswith("_")}
        if not r["available"]:
            return base
        v = r["_view"]
        return {
            **base,
            "direction": v["direction"],
            "cells": v["cells"],
            "state": v["state"],
            "strength": v["strength"],
            "age_weeks": v["age_weeks"],
            "setup": v["setup"]["key"],
            "pullback": bool(v["state"]["key"].endswith("PULLBACK")),
            "reversal_risk": v["setup"]["key"] == "REVERSAL_RISK",
        }

    def trend_structure_payload(self) -> dict:
        rows = [self._trend_public(r) for r in self._trend_rows()]
        ok = [r for r in rows if r["available"]]
        counts = {
            "analysed": len(ok),
            "total": len(rows),
            "trending": sum(1 for r in ok if r["direction"]),
            "bullish": sum(1 for r in ok if r["direction"] == "BULLISH"),
            "bearish": sum(1 for r in ok if r["direction"] == "BEARISH"),
            "pullback": sum(1 for r in ok if r["pullback"]),
            "continuation": sum(1 for r in ok if r["setup"] == "CONTINUATION"),
            "reversal_risk": sum(1 for r in ok if r["reversal_risk"]),
        }
        rows.sort(key=lambda r: (not r["available"], not r.get("direction"), -(r.get("strength") or 0), r["symbol"]))
        return {"meta": {**self.meta(), "trend_settings": trend_settings_payload()}, "counts": counts, "rows": rows}

    def trend_structure_detail(self, symbol: str) -> dict | None:
        sym = symbol.upper()
        r = next((x for x in self._trend_rows() if x["symbol"] == sym), None)
        if r is None:
            return None
        summary = self._trend_public(r)
        meta = {**self.meta(), "trend_settings": trend_settings_payload()}
        if not r["available"]:
            return {"meta": meta, "available": False, "summary": summary}
        v, core = r["_view"], r["_core"]
        return {
            "meta": meta,
            "available": True,
            "summary": summary,
            "view": {k: v[k] for k in v if k not in ("cells", "regimes")},
            "mtf": mtf_rows(core, v),
            "events": r["_events"],
            "channels": {tf: (core.get(tf) or {}).get("channel") for tf in TREND_TIMEFRAMES},
            "last_closed": {tf: (core.get(tf) or {}).get("closed_at") for tf in TREND_TIMEFRAMES},
        }


def _close_at_or_before(h1: list[Bar], at: datetime) -> float | None:
    """Close of the last H1 bar that had closed by ``at`` (24h change anchored to the price time, not wall clock)."""
    for b in reversed(h1):
        if b.t + timedelta(hours=1) <= at:
            return b.c
    return None


def _public(row: dict) -> dict:
    return {k: v for k, v in row.items() if k != "d1"}


def chart_candles(symbol: str, timeframe: str, limit: int) -> dict:
    tf = CHART_TIMEFRAMES.get(timeframe.upper())
    if tf is None:
        raise ValueError(f"Unsupported chart timeframe: {timeframe}")
    if symbol.upper() not in SCANNER_UNIVERSE:
        raise ValueError(f"Unknown instrument: {symbol}")
    with db() as conn:
        rows = MarketRepository(conn).candles(symbol.upper(), tf, limit)
    candles = []
    for r in rows:
        t = datetime.fromisoformat(r[0])
        t = t if t.tzinfo else t.replace(tzinfo=timezone.utc)
        candles.append({"t": t.isoformat(), "o": r[2], "h": r[3], "l": r[4], "c": r[5], "v": r[6]})
    return {"symbol": symbol.upper(), "timeframe": timeframe.upper(), "closed_only": True, "candles": candles}


_engine: MarketScannerEngine | None = None
_engine_lock = threading.Lock()


def get_scanner_engine() -> MarketScannerEngine:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = MarketScannerEngine()
        return _engine


def scanner_enabled() -> bool:
    return os.getenv("MARKET_SCANNER_ENABLED", "1").strip().lower() not in ("0", "false", "no")

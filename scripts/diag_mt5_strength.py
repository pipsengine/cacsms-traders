"""One-off MT5 + DB diagnostics for Strength 0/28 (run on the MT5 host)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_PATH", str(ROOT / "database" / "db_cacsms-traders.db"))


def main() -> None:
    from apps.api.app.core.database import db, db_path
    from apps.api.app.market.constants import FX_PAIRS_28
    from apps.api.app.market import mt5_session
    from apps.api.app.domain.mt5_connection import ensure_gateway_session, LocalMT5Gateway
    from apps.api.app.market.market_data import configuration, market_context
    from apps.api.app.market.strength_engine import get_strength_engine
    from apps.api.app.market.mt5_gateway import symbol_candidates, Mt5MarketDataGateway

    tenant = "tenant-cacsms"
    print("database_path", db_path())
    with db() as conn:
        cfg = configuration(conn)
        ctx = market_context(conn)
        print("market_data.provider", json.dumps(cfg, indent=2))
        print("market_context ready", ctx.get("market_data_ready"), "provider", ctx.get("active_provider"))
        gw = LocalMT5Gateway(tenant)
        settings = gw.settings(conn)
        print("mt5.local session", settings.get("session_status"), "path", settings.get("terminal_path"))
        restore = ensure_gateway_session(conn, tenant)
        print("ensure_gateway_session", restore)
        print("mt5_session initialized", mt5_session.is_initialized())

    meta = get_strength_engine().engine_meta()
    print("strength engine_meta", json.dumps({k: meta.get(k) for k in sorted(meta or {}) if k in (
        "engine_state", "pairs_loaded", "pairs_total", "symbols_resolved", "missing_pairs",
        "market_data_ready", "provider_status", "error_code", "failed_candle_requests",
        "closed_bar_status", "engine_error", "snapshot_id",
    )}, indent=2))

    if not mt5_session.is_initialized():
        print("SKIP MT5 IPC probes — not initialized")
        return

    import MetaTrader5 as mt5  # type: ignore

    ti = mt5.terminal_info()
    ai = mt5.account_info()
    print("terminal_info", ti.name if ti else None, "connected", getattr(ti, "connected", None) if ti else None)
    print("account_info", ai.login if ai else None, ai.server if ai else None)

    adapter = Mt5MarketDataGateway()
    resolved = []
    missing = []
    sample_rates = {}
    for pair in FX_PAIRS_28:
        row = adapter.get_symbol(pair)
        if row:
            resolved.append(pair)
        else:
            missing.append(pair)
            cands = symbol_candidates(pair)
            errs = []
            for sym in cands[:5]:
                mt5.symbol_select(sym, True)
                info = mt5.symbol_info(sym)
                if info is None:
                    errs.append(f"{sym}:no_info")
                    continue
                rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 5)
                if rates is None or len(rates) == 0:
                    errs.append(f"{sym}:no_rates({mt5.last_error()})")
                else:
                    sample_rates[pair] = (sym, len(rates), int(rates[-1]["time"]))
                    break
            if pair not in sample_rates:
                print(f"MISSING {pair} tried {cands[:5]} -> {errs}")

    print(f"symbols resolved via get_symbol: {len(resolved)}/28")
    print("missing", missing[:10], "..." if len(missing) > 10 else "")
    print("sample H1 rates", list(sample_rates.items())[:5])

    with db() as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%candle%'"
        ).fetchall()
        print("candle tables", [r[0] for r in tables])
        for t in [r[0] for r in tables]:
            try:
                n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                print(f"  {t} rows", n)
            except Exception as exc:
                print(f"  {t} err", exc)


if __name__ == "__main__":
    main()

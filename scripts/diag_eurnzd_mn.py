"""Inspect MT5 EURNZD MN raw rates and normalization."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_PATH", str(ROOT / "database" / "db_cacsms-traders.db"))


def main() -> None:
    from datetime import datetime, timezone
    import math

    from apps.api.app.core.database import db
    from apps.api.app.domain.mt5_connection import ensure_gateway_session
    from apps.api.app.market.market_data import create_market_data_gateway, market_context
    from apps.api.app.market.normalized_provider import candle_close

    with db() as conn:
        ensure_gateway_session(conn, "tenant-cacsms")
        ctx = market_context(conn)
        gw = create_market_data_gateway(conn, context=ctx)
        adapter = gw.adapter
        sym = "EURNZD"
        tf = "MN"
        import MetaTrader5 as mt5

        const = adapter._tf_const(tf)
        for pos in (0, 1):
            rates = mt5.copy_rates_from_pos(sym, const, pos, 20)
            print(f"copy_rates_from_pos pos={pos} count=20:", None if rates is None else len(rates))
            if rates is not None and len(rates):
                print("  first", rates[0])
                print("  last", rates[-1])
        try:
            raw = adapter.closed_candles(sym, tf, 50)
            print("adapter closed_candles", len(raw))
            for c in raw[:3]:
                print(" ", c)
            for c in raw:
                opened = c.open_time.astimezone(timezone.utc) if c.open_time.tzinfo else c.open_time.replace(tzinfo=timezone.utc)
                closed = candle_close(opened, tf, (gw.get_account_context() or {}).get("broker_utc_offset_seconds", 0))
                bad_price = not all(math.isfinite(v) and v > 0 for v in (c.open, c.high, c.low, c.close))
                bad_ohlc = c.high < max(c.open, c.close, c.low) or c.low > min(c.open, c.close, c.high)
                if bad_price or bad_ohlc:
                    print("BAD", c, "closed", closed, "is_closed", c.is_closed, bad_price, bad_ohlc)
        except Exception as e:
            print("adapter error", e)
        try:
            norm = gw.get_closed_candles(sym, tf, count=50)
            print("normalized", len(norm))
        except Exception as e:
            print("normalized error", type(e).__name__, e)


if __name__ == "__main__":
    main()

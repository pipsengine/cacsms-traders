"""Compare quarterly outlook outputs vs frozen-bar channel intelligence."""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from apps.api.app.core.env_loader import load_env_file

load_env_file()

from apps.api.app.market import channel_intelligence as chan
from apps.api.app.market.outlook.horizons import freeze_at, recent_quarter_closes
from apps.api.app.market.outlook.service import _scope_sql
from apps.api.app.market.provenance import values
from apps.api.app.market.repository import MarketRepository
from apps.api.app.market.scanner_engine import analysis_cores, SCANNER_UNIVERSE
from apps.api.app.core.database import db

SYMBOL = "EURUSD"


def main() -> None:
    with db() as conn:
        repo = MarketRepository(conn)
        now = datetime.now(timezone.utc)
        q_closes = recent_quarter_closes(conn, "EURUSD", now, 4)
        print("Recent quarter MN closes (EURUSD):", [c.isoformat() for c in q_closes])
        row = conn.execute(
            "SELECT id, analysis_date, close_at, state, symbols_published, qualified FROM ai_outlook_run "
            "WHERE horizon='QUARTERLY' AND state='PUBLISHED' ORDER BY published_at DESC LIMIT 1"
        ).fetchone()
        if not row:
            print("No published QUARTERLY run")
            return
        run = dict(zip(["id", "analysis_date", "close_at", "state", "symbols_published", "qualified"], values(row)))
        print("Latest published run:", run)
        cutoff = datetime.fromisoformat(run["close_at"])
        if cutoff.tzinfo is None:
            cutoff = cutoff.replace(tzinfo=timezone.utc)
        sym_row = conn.execute(
            "SELECT symbol, direction, confidence, regime, qualified, payload_json FROM ai_outlook_symbol "
            "WHERE run_id=? AND symbol=? AND status='PUBLISHED'",
            (run["id"], SYMBOL),
        ).fetchone()
        if not sym_row:
            print(f"No published outlook for {SYMBOL}")
            return
        keys = ["symbol", "direction", "confidence", "regime", "qualified", "payload_json"]
        pub = dict(zip(keys, values(sym_row)))
        payload = json.loads(pub["payload_json"])
        print(f"\nPublished {SYMBOL}:", pub["direction"], pub["confidence"], pub["regime"], "qualified=", pub["qualified"])
        print("Payload analysis_date:", payload.get("analysis_date"), "anchor:", payload.get("anchor"))
        print("timeframe_focus:", payload.get("timeframe_focus"))
        mtf = {r["tf"]: (r.get("direction"), r.get("dir")) for r in (payload.get("mtf") or []) if r.get("available")}
        print("MTF Q row:", mtf.get("Q"), "MN:", mtf.get("MN"), "W:", mtf.get("W"))

        _manifest, bars = freeze_at(conn, cutoff, "LIVE", [SYMBOL], "QUARTERLY", run["analysis_date"])
        cores = analysis_cores(bars[SYMBOL], h8bb=False)
        ch = chan.channel_bars(bars[SYMBOL])
        q_bars = ch.get("Q") or []
        mn = bars[SYMBOL].get("MN") or []
        print(f"\nFrozen bars at {cutoff.isoformat()}: MN={len(mn)} W1={len(bars[SYMBOL].get('W1') or [])} Q synth={len(q_bars)}")
        if q_bars:
            print(f"Last Q bar: open={q_bars[-1].t.isoformat()} close={q_bars[-1].c}")
        if mn:
            print(f"Last MN bar: open={mn[-1].t.isoformat()} close={mn[-1].c}")
        facts_q = (cores.get("facts") or {}).get("channels") or {}
        q_fact = facts_q.get("Q") or {}
        print("Engine Q channel available:", q_fact.get("available"), "dir:", (q_fact.get("direction") or {}).get("key"))


def inspect_mn() -> None:
    with db() as conn:
        rows = conn.execute(
            "SELECT open_time, close_time FROM mi_candle WHERE symbol=? AND timeframe='MN' AND is_closed=1 "
            "ORDER BY close_time DESC LIMIT 12",
            (SYMBOL,),
        ).fetchall()
        print("MN bars (open, close):")
        for o, cl in rows:
            print(" ", o, cl)


def list_runs() -> None:
    with db() as conn:
        rows = conn.execute(
            "SELECT analysis_date, close_at, state, symbols_published, qualified FROM ai_outlook_run "
            "WHERE horizon='QUARTERLY' ORDER BY COALESCE(published_at, started_at) DESC"
        ).fetchall()
        for r in rows:
            print(r)


if __name__ == "__main__":
    inspect_mn()
    print()
    list_runs()
    print()
    main()

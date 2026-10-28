import json
import sqlite3
from pathlib import Path

from apps.api.app.execution.money import D
from apps.api.app.execution.service import _apply_min_lot_fallback, _min_lot_max_risk_pct, load_spec
from apps.api.app.execution.sizing import account_tick_value, size_position

ROOT = Path(__file__).resolve().parents[1]
conn = sqlite3.connect(ROOT / "database" / "db_cacsms-traders.db")
conn.row_factory = sqlite3.Row

rows = conn.execute(
    """
    SELECT h.symbol, h.horizon, h.evidence_json, s.payload_json
    FROM ai_outlook_handoff h JOIN ai_outlook_symbol s ON s.id = h.outlook_id
    WHERE h.lifecycle='AUTHORIZATION_PENDING' AND h.evidence_json LIKE '%MINIMUM%'
    """
).fetchall()
print(f"handoffs with MINIMUM: {len(rows)}")
for r in rows:
    ev = json.loads(r["evidence_json"] or "{}")
    pl = json.loads(r["payload_json"] or "{}")
    print("===", r["symbol"], r["horizon"], "err=", ev.get("broker_error"))

acc = conn.execute(
    "SELECT id, tenant_id, equity, account_currency FROM trading_accounts ORDER BY updated_at DESC LIMIT 1"
).fetchone()
print("account", dict(acc) if acc else None)
prof = conn.execute(
    "SELECT * FROM account_risk_profiles WHERE trading_account_id=?", (acc["id"],)
).fetchone() if acc else None
print("profile max_trade", prof["max_trade_risk_pct"] if prof else None)

if not acc:
    raise SystemExit(0)

tenant = acc["tenant_id"]
account_id = acc["id"]
equity = float(acc["equity"] or 0)
currency = (acc["account_currency"] or "USD").upper()
ceiling = _min_lot_max_risk_pct(dict(prof) if prof else None)
print("ceiling_pct", ceiling, "equity", equity, "cap_ngn", equity * ceiling / 100)

for sym in ("EURCAD", "EURNZD", "EURJPY"):
    spec = load_spec(conn, account_id, sym)
    if not spec:
        print(sym, "NO SPEC")
        continue
    pl_row = conn.execute(
        "SELECT payload_json FROM ai_outlook_symbol WHERE symbol=? LIMIT 1", (sym,)
    ).fetchone()
    stop = None
    if pl_row:
        pl = json.loads(pl_row["payload_json"] or "{}")
        inv = pl.get("invalidation") or pl.get("stop")
        entry = pl.get("entry") or pl.get("entry_mid")
        if isinstance(pl.get("erz"), dict):
            erz = pl["erz"]
            entry = entry or erz.get("mid") or ((float(erz.get("lo", 0)) + float(erz.get("hi", 0))) / 2)
        stop = inv or pl.get("invalidation_level")
        print(sym, "entry/stop from payload", entry, stop)
    conversion = None
    profit = spec.get("currency_profit")
    if profit and profit.upper() != currency:
        conversion = conn.execute(
            """SELECT rate, from_currency, to_currency FROM currency_snapshots
               WHERE tenant_id=? AND from_currency=? AND to_currency=? AND reconciliation_status='VALIDATED'
               ORDER BY as_of DESC LIMIT 1""",
            (tenant, profit.upper(), currency),
        ).fetchone()
    tick_value, tick_reason = account_tick_value(
        account_currency=currency,
        tick_value=spec.get("tick_value"),
        tick_value_currency=spec.get("tick_value_currency") or currency,
        profit_tick_value=spec.get("profit_tick_value"),
        profit_currency=profit,
        conversion_rate=None if not conversion else conversion["rate"],
        conversion_from=None if not conversion else conversion["from_currency"],
        conversion_to=None if not conversion else conversion["to_currency"],
    )
    print(sym, "tick", tick_value, tick_reason, "vol_min", spec.get("volume_min"))
    if stop is None:
        continue
    # use a plausible entry near ERZ for bearish weekly
    price = float(entry) if entry else float(stop) + 0.001
    sized = size_position(
        equity=equity,
        risk_pct=prof["max_trade_risk_pct"] if prof and prof["max_trade_risk_pct"] is not None else 1,
        price=price,
        stop=stop,
        tick_size=spec["tick_size"],
        tick_value=tick_value,
        volume_min=spec["volume_min"],
        volume_max=spec["volume_max"],
        volume_step=spec["volume_step"],
    )
    print(sym, "sized", sized.ok, sized.reason, "proj", sized.projected_loss, "vol", sized.volume)
    retry, ok = _apply_min_lot_fallback(sized, equity=equity, volume_min=spec["volume_min"], ceiling_pct=ceiling)
    print(sym, "fallback", ok, retry.ok, retry.reason, "proj", retry.projected_loss, "pct", float(retry.projected_loss) / equity * 100 if retry.projected_loss else None)

"""Send one market order to the attached MetaTrader 5 terminal.

SHADOW and ANALYSIS_ONLY never reach this module. A demo system mode can send only
to a demo terminal, and a live system mode only to a live terminal.
"""
from __future__ import annotations

import math
from typing import Any

from ..market.mt5_gateway import symbol_candidates
from ..market import mt5_session

_DONE = {10008, 10009, 10010}  # placed, done, partial
_MAGIC = 260151


def execution_allowed(system_mode: str | None, terminal_trade_mode: str | None) -> bool:
    mode = (system_mode or "").upper()
    terminal = (terminal_trade_mode or "").upper()
    if mode == "DEMO_AUTONOMOUS":
        return terminal == "DEMO"
    if mode == "LIVE_AUTONOMOUS":
        return terminal == "LIVE"
    return False


def lot_size(info: Any, *, equity: float, risk_pct: float, price: float, stop: float) -> float | None:
    """Largest volume whose stop loss stays inside the per-trade risk budget. None when the minimum lot is too large."""
    distance = abs(price - stop)
    tick_size = float(getattr(info, "trade_tick_size", 0) or getattr(info, "point", 0) or 0)
    tick_value = float(getattr(info, "trade_tick_value", 0) or 0)
    step = float(getattr(info, "volume_step", 0) or 0)
    minimum = float(getattr(info, "volume_min", 0) or 0)
    maximum = float(getattr(info, "volume_max", 0) or 0)
    if distance <= 0 or tick_size <= 0 or tick_value <= 0 or step <= 0 or equity <= 0 or risk_pct <= 0:
        return None
    risk_money = equity * risk_pct / 100.0
    raw = risk_money / ((distance / tick_size) * tick_value)
    steps = math.floor((raw + step * 1e-9) / step)
    volume = round(steps * step, 8)
    if volume < minimum or (maximum and volume > maximum):
        if minimum and volume < minimum:
            return None
        volume = min(volume, maximum) if maximum else volume
    if volume < minimum or volume <= 0:
        return None
    return volume


def _trade_mode_label(mt5, trade_mode: int) -> str:
    if trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO:
        return "DEMO"
    if trade_mode == mt5.ACCOUNT_TRADE_MODE_REAL:
        return "LIVE"
    if trade_mode == mt5.ACCOUNT_TRADE_MODE_CONTEST:
        return "CONTEST"
    return str(trade_mode)


def terminal_trade_mode() -> str | None:
    if not mt5_session.is_initialized() and not mt5_session.initialize():
        return None
    try:
        import MetaTrader5 as mt5  # type: ignore
    except Exception:
        return None
    account = mt5.account_info()
    if account is None:
        return None
    return _trade_mode_label(mt5, int(getattr(account, "trade_mode", -1)))


def _filling(mt5, info) -> int:
    flags = int(getattr(info, "filling_mode", 0) or 0)
    if flags & 1:
        return mt5.ORDER_FILLING_FOK
    if flags & 2:
        return mt5.ORDER_FILLING_IOC
    return mt5.ORDER_FILLING_RETURN


def _round_price(info, price: float) -> float:
    digits = int(getattr(info, "digits", 5) or 5)
    return round(price, digits)


def open_market_position(*, symbol: str, direction: str, stop: float, target: float, risk_pct: float) -> dict[str, Any]:
    """Market deal with the plan's stop and target. Returns ok False when the broker rejects it or the size is unsafe."""
    if not mt5_session.is_initialized() and not mt5_session.initialize():
        return {"ok": False, "error": "MT5 terminal is not attached"}
    try:
        import MetaTrader5 as mt5  # type: ignore
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    account = mt5.account_info()
    if account is None:
        return {"ok": False, "error": "MT5 account_info returned no data"}
    names = {item.name for item in (mt5.symbols_get() or ())}
    broker = next((name for name in symbol_candidates(symbol) if name in names), None)
    if broker is None or not mt5.symbol_select(broker, True):
        return {"ok": False, "error": f"Symbol {symbol} is not on the terminal"}
    info = mt5.symbol_info(broker)
    tick = mt5.symbol_info_tick(broker)
    if info is None or tick is None or not tick.bid or not tick.ask:
        return {"ok": False, "error": f"No quote for {symbol}"}
    side = direction.upper()
    if side == "BULLISH":
        order_type = mt5.ORDER_TYPE_BUY
        price = float(tick.ask)
    elif side == "BEARISH":
        order_type = mt5.ORDER_TYPE_SELL
        price = float(tick.bid)
    else:
        return {"ok": False, "error": "Direction is not bullish or bearish"}
    stop_price = _round_price(info, float(stop))
    target_price = _round_price(info, float(target))
    point = float(info.point or 0)
    min_distance = int(getattr(info, "trade_stops_level", 0) or 0) * point
    if side == "BULLISH" and not (stop_price < price - min_distance and target_price > price + min_distance):
        return {"ok": False, "error": "Stop or target is on the wrong side of the ask"}
    if side == "BEARISH" and not (target_price < price - min_distance and stop_price > price + min_distance):
        return {"ok": False, "error": "Stop or target is on the wrong side of the bid"}
    equity = float(account.equity or 0)
    volume = lot_size(info, equity=equity, risk_pct=risk_pct, price=price, stop=stop_price)
    if volume is None:
        return {"ok": False, "error": "Minimum lot would risk more than the per-trade budget"}
    from ..prop_firm.gate import block_prop_order

    blocked = block_prop_order(
        login=getattr(account, "login", None),
        equity=equity,
        balance=float(getattr(account, "balance", 0) or 0),
        floating_pnl=float(getattr(account, "profit", 0) or 0),
        symbol=symbol,
        volume=volume,
        risk_pct=risk_pct,
        open_positions=int(mt5.positions_total() or 0),
    )
    if blocked:
        return {"ok": False, "error": blocked}
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": broker,
        "volume": volume,
        "type": order_type,
        "price": _round_price(info, price),
        "sl": stop_price,
        "tp": target_price,
        "deviation": 20,
        "magic": _MAGIC,
        "comment": "cacsms",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": _filling(mt5, info),
    }
    result = mt5.order_send(request)
    retcode = None if result is None else int(result.retcode)
    if result is None or retcode not in _DONE:
        if request["type_filling"] != mt5.ORDER_FILLING_RETURN:
            request["type_filling"] = mt5.ORDER_FILLING_RETURN
            result = mt5.order_send(request)
            retcode = None if result is None else int(result.retcode)
    if result is None or retcode not in _DONE:
        comment = "" if result is None else str(result.comment or "")
        return {"ok": False, "error": comment or f"Broker retcode {retcode}", "retcode": retcode, "volume": volume}
    return {
        "ok": True,
        "ticket": str(result.order or result.deal or ""),
        "deal": str(getattr(result, "deal", "") or ""),
        "volume": volume,
        "price": float(result.price or price),
        "symbol": broker,
        "retcode": retcode,
    }


def close_position(ticket: int) -> dict[str, Any]:
    """Close one open ticket. Used to remove an order the outlook does not authorise."""
    if not mt5_session.is_initialized() and not mt5_session.initialize():
        return {"ok": False, "error": "MT5 terminal is not attached"}
    try:
        import MetaTrader5 as mt5  # type: ignore
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    rows = mt5.positions_get(ticket=int(ticket))
    if not rows:
        return {"ok": False, "error": f"Ticket {ticket} is not open"}
    pos = rows[0]
    info = mt5.symbol_info(pos.symbol)
    tick = mt5.symbol_info_tick(pos.symbol)
    if info is None or tick is None:
        return {"ok": False, "error": f"No quote for {pos.symbol}"}
    if int(pos.type) == int(mt5.POSITION_TYPE_BUY):
        order_type = mt5.ORDER_TYPE_SELL
        price = float(tick.bid)
        direction = "BULLISH"
    else:
        order_type = mt5.ORDER_TYPE_BUY
        price = float(tick.ask)
        direction = "BEARISH"
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": pos.symbol,
        "volume": float(pos.volume),
        "type": order_type,
        "position": int(pos.ticket),
        "price": _round_price(info, price),
        "deviation": 20,
        "magic": _MAGIC,
        "comment": "cacsms-close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": _filling(mt5, info),
    }
    result = mt5.order_send(request)
    retcode = None if result is None else int(result.retcode)
    if result is None or retcode not in _DONE:
        comment = "" if result is None else str(result.comment or "")
        return {"ok": False, "error": comment or f"Broker retcode {retcode}", "retcode": retcode, "symbol": pos.symbol, "direction": direction}
    return {"ok": True, "ticket": str(pos.ticket), "symbol": pos.symbol, "direction": direction, "volume": float(pos.volume)}

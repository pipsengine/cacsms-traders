"""Send one market order to the attached MetaTrader 5 terminal.

SHADOW and ANALYSIS_ONLY never reach this module. A demo system mode can send only
to a demo terminal, and a live system mode only to a live terminal.
"""
from __future__ import annotations

from typing import Any

from ..execution.pipeline import UNCERTAIN_RETCODES
from ..execution.symbols import resolve_broker_symbol
from ..market import mt5_session

_DONE = {10008, 10009, 10010}  # placed, done, partial
_INVALID_FILL = 10031
_MAGIC = 260151


def execution_allowed(system_mode: str | None, terminal_trade_mode: str | None) -> bool:
    mode = (system_mode or "").upper()
    terminal = (terminal_trade_mode or "").upper()
    if mode == "DEMO_AUTONOMOUS":
        return terminal == "DEMO"
    if mode == "LIVE_AUTONOMOUS":
        return terminal == "LIVE"
    return False


def lot_size(info: Any, *, equity: float, risk_pct: float, price: float, stop: float,
             commission_per_lot: float = 0, spread_cost_per_lot: float = 0) -> float | None:
    """Largest volume whose stop loss stays inside the per-trade risk budget. None when the minimum lot is too large."""
    from ..execution.sizing import size_position

    sized = size_position(
        equity=equity, risk_pct=risk_pct, price=price, stop=stop,
        tick_size=getattr(info, "trade_tick_size", 0) or getattr(info, "point", 0) or 0,
        tick_value=getattr(info, "trade_tick_value", 0) or 0,
        volume_min=getattr(info, "volume_min", 0) or 0,
        volume_max=getattr(info, "volume_max", 0) or 0,
        volume_step=getattr(info, "volume_step", 0) or 0,
        commission_per_lot=commission_per_lot,
        spread_cost_per_lot=spread_cost_per_lot,
    )
    return None if not sized.ok or sized.volume is None else float(sized.volume)


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


def _broker_name(mt5, symbol: str, mapped: str | None = None) -> str | None:
    names = [item.name for item in (mt5.symbols_get() or ())]
    return resolve_broker_symbol(symbol, names, mapped)


def terminal_order_context(symbol: str, direction: str) -> dict[str, Any]:
    """Broker price and contract figures for one symbol. Tick value stays in the account currency."""
    if not mt5_session.is_initialized() and not mt5_session.initialize():
        return {"ok": False, "error": "MT5 terminal is not attached"}
    try:
        import MetaTrader5 as mt5  # type: ignore
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    account = mt5.account_info()
    broker = _broker_name(mt5, symbol)
    if account is None or broker is None or not mt5.symbol_select(broker, True):
        return {"ok": False, "error": f"Symbol {symbol} is not uniquely available on this account"}
    info = mt5.symbol_info(broker)
    tick = mt5.symbol_info_tick(broker)
    if info is None or tick is None or not tick.bid or not tick.ask:
        return {"ok": False, "error": f"No quote for {symbol}"}
    side = direction.upper()
    price = float(tick.ask if side == "BULLISH" else tick.bid if side == "BEARISH" else 0)
    if not price:
        return {"ok": False, "error": "Direction is not bullish or bearish"}
    point = float(info.point or 0)
    tick_size = float(getattr(info, "trade_tick_size", 0) or point or 0)
    spread_points = float(getattr(info, "spread", 0) or 0)
    return {
        "ok": True,
        "broker_symbol": broker,
        "price": price,
        "currency": str(account.currency or ""),
        "equity": float(account.equity or 0),
        "free_margin": float(getattr(account, "margin_free", 0) or 0),
        "balance": float(account.balance or 0),
        "floating_pnl": float(getattr(account, "profit", 0) or 0),
        "open_positions": int(mt5.positions_total() or 0),
        "spec": {
            "symbol": symbol,
            "broker_symbol": broker,
            "currency_profit": str(getattr(info, "currency_profit", "") or ""),
            "currency_margin": str(getattr(info, "currency_margin", "") or ""),
            "digits": int(getattr(info, "digits", 5) or 5),
            "point": point,
            "tick_size": tick_size,
            "tick_value": float(getattr(info, "trade_tick_value", 0) or 0),
            "tick_value_currency": str(account.currency or ""),
            "profit_tick_value": float(getattr(info, "trade_tick_value_profit", 0) or 0),
            "volume_min": float(getattr(info, "volume_min", 0) or 0),
            "volume_max": float(getattr(info, "volume_max", 0) or 0),
            "volume_step": float(getattr(info, "volume_step", 0) or 0),
            "stops_level_points": int(getattr(info, "trade_stops_level", 0) or 0),
            "spread_points": spread_points,
            "margin_per_lot": float(getattr(info, "margin_initial", 0) or 0) or None,
            "commission_per_lot": 0,
        },
    }


def side_price(symbol: str, direction: str) -> float | None:
    """Ask for a buy, bid for a sell. None when the terminal has no quote."""
    if not mt5_session.is_initialized() and not mt5_session.initialize():
        return None
    try:
        import MetaTrader5 as mt5  # type: ignore
    except Exception:
        return None
    broker = _broker_name(mt5, symbol)
    if broker is None:
        return None
    tick = mt5.symbol_info_tick(broker)
    if tick is None:
        return None
    side = direction.upper()
    raw = tick.ask if side == "BULLISH" else tick.bid if side == "BEARISH" else 0
    price = float(raw or 0)
    return price or None


def _uncertain(result, retcode) -> bool:
    return result is None or retcode in UNCERTAIN_RETCODES


def open_market_position(*, symbol: str, direction: str, stop: float, target: float, risk_pct: float,
                         volume: float | None = None, broker_symbol: str | None = None) -> dict[str, Any]:
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
    broker = _broker_name(mt5, symbol, broker_symbol)
    if broker is None or not mt5.symbol_select(broker, True):
        return {"ok": False, "error": f"Symbol {symbol} is not uniquely available on this account"}
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
    if volume is None:
        point = float(info.point or 0)
        tick_size = float(getattr(info, "trade_tick_size", 0) or point or 0)
        spread_cost = 0.0
        tick_value = float(getattr(info, "trade_tick_value", 0) or 0)
        if tick_size and tick_value:
            spread_cost = (float(getattr(info, "spread", 0) or 0) * point / tick_size) * tick_value
        volume = lot_size(info, equity=equity, risk_pct=risk_pct, price=price, stop=stop_price, spread_cost_per_lot=spread_cost)
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
    if _uncertain(result, retcode):
        return {"ok": False, "uncertain": True, "error": "Broker result is uncertain", "retcode": retcode, "volume": volume}
    if retcode == _INVALID_FILL and request["type_filling"] != mt5.ORDER_FILLING_RETURN:
        request["type_filling"] = mt5.ORDER_FILLING_RETURN
        result = mt5.order_send(request)
        retcode = None if result is None else int(result.retcode)
        if _uncertain(result, retcode):
            return {"ok": False, "uncertain": True, "error": "Broker result is uncertain", "retcode": retcode, "volume": volume}
    if result is None or retcode not in _DONE:
        comment = "" if result is None else str(result.comment or "")
        return {"ok": False, "uncertain": False, "error": comment or f"Broker retcode {retcode}", "retcode": retcode, "volume": volume}
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

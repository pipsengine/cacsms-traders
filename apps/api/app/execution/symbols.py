"""Resolve the symbol name this account actually trades.

Brokers differ. One lists EURUSD, another lists EURUSDb, and some list both.
The name that can open a position wins. A plain name is kept when that is the
tradable contract. A suffix is used only when the plain name cannot be traded,
or when it is the only quoted name. A stored suffix never replaces a tradable
plain name. Two equally tradable decorations stay unresolved.
"""
from __future__ import annotations

_CURRENCIES = {"USD", "EUR", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF", "XAU", "XAG"}


def canonical_symbol(symbol: str) -> str:
    return "".join(ch for ch in (symbol or "").upper().replace("/", "") if ch.isalnum())


def _head(name: str) -> str:
    return "".join(ch for ch in name.upper().split(".")[0] if ch.isalnum())


def _is_suffix(rest: str) -> bool:
    """Broker mark after the pair, such as b, m, .a, or pro. Not another currency."""
    if not rest or len(rest) > 4 or rest in _CURRENCIES:
        return False
    if rest[0] in ".#_":
        return True
    if rest.isalpha() and len(rest) <= 3:
        return True
    return rest.isalnum() and len(rest) <= 2


def symbol_aliases(symbol: str, available) -> list[str]:
    """Plain name first, then the same pair with a broker suffix. EURUSDCAD is not an alias of EURUSD."""
    canon = canonical_symbol(symbol)
    if not canon:
        return []
    exact, suffix = [], []
    for raw in available:
        if not raw:
            continue
        name = str(raw)
        upper = name.upper()
        if _head(name) == canon or upper == canon:
            exact.append(name)
            continue
        if upper.startswith(canon) and _is_suffix(upper[len(canon):]):
            suffix.append(name)
    suffix.sort(key=len)
    return exact + suffix


def trade_mode_allows_entry(mode) -> bool:
    """True when a symbol can open a position. Disabled and close-only cannot."""
    if mode is None:
        return True
    try:
        number = int(mode)
    except (TypeError, ValueError):
        return True
    return number in (1, 2, 4)


def choose_account_symbol(symbol: str, available, select, tick, tradable=None, mapped: str | None = None) -> str | None:
    """Enable each alias and keep the one this terminal can trade.

    ``select(name)`` turns the symbol on in Market Watch. ``tick(name)`` returns
    an object or pair with bid and ask. ``tradable(name)`` is true when that
    name can open a position. A single quoted name is used whether it is plain
    or suffixed. When both are quoted, the one that can open wins. When several
    can open, the plain name wins. ``mapped`` breaks a tie only between two
    suffixes, and it does not override a tradable plain name.
    """
    canon = canonical_symbol(symbol)
    aliases = symbol_aliases(symbol, available)
    if not aliases:
        return None
    live: list[str] = []
    for name in aliases:
        try:
            selected = bool(select(name))
        except Exception:
            selected = False
        if not selected:
            continue
        try:
            quote = tick(name)
        except Exception:
            quote = None
        bid = ask = 0
        if isinstance(quote, tuple):
            bid = quote[0] if quote else 0
            ask = quote[1] if quote and len(quote) > 1 else 0
        elif quote is not None:
            bid = getattr(quote, "bid", 0) or 0
            ask = getattr(quote, "ask", 0) or 0
        if bid or ask:
            live.append(name)
    if tradable is not None and len(live) > 1:
        dealing = []
        for name in live:
            try:
                allowed = bool(tradable(name))
            except Exception:
                allowed = False
            if allowed:
                dealing.append(name)
        if len(dealing) == 1:
            return dealing[0]
        if dealing:
            live = dealing
    if len(live) == 1:
        return live[0]
    if len(live) > 1:
        exact = [name for name in live if _head(name) == canon or name.upper() == canon]
        if len(exact) == 1:
            return exact[0]
        if mapped:
            wanted = mapped.strip().upper()
            for name in live:
                if name.upper() == wanted:
                    return name
        return None
    return aliases[0] if len(aliases) == 1 else None


def resolve_broker_symbol(symbol: str, available, mapped: str | None = None) -> str | None:
    canon = canonical_symbol(symbol)
    if not canon:
        return None
    names = [str(name) for name in available if name]
    if mapped:
        wanted = mapped.strip()
        for name in names:
            if name == wanted or name.upper() == wanted.upper():
                return name
        return None
    keyed = [name for name in names if _head(name) == canon]
    loose = [name for name in names if name.upper().startswith(canon) and _head(name) != canon]
    if len(keyed) == 1:
        return keyed[0]
    if len(keyed) > 1:
        return None
    if len(loose) == 1:
        return loose[0]
    return None

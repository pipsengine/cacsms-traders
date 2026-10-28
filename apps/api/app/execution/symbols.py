"""Resolve the symbol name this account actually trades.

A stored broker symbol wins. Otherwise the live name is the one with a price,
whether the broker prints EURUSD or EURUSDb. Two quoted decorations of the
same pair stay unresolved instead of guessing.
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


def choose_account_symbol(symbol: str, available, select, tick) -> str | None:
    """Enable each alias and keep the one the terminal is quoting.

    ``select(name)`` turns the symbol on in Market Watch. ``tick(name)`` returns
    an object or pair with bid and ask. A suffix is used when it is the name
    that has a price. A plain name is used when that is the one with a price.
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
    if len(live) == 1:
        return live[0]
    if len(live) > 1:
        exact = [name for name in live if _head(name) == canon]
        return exact[0] if len(exact) == 1 else None
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

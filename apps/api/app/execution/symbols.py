"""Resolve the symbol name this account actually trades.

A stored broker symbol wins. Otherwise the match has to be unique on the
terminal. A fixed suffix list is not applied, so two decorations of the same
pair are left unresolved instead of picking one.
"""
from __future__ import annotations


def canonical_symbol(symbol: str) -> str:
    return "".join(ch for ch in (symbol or "").upper().replace("/", "") if ch.isalnum())


def _head(name: str) -> str:
    return "".join(ch for ch in name.upper().split(".")[0] if ch.isalnum())


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
    if keyed and loose:
        return None
    candidates = keyed or loose
    if len(candidates) == 1:
        return candidates[0]
    return None

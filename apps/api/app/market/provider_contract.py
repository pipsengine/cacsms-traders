"""Provider-neutral contract for market-data ingestion and intelligence."""
from __future__ import annotations

from datetime import datetime
from typing import Protocol

from .models import Candle


class MarketDataUnavailable(RuntimeError):
    """The selected market-data provider cannot serve a fresh request."""


class MarketDataProvider(Protocol):
    provider_id: str

    def get_symbols(self) -> list[dict]: ...

    def get_symbol(self, symbol: str) -> dict | None: ...

    def get_latest_price(self, symbol: str) -> dict: ...

    def get_candles(
        self,
        symbol: str,
        timeframe: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        count: int = 400,
    ) -> list[Candle]: ...

    def get_closed_candles(
        self,
        symbol: str,
        timeframe: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        count: int = 400,
    ) -> list[Candle]: ...

    def get_provider_health(self) -> dict: ...

    def get_account_context(self) -> dict | None: ...
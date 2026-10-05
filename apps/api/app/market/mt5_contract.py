"""Backward-compatible imports for the former MT5-only market-data contract."""
from .provider_contract import MarketDataProvider as MarketDataGateway
from .provider_contract import MarketDataUnavailable

__all__ = ["MarketDataGateway", "MarketDataUnavailable"]

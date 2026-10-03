from abc import ABC, abstractmethod

from .mt5_connection import LocalMT5Gateway as Mt5GatewayCore


class TradingGateway(ABC):
    @abstractmethod
    def health(self): ...

    @abstractmethod
    def account_snapshot(self, account): ...


class LocalMT5Gateway(Mt5GatewayCore):
    def account_snapshot(self, account):
        h = self.health()
        if h.get("status") != "CONNECTED":
            return {"status": "NOT_CONNECTED", "account_id": account.get("id")}
        return {"status": "CONNECTED", "account_id": account.get("id"), "adapter": h.get("adapter")}

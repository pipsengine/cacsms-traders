"""One-shot, read-only cTrader Open API discovery process."""
from __future__ import annotations

import json
import sys


def main() -> int:
    request_data = json.load(sys.stdin)
    if request_data.get("environment") != "demo":
        print("CTRADER_RESULT:{\"error\":\"demo_only\"}", flush=True)
        return 1

    try:
        from ctrader_open_api import Client, EndPoints, TcpProtocol
        from ctrader_open_api.messages.OpenApiMessages_pb2 import (
            ProtoOAAccountAuthReq,
            ProtoOAApplicationAuthReq,
            ProtoOAAssetListReq,
            ProtoOAGetAccountListByAccessTokenReq,
            ProtoOATraderReq,
        )
        from twisted.internet import reactor
    except Exception:
        print("CTRADER_RESULT:{\"error\":\"sdk_unavailable\"}", flush=True)
        return 1

    client_id = __import__("os").getenv("CTRADER_CLIENT_ID", "").strip()
    client_secret = __import__("os").getenv("CTRADER_CLIENT_SECRET", "").strip()
    access_token = request_data.get("access_token", "")
    if not (client_id and client_secret and access_token):
        print("CTRADER_RESULT:{\"error\":\"not_configured\"}", flush=True)
        return 1

    result: dict = {"accounts": [], "error": None}
    account_metadata: dict[str, dict] = {}
    reactor_instance = reactor
    client = Client(EndPoints.PROTOBUF_DEMO_HOST, EndPoints.PROTOBUF_PORT, TcpProtocol)
    timeout_call = None
    finished = False

    def finish(error: str | None = None) -> None:
        nonlocal finished
        if finished:
            return
        finished = True
        result["error"] = error
        if timeout_call is not None and timeout_call.active():
            timeout_call.cancel()
        client.stopService()
        reactor_instance.callLater(0, reactor_instance.stop)

    def failed(_failure) -> None:
        finish("provider_unavailable")

    def account_details_done(account_id: str) -> None:
        item = account_metadata[account_id]
        if item.get("trader") is None or item.get("assets") is None:
            return
        trader = item["trader"]
        account = item["account"]
        deposit_asset_id = trader.depositAssetId
        asset = next((asset for asset in item["assets"] if asset.assetId == deposit_asset_id), None)
        if asset is None:
            finish("account_metadata_unavailable")
            return
        account_type = (
            {0: "HEDGED", 1: "NETTED", 2: "SPREAD_BETTING"}.get(trader.accountType, "UNKNOWN")
            if trader.HasField("accountType")
            else "UNKNOWN"
        )
        broker = trader.brokerName or account.brokerTitleShort or None
        result["accounts"].append(
            {
                "ctid_trader_account_id": account_id,
                "trader_login": str(account.traderLogin) if account.traderLogin else None,
                "broker_name": broker,
                "account_type": account_type,
                "currency_code": asset.name,
                "environment": "demo",
            }
        )
        item["complete"] = True
        if all(metadata.get("complete") for metadata in account_metadata.values()):
            finish()

    def on_account_authorized(account_id: str, _response) -> None:
        trader_req = ProtoOATraderReq()
        trader_req.ctidTraderAccountId = int(account_id)
        client.send(trader_req).addCallbacks(
            lambda trader, aid=account_id: on_trader(aid, trader), failed
        )

        assets_req = ProtoOAAssetListReq()
        assets_req.ctidTraderAccountId = int(account_id)
        client.send(assets_req).addCallbacks(
            lambda assets, aid=account_id: on_assets(aid, assets), failed
        )

    def on_trader(account_id: str, trader) -> None:
        account_metadata[account_id]["trader"] = trader
        account_details_done(account_id)

    def on_assets(account_id: str, response) -> None:
        account_metadata[account_id]["assets"] = list(response.asset)
        account_details_done(account_id)

    def on_account_list(response) -> None:
        demo_accounts = [account for account in response.ctidTraderAccount if not account.isLive]
        if not demo_accounts:
            finish("no_demo_accounts")
            return
        for account in demo_accounts:
            account_id = str(account.ctidTraderAccountId)
            account_metadata[account_id] = {"account": account, "trader": None, "assets": None}
            auth_req = ProtoOAAccountAuthReq()
            auth_req.ctidTraderAccountId = account.ctidTraderAccountId
            auth_req.accessToken = access_token
            client.send(auth_req).addCallbacks(
                lambda auth, aid=account_id: on_account_authorized(aid, auth), failed
            )

    def on_app_authorized(_response) -> None:
        accounts_req = ProtoOAGetAccountListByAccessTokenReq()
        accounts_req.accessToken = access_token
        client.send(accounts_req).addCallbacks(on_account_list, failed)

    def on_connected(connected_client) -> None:
        app_auth = ProtoOAApplicationAuthReq()
        app_auth.clientId = client_id
        app_auth.clientSecret = client_secret
        connected_client.send(app_auth).addCallbacks(on_app_authorized, failed)

    client.setConnectedCallback(on_connected)
    timeout_call = reactor_instance.callLater(18, finish, "provider_timeout")
    client.startService()
    reactor_instance.run()
    print("CTRADER_RESULT:" + json.dumps(result, separators=(",", ":")), flush=True)
    return 0 if result["error"] is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
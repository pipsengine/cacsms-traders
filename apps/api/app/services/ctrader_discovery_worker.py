"""One-shot, read-only cTrader Open API discovery process."""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone

_PRICE_SCALE = 100_000
_TIMEFRAME_SECONDS = {
    "M1": 60,
    "M5": 300,
    "M15": 900,
    "M30": 1_800,
    "H1": 3_600,
    "H4": 14_400,
    "D1": 86_400,
    "W": 604_800,
    "W1": 604_800,
    "MN": 2_592_000,
    "MN1": 2_592_000,
}
_PERIODS = {"M1": 1, "M5": 5, "M15": 7, "M30": 8, "H1": 9, "H4": 10, "D1": 12, "W": 13, "W1": 13, "MN": 14, "MN1": 14}


def decode_response(message, extract):
    """SDK send() returns a ProtoMessage envelope, including error responses."""
    response = extract(message)
    if getattr(response, 'errorCode', None):
        # This file also runs as a standalone subprocess.
        if __package__:
            from .ctrader_application_state import provider_error_code
        else:
            from ctrader_application_state import provider_error_code
        raise RuntimeError(provider_error_code(response.errorCode, getattr(response, 'description', '')))
    return response


def main() -> int:
    request_data = json.load(sys.stdin)
    environment = request_data.get("environment") or "demo"
    if environment not in ("demo", "live"):
        print("CTRADER_RESULT:{\"error\":\"demo_only\"}", flush=True)
        return 1
    action = request_data.get("action", "discover")
    if action not in ("discover", "authenticate", "symbols", "history", "quote", "verify_application"):
        print("CTRADER_RESULT:{\"error\":\"unsupported_action\"}", flush=True)
        return 1

    try:
        from ctrader_open_api import Client, EndPoints, TcpProtocol, Protobuf
        from ctrader_open_api.messages.OpenApiMessages_pb2 import (
            ProtoOAAccountAuthReq,
            ProtoOAApplicationAuthReq,
            ProtoOAAssetListReq,
            ProtoOAErrorRes,
            ProtoOAGetAccountListByAccessTokenReq,
            ProtoOAGetAccountListByAccessTokenRes,
            ProtoOAGetTrendbarsReq,
            ProtoOASymbolsListReq,
            ProtoOASymbolByIdReq,
            ProtoOASubscribeSpotsReq,
            ProtoOASpotEvent,
            ProtoOATraderReq,
        )
        from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOATrendbarPeriod
        from twisted.internet import reactor
    except Exception:
        print("CTRADER_RESULT:{\"error\":\"sdk_unavailable\"}", flush=True)
        return 1

    client_id = __import__("os").getenv("CTRADER_CLIENT_ID", "").strip()
    client_secret = __import__("os").getenv("CTRADER_CLIENT_SECRET", "").strip()
    access_token = request_data.get("access_token", "")
    if not (client_id and client_secret) or (action != "verify_application" and not access_token):
        print("CTRADER_RESULT:{\"error\":\"not_configured\"}", flush=True)
        return 1

    reactor_instance = reactor
    host = EndPoints.PROTOBUF_LIVE_HOST if environment == "live" else EndPoints.PROTOBUF_DEMO_HOST
    result: dict = {
        "accounts": [], "symbols": [], "candles": [], "missing_symbols": [], "error": None,
        "stage": "transport", "market_data": "unverified", "host": host,
    }
    account_metadata: dict[str, dict] = {}
    pending_candles = 0
    client = Client(host, EndPoints.PROTOBUF_PORT, TcpProtocol)
    timeout_call = None
    finished = False
    connected_flag = {"ok": False}
    list_seen = {"done": False}

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

    def failed(failure) -> None:
        message = str(getattr(failure, 'value', failure))
        if result["accounts"]:
            result["stage"] = "account_auth"
            finish(None)
            return
        if __package__:
            from .ctrader_application_state import APP_INACTIVE, provider_error_code
        else:
            from ctrader_application_state import APP_INACTIVE, provider_error_code
        if provider_error_code(message) == APP_INACTIVE or APP_INACTIVE in message:
            finish(APP_INACTIVE)
            return
        lowered = message.lower()
        if "timeout" in lowered or "cancelled" in lowered:
            finish("provider_timeout" if connected_flag["ok"] else "transport_timeout")
            return
        finish("provider_unavailable")

    def send(message):
        return client.send(message).addCallback(lambda reply: decode_response(reply, Protobuf.extract))

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
                "environment": "live" if getattr(account, "isLive", False) else "demo",
            }
        )
        item["complete"] = True
        if all(metadata.get("complete") for metadata in account_metadata.values()):
            finish()

    def on_account_authorized(account_id: str, _response) -> None:
        if action in ("symbols", "quote"):
            symbols_req = ProtoOASymbolsListReq()
            symbols_req.ctidTraderAccountId = int(account_id)
            send(symbols_req).addCallbacks(lambda response: on_symbols(account_id, response), failed)
            return
        if action == "history":
            symbols_req = ProtoOASymbolsListReq()
            symbols_req.ctidTraderAccountId = int(account_id)
            send(symbols_req).addCallbacks(lambda response: on_history_symbols(account_id, response), failed)
            return
        trader_req = ProtoOATraderReq()
        trader_req.ctidTraderAccountId = int(account_id)
        send(trader_req).addCallbacks(
            lambda trader, aid=account_id: on_trader(aid, trader), failed
        )

        assets_req = ProtoOAAssetListReq()
        assets_req.ctidTraderAccountId = int(account_id)
        send(assets_req).addCallbacks(
            lambda assets, aid=account_id: on_assets(aid, assets), failed
        )

    def on_trader(account_id: str, trader) -> None:
        account_metadata[account_id]["trader"] = trader
        account_details_done(account_id)

    def on_assets(account_id: str, response) -> None:
        account_metadata[account_id]["assets"] = list(response.asset)
        account_details_done(account_id)

    expected_symbols = {str(symbol).upper() for symbol in request_data.get("symbols", [])}

    def canonical_symbol(provider_name: str) -> str | None:
        normalized = re.sub(r"[^A-Z0-9]", "", provider_name.upper())
        exact = [symbol for symbol in expected_symbols if normalized == symbol]
        if exact:
            return exact[0]
        candidates = [symbol for symbol in expected_symbols if symbol in normalized]
        return candidates[0] if len(candidates) == 1 else None

    def on_symbols(account_id, response) -> None:
        result["symbols"] = [
            {
                "provider_symbol": item.symbolName,
                "symbol_id": str(item.symbolId),
                "canonical_symbol": canonical_symbol(item.symbolName),
                "environment": "demo",
            }
            for item in response.symbol
            if canonical_symbol(item.symbolName)
        ]
        if not result['symbols']:
            finish('symbols_unavailable')
            return
        details = ProtoOASymbolByIdReq()
        details.ctidTraderAccountId = int(account_id)
        details.symbolId.extend(int(s['symbol_id']) for s in result['symbols'])
        send(details).addCallbacks(lambda response: on_symbol_details(account_id, response), failed)

    def on_symbol_details(account_id, response):
        for item in response.symbol:
            symbol = next((s for s in result['symbols'] if s['symbol_id'] == str(item.symbolId)), None)
            if symbol:
                symbol.update(digits=item.digits, tick_size=10 ** -item.digits,
                              pip_size=10 ** -item.pipPosition, provider='ctrader', spread=None)
        if action == 'symbols':
            finish()
            return
        if not all('digits' in symbol for symbol in result['symbols']):
            finish('symbol_metadata_unavailable')
            return
        spots = ProtoOASubscribeSpotsReq()
        spots.ctidTraderAccountId = int(account_id)
        spots.symbolId.append(int(result['symbols'][0]['symbol_id']))
        spots.subscribeToSpotTimestamp = True
        send(spots).addErrback(failed)

    spot_prices = {}

    def on_message(_client, message):
        if message.payloadType == ProtoOAErrorRes().payloadType and not list_seen["done"]:
            error = Protobuf.extract(message)
            failed(type("Failure", (), {"value": RuntimeError(f"{error.errorCode} {getattr(error, 'description', '')}")})())
            return
        if message.payloadType == ProtoOAGetAccountListByAccessTokenRes().payloadType:
            on_account_list(Protobuf.extract(message))
            return
        if action != 'quote' or message.payloadType != ProtoOASpotEvent().payloadType:
            return
        event = Protobuf.extract(message)
        symbol = next((s for s in result['symbols'] if s['symbol_id'] == str(event.symbolId)), None)
        if not symbol:
            return
        for field in ('bid', 'ask'):
            if event.HasField(field):
                spot_prices[field] = round(getattr(event, field) / _PRICE_SCALE, symbol['digits'])
        if 'bid' in spot_prices and 'ask' in spot_prices:
            timestamp = datetime.fromtimestamp(event.timestamp / 1000, timezone.utc) if event.HasField('timestamp') else datetime.now(timezone.utc)
            result['quote'] = dict(symbol=symbol['canonical_symbol'], provider='ctrader',
                                  bid=spot_prices['bid'], ask=spot_prices['ask'],
                                  spread=spot_prices['ask'] - spot_prices['bid'],
                                  point=symbol['tick_size'], tick_size=symbol['tick_size'], pip_size=symbol['pip_size'], digits=symbol['digits'],
                                  spread_points=(spot_prices['ask']-spot_prices['bid'])/symbol['tick_size'],
                                  timestamp=timestamp.isoformat())
            finish()

    def on_history_symbols(account_id: str, response) -> None:
        nonlocal pending_candles
        symbols_by_canonical = {
            canonical_symbol(item.symbolName): item.symbolId
            for item in response.symbol
            if canonical_symbol(item.symbolName)
        }
        requests = request_data.get("requests", [])
        available = []
        for item in requests:
            canonical = str(item.get("symbol", "")).upper()
            provider_id = symbols_by_canonical.get(canonical)
            if provider_id is None:
                result["missing_symbols"].append(canonical)
                continue
            available.append((canonical, provider_id, str(item.get("timeframe", "")).upper(), item))
        if not available:
            finish("symbols_unavailable")
            return
        pending_candles = len(available)
        for canonical, provider_id, timeframe, request in available:
            period = _PERIODS.get(timeframe)
            if period is None:
                pending_candles -= 1
                result["missing_symbols"].append(f"{canonical}:{timeframe}")
                continue
            trendbars_req = ProtoOAGetTrendbarsReq()
            trendbars_req.ctidTraderAccountId = int(account_id)
            trendbars_req.symbolId = int(provider_id)
            trendbars_req.period = period
            trendbars_req.count = max(1, min(int(request.get("count", 400)), 2000))
            trendbars_req.toTimestamp = int(request.get("end") or time.time() * 1000)
            if request.get("start"):
                trendbars_req.fromTimestamp = int(request["start"])
            send(trendbars_req).addCallbacks(
                lambda reply, symbol=canonical, tf=timeframe: on_trendbars(symbol, tf, reply), failed
            )
        if pending_candles == 0:
            finish("unsupported_timeframes")

    def on_trendbars(symbol: str, timeframe: str, response) -> None:
        nonlocal pending_candles
        duration = _TIMEFRAME_SECONDS[timeframe]
        now_epoch = int(datetime.now(timezone.utc).timestamp())
        for bar in response.trendbar:
            open_epoch = int(bar.utcTimestampInMinutes) * 60
            if timeframe in ("MN", "MN1"):
                opened = datetime.fromtimestamp(open_epoch, timezone.utc)
                close_epoch = int(datetime(
                    opened.year + (opened.month == 12),
                    1 if opened.month == 12 else opened.month + 1,
                    1, tzinfo=timezone.utc,
                ).timestamp())
            else:
                close_epoch = open_epoch + duration
            if close_epoch > now_epoch:
                continue
            low = float(bar.low) / _PRICE_SCALE
            result["candles"].append(
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "open_time": open_epoch,
                    "close_time": close_epoch,
                    "open": (float(bar.low) + float(bar.deltaOpen)) / _PRICE_SCALE,
                    "high": (float(bar.low) + float(bar.deltaHigh)) / _PRICE_SCALE,
                    "low": low,
                    "close": (float(bar.low) + float(bar.deltaClose)) / _PRICE_SCALE,
                    "tick_volume": int(bar.volume),
                    "spread": None,
                    "source": "CTRADER",
                    "is_closed": True,
                }
            )
        pending_candles -= 1
        if pending_candles == 0:
            finish()

    def remember_account(account) -> dict:
        environment_name = "live" if getattr(account, "isLive", False) else "demo"
        login = str(account.traderLogin) if account.HasField("traderLogin") and account.traderLogin else None
        record = {
            "ctid_trader_account_id": str(account.ctidTraderAccountId),
            "trader_login": login,
            "broker_name": None,
            "account_type": None,
            "currency_code": None,
            "environment": environment_name,
            "authenticated": False,
        }
        result["accounts"].append(record)
        return record

    def mark_authenticated(account_id: str, ok: bool, auth_error: str | None = None) -> None:
        for item in result["accounts"]:
            if item["ctid_trader_account_id"] == account_id:
                item["authenticated"] = ok
                if auth_error:
                    item["auth_error"] = auth_error

    def auth_failure_code(failure) -> str:
        message = str(getattr(failure, "value", failure))
        if __package__:
            from .ctrader_application_state import provider_error_code
        else:
            from ctrader_application_state import provider_error_code
        lowered = message.lower()
        if "timeout" in lowered or "cancelled" in lowered:
            return "account_auth_timeout"
        return provider_error_code(message)[:80]

    def verify_market_data(account_id: str) -> None:
        symbols_req = ProtoOASymbolsListReq()
        symbols_req.ctidTraderAccountId = int(account_id)
        def accepted(response) -> None:
            result["market_data"] = "ok" if list(response.symbol) else "empty"
            result["stage"] = "market_data"
            finish(None)
        def rejected(failure) -> None:
            result["market_data"] = "unavailable"
            result["stage"] = "market_data"
            finish(None)
        send(symbols_req).addCallbacks(accepted, rejected)

    def authorize_next(pending: list) -> None:
        if not pending:
            authenticated = next((item for item in result["accounts"] if item.get("authenticated")), None)
            if authenticated and action == "discover":
                verify_market_data(authenticated["ctid_trader_account_id"])
                return
            result["stage"] = "account_auth"
            finish(None)
            return
        account = pending.pop(0)
        account_id = str(account.ctidTraderAccountId)
        auth_req = ProtoOAAccountAuthReq()
        auth_req.ctidTraderAccountId = account.ctidTraderAccountId
        auth_req.accessToken = access_token
        def accepted(_auth, aid=account_id) -> None:
            mark_authenticated(aid, True)
            authorize_next(pending)
        def rejected(failure, aid=account_id) -> None:
            mark_authenticated(aid, False, auth_failure_code(failure))
            authorize_next(pending)
        send(auth_req).addCallbacks(accepted, rejected)

    def on_account_list(response) -> None:
        if list_seen["done"]:
            return
        list_seen["done"] = True
        result["stage"] = "account_list"
        listed = list(response.ctidTraderAccount)
        requested_account_id = str(request_data.get("account_id", ""))
        requested_ids = {str(item) for item in request_data.get("account_ids", []) if str(item)}
        if requested_account_id:
            listed = [account for account in listed if str(account.ctidTraderAccountId) == requested_account_id]
        if requested_ids:
            listed = [account for account in listed if str(account.ctidTraderAccountId) in requested_ids]
        if environment == "demo" and action in ("symbols", "history", "quote"):
            listed = [account for account in listed if not account.isLive] or listed
        if environment == "live" and action in ("symbols", "history", "quote"):
            listed = [account for account in listed if account.isLive] or listed
        if not listed:
            finish("no_authorized_accounts" if action in ("discover", "authenticate") else "no_demo_accounts")
            return
        if action in ("discover", "authenticate"):
            host_matches = []
            for account in listed:
                record = remember_account(account)
                same_host = (record["environment"] == "live") == (environment == "live")
                if same_host:
                    host_matches.append(account)
                else:
                    record["auth_error"] = "live_host_required" if record["environment"] == "live" else "demo_host_required"
            authorize_next(host_matches)
            return
        selected = listed[0]
        account_id = str(selected.ctidTraderAccountId)
        auth_req = ProtoOAAccountAuthReq()
        auth_req.ctidTraderAccountId = selected.ctidTraderAccountId
        auth_req.accessToken = access_token
        send(auth_req).addCallbacks(lambda auth: on_account_authorized(account_id, auth), failed)

    def on_app_authorized(_response) -> None:
        if action == "verify_application":
            result["application_status"] = "ACTIVE"
            finish()
            return
        accounts_req = ProtoOAGetAccountListByAccessTokenReq()
        accounts_req.accessToken = access_token
        send(accounts_req).addCallbacks(on_account_list, failed)

    def on_connected(connected_client) -> None:
        connected_flag["ok"] = True
        result["stage"] = "application_auth"
        app_auth = ProtoOAApplicationAuthReq()
        app_auth.clientId = client_id
        app_auth.clientSecret = client_secret
        send(app_auth).addCallbacks(on_app_authorized, failed)

    def overall_timeout() -> None:
        if finished:
            return
        if result["accounts"]:
            result["stage"] = result.get("stage") or "account_list"
            result["market_data"] = result.get("market_data") or "unverified"
            finish(None)
            return
        finish("provider_timeout" if connected_flag["ok"] else "transport_timeout")

    def transport_deadline() -> None:
        if not connected_flag["ok"]:
            finish("transport_timeout")

    client.setConnectedCallback(on_connected)
    client.setMessageReceivedCallback(on_message)
    timeout_call = reactor_instance.callLater(12, overall_timeout)
    reactor_instance.callLater(8, transport_deadline)
    client.startService()
    reactor_instance.run()
    print("CTRADER_RESULT:" + json.dumps(result, separators=(",", ":")), flush=True)
    return 0 if result["error"] is None else 1


if __name__ == "__main__":
    raise SystemExit(main())

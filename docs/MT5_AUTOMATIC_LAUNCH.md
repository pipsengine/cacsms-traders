# MT5 automatic read-only connection

Selecting MT5 Preferred or pressing Connect pairs the signed-in tenant with the
Windows gateway. The gateway attaches to the configured, already-open broker
terminal using MetaTrader5.initialize; a closed terminal starts automatically.
It does not launch or restore the terminal on each heartbeat.

Connect reports success only after the hosted API accepts its first heartbeat.
The worker sends account status and quotes every 15 seconds, rotating through
400 closed bars per symbol for H1, M1, M5, M15, M30, H4, D1, W1 and MN. H8 is
aggregated from H1 by the existing analytical adapter. History becomes available
over the first few minutes. The worker continues when the browser tab is closed.

The tenant-specific credential lasts eight hours and is stored only in worker
memory; the cloud stores its hash. Disconnect revokes it. Account changes require
reconnecting. A heartbeat expires after 90 seconds; the platform then reports
Disconnected and refuses to use the stale bridge. Broker passwords never leave
MT5. This bridge has no order submission capability and keeps execution disabled.

Cloud ingestion validates finite prices, OHLC bounds and closed bars, scopes all
candles to provider/tenant/account, and imports the account with trading disabled.
Global market-data tenant selection is restricted to platform administrators.
Tenant permissions are rechecked on every upload. No schema migration is needed.

The service runs scripts/run_mt5_local_gateway.py --terminal-path <terminal64.exe>
on the interactive Windows desktop and listens only on 127.0.0.1:8917. Allowed
website origins, Host validation and custom CORS headers protect the local API.
Web requests cannot choose executables or arbitrary upload destinations. Chrome
requires local/loopback network permission for the production website.

Python SDK reference: https://www.mql5.com/en/docs/python_metatrader5/mt5initialize_py
Chrome permission reference: https://developer.chrome.com/blog/local-network-access

On this PC the gateway starts at Windows sign-in through the current user's
Cacsms MT5 Gateway.lnk Startup shortcut. The shortcut runs pythonw.exe with the
fixed installed broker path and does not store a credential. Connect pairs it
again after a reboot or when the eight-hour upload credential expires.

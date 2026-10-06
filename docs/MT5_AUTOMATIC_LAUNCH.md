# Automatic MT5 opening

Selecting **MT5 Preferred** saves the authenticated provider policy, then requests
this PC's loopback gateway to open its configured broker terminal. Changing a
cTrader account or polling status does not launch MT5. An already-running matching
terminal is reused. Opening does not enable trading or connect cloud market data.

The gateway runs `scripts/run_mt5_local_gateway.py --terminal-path <terminal64.exe>`
using Python on the Windows PC. It listens only on 127.0.0.1:8917, accepts the
production website and local development origins, and requires a custom header.
Web requests cannot choose paths, arguments, credentials or commands.

No downloaded installer or protocol registration is used. The background process
must remain running; restart it after a PC reboot. Chrome may request local-network
permission: https://developer.chrome.com/blog/local-network-access

The hosted API still needs a separate authenticated market-data bridge to consume
local MT5 prices. ANALYSIS ONLY remains unchanged.

# Native NGN live trading

Cacsms Traders sizes, risks and records orders in the currency the broker reports for the connected account. NGN is a native denomination beside USD, EUR and any other currency MetaTrader 5 returns. Balances, leverage and exchange rates are not hardcoded.

Live order submission stays off until broker connectivity, contract specifications and the safety controls have been checked, and the account owner enables live trading on that account.

## What was added

- Account sync stores broker currency, equity, margin, free margin, margin level, floating profit and loss, and trade permissions.
- Contract specifications uploaded by the Windows gateway are stored per account, including the real symbol name. A fixed symbol suffix is not assumed.
- Position size uses the broker tick value in the account currency. Volume is rounded down. A minimum lot that would exceed the risk budget is rejected.
- Mode 1 (Trend-in-Trend, Channel Continuation, Breakout–Retest) and Mode 2 (AI Market Outlook) share one execution lock, one exposure budget and one order queue.
- An uncertain broker response is stored and is not sent again. Reconciliation against open tickets happens first.
- Equity baselines used for daily, weekly and drawdown limits come from observed broker equity.

## Operating states

| State | Meaning |
| --- | --- |
| Connected | The account sync is current |
| Disconnected | No current broker link |
| Degraded | The last sync is stale |
| Simulation | Orders are not being sent to a live or prop account |
| Live execution | The owner has enabled live submission on a live or prop account |

Demo autonomous mode can still send to a demo terminal without the live switch. Live and prop accounts cannot.

## Enable live trading

1. Run the API so migration `025_ngn_live_execution.sql` (SQLite) or `013_ngn_live_execution.sql` (PostgreSQL) is applied.
2. Connect the MT5 gateway and confirm the account currency, equity and contract specs.
3. On Trading Accounts, choose **Enable live** for that account. The action is audited and requires `accounts.enable_live`.
4. Set the platform operating mode to `LIVE_AUTONOMOUS` only after the checks above.
5. **Emergency stop** on the account blocks new entries from both modes until it is cleared.

## MT5 gateway

Do not run the MetaTrader 5 desktop terminal inside a Vercel function. Run `apps/api/app/domain/mt5_windows_worker.py` on a Windows machine that has the HFM terminal installed and logged in. The worker heartbeats market data and account figures to the FastAPI backend, then pulls at most one authorized order at a time.

Copy `deploy/mt5-gateway/.env.example` onto that host. The bridge token is issued from the platform and is not a broker password. Broker passwords stay in the MT5 terminal.

If the API process itself is attached to a local terminal, it may submit the order directly. Otherwise the order remains queued until the gateway reports a broker result.

## API

Authenticated routes, scoped to one tenant and one account:

- `GET /api/tenants/{tenant}/accounts/{account}/report`
- `POST /api/tenants/{tenant}/accounts/{account}/live-trading` with `{ "enabled": true }`
- `POST /api/tenants/{tenant}/accounts/{account}/emergency-stop` with `{ "enabled": true }`
- `POST /api/tenants/{tenant}/accounts/{account}/risk/evaluate` sizes a candidate and does not send it
- `WS /api/tenants/{tenant}/accounts/{account}/stream` pushes the same report

The gateway uses its bridge token:

- `POST /api/tenants/{tenant}/mt5-bridge/orders/pull`
- `POST /api/tenants/{tenant}/mt5-bridge/orders/result`

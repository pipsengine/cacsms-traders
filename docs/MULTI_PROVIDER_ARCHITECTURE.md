# Multi-provider market data

The existing Vercel web/API deployment, Neon PostgreSQL integration, identity/RBAC,
cTrader OAuth flow and EarnForex strength calculations are retained.

`ProviderManager` selects market data independently of execution. `AUTO` and
`MT5_PREFERRED` use MT5, then cTrader Direct; `CTRADER_PREFERRED` reverses that order.
An unavailable preferred provider can fall back for market data. No usable provider
produces `MARKET DATA UNAVAILABLE`. Legacy `MARKET_DATA_PROVIDER=none` remains an
explicit disable switch; legacy `mt5` and `ctrader` values become preference policies.

## Configuration and operator controls

System Control → Market & Trading Connections contains Overview, MT5 and cTrader
Direct. Platform administrators can change the global selection mode and choose
an OAuth-authorized cTrader demo account for the current tenant. Other users retain
their existing tenant connection controls. Choosing a market-data account does not
authorize execution.

The policy is stored in `system_settings` under `market_data.provider`:

```json
{"provider":"auto","selection_mode":"AUTO","tenant_id":"tenant-id","account_id":"authorized-ctid-account"}
```

Environment defaults: `MARKET_DATA_SELECTION_MODE`, `MARKET_DATA_PROVIDER`,
`MARKET_DATA_TENANT_ID`, and `MARKET_DATA_ACCOUNT_ID`. Persisted configuration wins.
MT5 uses the attached terminal account; its normalized account ID includes the broker server and login. A runtime with no MT5 SDK/terminal cannot
serve MT5 data; the manager can use an authorized healthy cTrader connection.

Provider state reports configured, authorized, connected, healthy, market data,
execution, heartbeat, data time, error, account and environment separately.
Status requests are passive. Workers make bounded cTrader health probes, at most
once per minute when needed; a successful data request updates telemetry.
`APP_INACTIVE`, `CTRADER_APP_INACTIVE`, and `PENDING_PROVIDER_ACTIVATION` remain
visible, and inactive applications receive no automatic OAuth or market-data retries.
Existing manual OAuth authorization is still required after activation.

## Normalized data and snapshots

Both adapters are registered through `NormalizedProvider`, which exposes the
shared `MarketDataProvider` contract. UTC timestamps, canonical symbols/timeframes,
OHLC, tick volume, symbol digits, pip/tick sizes, quotes, source and account are
normalized at the boundary. Spread is a price distance; unavailable historical
spread is null rather than a fabricated zero. Monthly closure uses calendar months; H8 aggregation
requires eight contiguous closed H1 bars with identical provider/account provenance.
Live quotes are display data. Scanner channel scoring uses closed prices.

`mi_provider_candle` keys bars by provider, account, symbol, timeframe and open time.
Duplicate synchronization updates the same bar. Existing candles are copied with
their recorded source and an unspecified legacy account; live account ingestion
does not silently mix these legacy bars with an attached account's history.
The old candle table is retained for compatibility and historical recovery.

`mi_provider_snapshot` defines an immutable provider/account analytical scope.
Provider or account changes finalize the old scope and create a new one. Cached
strength and scanner results are invalidated. Finalized scopes reject new analytical
provenance writes. `mi_analysis_provenance` links strength, relationships, scanner,
structure and channel calculations to the scope. Historical strength/reference reads
are scoped, and scanner composition refuses strength from a different snapshot.

Ingestion detects gaps within fetched windows and across incremental outage gaps.
Weekends are excluded from expected FX bars; unexpected gaps, including holidays,
remain explicit observations. Missing bars are never interpolated or synthesized.
Stale, missing or invalid baskets prevent successful autonomous strength analysis;
scanner instruments with missing/stale required history are excluded.

`POST /api/providers/backfill` accepts symbol, timeframe, timezone-aware start/end,
and a bounded count (1–2000). It uses the selected provider/account and records
provenance. Request consecutive bounded windows for deeper history. Providers may
return less history than requested; no missing history is invented.

## Execution and audit

Production remains `ANALYSIS_ONLY`. Production mode changes cannot enable SHADOW,
DEMO_AUTONOMOUS or LIVE_AUTONOMOUS; PAUSED and EMERGENCY_STOP remain available.
No order-submission implementation is added. Market-data selection never changes
`execution.provider` or the explicitly bound execution account.

Future campaign creation must call `bind_campaign`, supplying an explicit provider
and account. A persisted campaign cannot be rebound, including during data failover.
`execution_provider_binding` is independent of analytical snapshots.

Provider connection/degradation/recovery, selection, market-data changes, inactive
cTrader applications and MT5 connection failures use the existing audit trail.
Repeated unchanged state observations do not repeat transition events.

## Migrations and verification

SQLite migration: `database/migrations/015_multi_provider.sql`.
Neon migration: `apps/api/database/migrations/postgres/003_multi_provider.sql`.
The production migration restores Operating Mode to `ANALYSIS_ONLY`.
Both use the existing bootstrap migration runner; deployment architecture is unchanged.
The Vercel HTTP service retains its existing disabled-persistent-worker behavior.
Autonomous polling runs in the existing persistent backend worker runtime; explicit
intelligence cycles and authorized backfills can also refresh provider health.

Tests cover provider availability/preferences, recovery, closed-bar normalization,
gap/stale detection, incremental outages, duplicate prevention, provider/account
isolation, snapshot finalization/history isolation, 28-pair strength calculations
through stored data from both providers, OAuth inactivity, administrator policy
controls and immutable execution ownership. Live broker connectivity and Neon
migration execution require their configured runtimes and are not simulated by unit tests.

cTrader quote decoding follows the official [symbol-data contract](https://help.ctrader.com/open-api/symbol-data/)
and [Spotware protocol schemas](https://github.com/spotware/openapi-proto-messages).

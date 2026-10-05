# Strength Intelligence production data-path audit

The original gate was `StrengthEngine._tick()` in `apps/api/app/market/strength_engine.py`: it required `get_mt5_market_context()` and both `mt5_connected` and `market_data_ready`. The gateway factory in `mt5_gateway.py` only constructed MT5 or NULL adapters. `CurrencyStrengthMatrixService` also imported the MT5 broker-symbol resolver. History scope came from `mt5.active_tenant_id`. Frontend header, banners, empty cells, source bar and sidebar had MT5-specific labels/state checks.

The new centralized selection is `market/market_data.py`, reading `system_settings['market_data.provider']` as `{provider, tenant_id, account_id}`, with server-side `MARKET_DATA_PROVIDER`, `MARKET_DATA_TENANT_ID`, `MARKET_DATA_ACCOUNT_ID` fallbacks. Production defaults to cTrader; no automatic MT5 fallback. cTrader uses the existing read-only Open API discovery subprocess for application/account authorization, canonical symbol discovery and closed historical trendbars. Only an explicitly selected authorized demo account is eligible for ingestion. No execution or risk authorization is changed.

`GET /api/market-intelligence/status` and the matrix meta expose safe provider, OAuth, account, basket, candle and calculation diagnostics. Without a selected tenant, an aggregate read of existing cTrader authorization/account records distinguishes missing OAuth from completed OAuth requiring scope selection. No identifiers, tokens or credentials are included in diagnostics.

Production observations before deployment on 5 October 2026: status returned NULL/MetaTrader5 unavailable; health reported strength_engine stopped, market_scanner stopped, intelligence_worker disabled. Vercel's serverless startup deliberately skips background services. A stopped worker now returns WORKER_UNAVAILABLE rather than claiming it is calculating. Real continuous synchronization still requires the existing always-on backend runtime; do not enable background trading to address that blocker.

MT5-specific adapters/session management remain available in System Control. Scanner and other engines outside Strength Intelligence retain legacy MT5 code and are not made provider-independent by this change. Candle and strength-history tables still use the existing shared-universe schema; fully isolated multi-provider/multi-account history requires a separate storage migration. The strength engine resets its live calculation and resynchronizes the basket when provider scope changes.

Verification: frontend TypeScript/Vite build, Python compilation, strength/scoring/history regression tests and provider gating tests. Production OAuth, account discovery, mapping, candles and matrix must be reported from the deployed API, never inferred from local tests.

## Final production verification, 5 October 2026 (Africa/Lagos)

Deployment: dpl_3MB9Y6Pcnk53eXGmni1Ag7BfNRS2, READY, aliased to https://cacsms-traders.vercel.app.

Both the live status API and matrix API report:
- active_provider: ctrader
- provider_status / strength_engine_status: AUTHORIZATION REQUIRED
- authorization_status: NOT_AUTHORIZED
- accounts_discovered: 0
- account_status: NOT_SELECTED
- symbols_resolved: 0/28
- closed_bar_status: NOT_STARTED
- failed_symbol_mappings: [] (discovery not attempted)
- failed_candle_requests: [] (retrieval not attempted)
- last_successful_sync / last_calculation: null
- matrix / rankings / currency summary: empty
- analysis_only: true

Missing pairs: AUDCAD, AUDCHF, AUDJPY, AUDNZD, AUDUSD, CADCHF, CADJPY, CHFJPY, EURAUD, EURCAD, EURCHF, EURGBP, EURJPY, EURNZD, EURUSD, GBPAUD, GBPCAD, GBPCHF, GBPJPY, GBPNZD, GBPUSD, NZDCAD, NZDCHF, NZDJPY, NZDUSD, USDCAD, USDCHF, USDJPY.

The production HTML and its deployed JS bundle returned HTTP 200. The bundle contains the authorization-required and market-data-unavailable views and no longer contains the old closed-MT5-bars calculation message. No browser session was available for a rendered visual check.

Live health reported strength_engine stopped and intelligence_worker disabled. Market scanner reported running during the final health read; no execution, risk, trading or mode settings were changed. The requested Strength path remains analysis-only.

The data chain currently stops BEFORE cTrader authorization. Real candle retrieval, synchronized bars, persistence and a populated strength matrix are not claimed. Next steps: authorize cTrader in System Control, configure the intended market-data tenant/account centrally, and run the strength worker on the always-on backend. Existing shared-universe history storage remains a limitation for switching among multiple accounts/providers.

Validation: 54 targeted tests passed across provider-path, strength/scoring/history, production-auth/routing/deployment suites; frontend TypeScript/Vite build and Python compilation passed. Production verification caught and corrected PostgreSQL dictionary-row handling and a status route that attempted adapter creation before reporting authorization state.

## Changed files

Backend:
- apps/api/app/market/market_data.py (new centralized configuration and diagnostics)
- apps/api/app/market/ctrader_gateway.py (new read-only provider adapter)
- apps/api/app/market/strength_engine.py
- apps/api/app/market/csm_service.py
- apps/api/app/market/ingestion_runner.py
- apps/api/app/market/intelligence_cycle.py
- apps/api/app/market/strength_intel_store.py
- apps/api/app/routers/market_intelligence.py
- apps/api/app/routers/platform.py
- apps/api/app/services/ctrader_discovery_worker.py (calendar-month closed-bar normalization)

Frontend:
- apps/web/src/components/AppShell.tsx
- apps/web/src/pages/hubs/StrengthIntelligence.tsx
- apps/web/src/features/market-intelligence/types.ts
- apps/web/src/features/market-intelligence/components/MatrixPanelStates.tsx
- apps/web/src/features/market-intelligence/components/MatrixStatusBar.tsx
- apps/web/src/features/market-intelligence/components/StrengthMatrixTable.tsx
- apps/web/src/features/market-intelligence/components/StrengthPageHeader.tsx
- apps/web/src/types.ts

Validation/deployment/report:
- tests/test_market_data_strength_path.py
- .gitignore
- .vercelignore
- docs/STRENGTH_PRODUCTION_AUDIT.md

## Remaining MT5 occurrences and classification

- Strength frontend/API/calculation/history: no MT5 dependency remains. The link #/system-control/mt5 is a legacy navigation identifier for the existing Market & Trading Connections tab, not a provider gate.
- market_data.py: explicit MT5 branch and lazy adapter imports, used only when MT5 is selected. No automatic fallback from cTrader to MT5.
- mt5_gateway.py, mt5_platform_status.py, mt5_session.py, mt5_contract.py and domain MT5 connection management: provider adapter/compatibility implementation, retained for MT5 as an available provider.
- platform.py: legacy MT5 health remains available for System Control; the global sidebar consumes market_data instead.
- Scanner and other intelligence engines outside this Strength task: legacy MT5 integrations remain; they are documented rather than represented as refactored.

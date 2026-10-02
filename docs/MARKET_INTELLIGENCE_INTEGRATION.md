# Cacsms-Traders Market Intelligence — Integration
This is an additive package for the existing detailed Cacsms-Traders Foundation. Do not create a second app, database, auth system, tenant system, shell or MT5 connection module.

1. Copy `apps/api/app/market/` into the existing API application.
2. Copy `apps/api/app/routers/market_intelligence.py` and `apps/api/app/workers/market_intelligence_worker.py`.
3. Apply `database/migrations/002_market_intelligence_foundation.sql` to the existing `database/db_cacsms-traders.db`.
4. Register `market_intelligence.router` once in the existing FastAPI `main.py`. `REPLACE/apps/api/app/main.py` is supplied only as a reference integration version; reconcile it if your foundation has changed.
5. Copy `apps/web/src/features/market-intelligence/`, `apps/web/src/pages/StrengthMatrix.tsx`, and `apps/web/src/styles/market-intelligence.css`.
6. Import `market-intelligence.css` once in the existing frontend entry point and add `Strength Matrix` under Market Intelligence in the existing navigation/router. Do not replace the app shell blindly.
7. Wire the existing Local MT5 gateway to the `MarketDataGateway` contract. The adapter must return CLOSED candles only; never fabricate unavailable history.
8. Start the Market Intelligence worker as a backend process/service, not from React.
9. Run tests and frontend build.

This layer must remain analysis-only. It must not submit orders or emit BUY/SELL instructions.

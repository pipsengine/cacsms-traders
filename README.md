# Cacsms-Traders — Detailed Foundation

Production-oriented foundation for the clean Cacsms-Traders rebuild. This release deliberately contains **no market strategy, AI opportunity logic or live order submission**. It establishes the platform on which those layers will be built.

## Included
- FastAPI modular backend with SQLite repository/unit-of-work foundation.
- Multi-tenant identity, memberships, RBAC permissions, sessions and audit trail.
- User profile and tenant administration APIs.
- Trading-account registry for DEMO, LIVE and PROP_FIRM accounts with USD/NGN-ready currency model.
- Trading gateway abstraction and safe local-MT5 stub (read-only foundation).
- Runtime health, system modes, configuration and security event model.
- React + TypeScript + Vite light-theme administration shell with Overview, Tenants, Users & Access, Trading Accounts, MT5 Connections, System Control, Audit Trail and Profile views.
- Reusable design tokens/components and responsive desktop UI.
- Migrations, bootstrap data, indexes, tests, scripts and architecture documentation.

## Database
`database/db_cacsms-traders.db`

SQLite has no database username. `cacsms` is the bootstrap **application** username. Change the bootstrap password immediately outside development.

## Start backend
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r apps/api/requirements.txt
python scripts/init_db.py
uvicorn apps.api.app.main:app --reload --port 8000
```

## Start frontend
```bash
cd apps/web
npm install
npm run dev
```

## Deployment
| Part | Location |
|---|---|
| Frontend (Vite build of `apps/web`) | Vercel — https://cacsms-traders.vercel.app |
| Vercel API proxy (`apps/web/api/proxy.js`) | Vercel serverless function serving `https://cacsms-traders.vercel.app/api/*` |
| Backend API (FastAPI + SQLite + MT5) | Windows host running the MT5 terminal, published on a private HTTPS URL (`API_ORIGIN`) |
| Source | https://github.com/pipsengine/cacsms-traders |

**Routing.** Every backend route lives under `/api` (`/api/auth/login`, `/api/auth/me`, `/api/auth/logout`, `/api/health`,
`/api/tenants/...`, `/api/market-intelligence/...`, `/api/connections/ctrader/callback`). Locally Vite proxies `/api` to
`127.0.0.1:8000`; on Vercel `apps/web/vercel.json` rewrites `/api/*` to the proxy function, which forwards to `API_ORIGIN`.
The browser always talks to its own origin, so the session is a first-party `HttpOnly` cookie (`ct_session`, `Path=/api`,
`SameSite=Lax`, `Secure` in production). Cookie-authenticated writes must send `X-CT-Client` (CSRF guard).
The backend cannot run on Vercel itself: it needs the MT5 terminal, a durable SQLite file and long-running engine threads.

**Database.** The only production database is the SQLite file on the trading host (`DATABASE_PATH`, on durable local disk —
back it up). Vercel holds no data. With `APP_ENV=production` the API refuses to start against a missing database file
instead of silently creating an empty one; provision once with `DATABASE_ALLOW_CREATE=1` (or `python scripts/init_db.py`),
then remove the flag.

**Setup / redeploy**
1. Trading host `.env`: `APP_ENV=production`, `DATABASE_PATH=<absolute path>`, strong `SUPER_ADMIN_PASSWORD` /
   `BOOTSTRAP_PASSWORD`, `API_PROXY_SECRET=<long random string>`, and the `CTRADER_*` values (server-side only).
   Restart the API (`npm run dev`, or `py -3.14 scripts/run_api.py`).
2. Publish the API over HTTPS, e.g. a named Cloudflare Tunnel to `http://localhost:8000`.
3. Vercel → Project → Settings: Root Directory `apps/web`. Environment Variables (Production, **not** `VITE_*`):
   `API_ORIGIN=https://<tunnel-host>` (no trailing slash, no `/api`) and `API_PROXY_SECRET=<same value as the host>`.
   Leave `VITE_API_BASE` unset so the browser stays same-origin.
4. Redeploy (Deployments → Redeploy, or push to the connected branch). Environment variable changes need a redeploy.
5. Verify: `https://cacsms-traders.vercel.app/api/health` → `200 {"status":"ok",...}`. A `503` from the proxy means
   `API_ORIGIN` is not set; `502` means the host or tunnel is down.
6. cTrader: register `https://cacsms-traders.vercel.app/api/connections/ctrader/callback` as the redirect URI in the
   cTrader Open API app and set the same value in `CTRADER_REDIRECT_URI`.

## Market Intelligence layer
Integrated from the detailed Market Intelligence package (see `docs/MARKET_INTELLIGENCE_INTEGRATION.md`):
- Backend: `apps/api/app/market/`, `/api/market-intelligence/*` routes, migration `003_market_intelligence_foundation.sql`
- UI: **Strength Matrix** in the shell (Market Intelligence nav), `apps/web/src/features/market-intelligence/`
- Worker: `apps/api/app/workers/market_intelligence_worker.py` (run as a separate backend process when MT5 data is wired)

Apply migrations after pull: `python scripts/init_db.py`

## Safety boundary
Platform mode remains ANALYSIS_ONLY for trading. Market intelligence provides strength and relationship inspection only—no BUY/SELL signals or order execution. AI reasoning, opportunity contracts, risk authorization and execution are later layers.

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

## Production deployment architecture

This repository is already structured for the required production split:

- Frontend remains on Vercel under `apps/web`.
- The API runtime runs as a cloud backend service rather than in the browser.
- The public backend address is configured with `API_ORIGIN` only; `localhost` is a development-only dependency.
- The existing auth, database, audit, and market-intelligence layers stay in the backend process, where autonomous services can continue without a browser session.

## Database
`database/db_cacsms-traders.db`

The safest production database architecture for the existing app is to keep SQLite on durable storage, not on a workstation path. Persist the database file to a mounted volume or cloud disk so it survives backend restarts and redeployments without losing state. SQLite is a valid choice here because the repo already relies on WAL mode and a durable file-backed model.

SQLite has no database username. `cacsms` is the bootstrap **application** username. Change the bootstrap password immediately outside development.

## Start backend
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r apps/api/requirements.txt
python scripts/init_db.py
python scripts/run_api.py
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
| Frontend | Vercel — https://cacsms-traders.vercel.app |
| Vercel API proxy | `apps/web/api/proxy.js` serverless function serving `/api/*` |
| Cloud backend | Always-on HTTPS service such as `https://api.example.com` |
| Database | Durable volume mounted to the backend process |
| cTrader gateway | Server-side backend process, not the local machine |

**Routing.** Every backend route lives under `/api` (`/api/auth/login`, `/api/auth/me`, `/api/auth/logout`, `/api/health`, `/api/health/ready`, `/api/health/live`, `/api/tenants/...`, `/api/connections/ctrader/callback`). Local Vite development uses `localhost`, while production goes through Vercel to the cloud backend using `API_ORIGIN`.

**Production posture.** The backend service binds to `0.0.0.0` in production. The public address is configured through environment variables only; no code path should depend on `127.0.0.1`, a temporary tunnel, or a browser connection for autonomous processing.

**Database.** The production database must live on durable, non-ephemeral storage. With `APP_ENV=production`, the backend refuses to silently create a fresh local SQLite database; provision the file once and keep it on a persistent mount.

**Setup / redeploy**
1. Backend `.env`: `APP_ENV=production`, `APP_HOST=0.0.0.0`, `DATABASE_PATH=/var/lib/cacsms/database/db_cacsms-traders.db`, strong bootstrap/super-admin credentials, `API_ORIGIN=https://api.example.com`, `WEB_ORIGINS=https://cacsms-traders.vercel.app`, and server-side `CTRADER_*` values.
2. Run the API as a service or container with automatic restart enabled. This backend continues operating when the workstation is off or asleep.
3. Vercel → Project → Settings → Environment Variables: set `API_ORIGIN=https://api.example.com` (no trailing slash, no `/api`) and `API_PROXY_SECRET=<same value as the cloud backend>`. Keep the frontend bundle free of backend URLs.
4. Validate the public chain: `https://cacsms-traders.vercel.app/api/health` → cloud backend `https://api.example.com/api/health` → database and cTrader gateway.
5. cTrader OAuth redirect URI: register `https://cacsms-traders.vercel.app/api/connections/ctrader/callback` in the cTrader Open API app and set the same value in `CTRADER_REDIRECT_URI`.

## Production health endpoints
The backend exposes readiness and liveness endpoints for process supervision:

- `/api/health` — readiness check for database/auth bootstrapping
- `/api/health/ready` — ready-to-serve endpoint
- `/api/health/live` — liveness endpoint used by process managers

## Deployment commands
```bash
# Back-end service
python scripts/init_db.py
python scripts/run_api.py

# Frontend build
cd apps/web
npm install
npm run build
```

## Security notes
- Never commit `.env` files or database backups.
- Never expose cTrader secrets, access tokens, refresh tokens, session secrets, or database credentials to the browser.
- Use HTTPS only in production.
- Keep CORS explicit and tighten it to the Vercel production origin.

## Notes for the live deployment
The repo now assumes a cloud backend rather than a developer workstation. The live environment must provision a durable VM or container host, a persistent data volume, and the production cTrader credentials before the system is considered fully independent from the local PC.

## Market Intelligence layer
Integrated from the detailed Market Intelligence package (see `docs/MARKET_INTELLIGENCE_INTEGRATION.md`):
- Backend: `apps/api/app/market/`, `/api/market-intelligence/*` routes, migration `003_market_intelligence_foundation.sql`
- UI: **Strength Matrix** in the shell (Market Intelligence nav), `apps/web/src/features/market-intelligence/`
- Worker: `apps/api/app/workers/market_intelligence_worker.py` (run as a separate backend process when MT5 data is wired)

Apply migrations after pull: `python scripts/init_db.py`

## Safety boundary
Platform mode remains ANALYSIS_ONLY for trading. Market intelligence provides strength and relationship inspection only—no BUY/SELL signals or order execution. AI reasoning, opportunity contracts, risk authorization and execution are later layers.

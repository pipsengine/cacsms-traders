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
| Backend API (FastAPI + SQLite + MT5) | Windows host running the MT5 terminal; must be exposed on a public HTTPS URL |
| Source | https://github.com/pipsengine/cacsms-traders |

The backend cannot run on Vercel (it needs the MT5 terminal, the SQLite file and long-running engine threads).
To make the Vercel site work:

1. Expose the API over HTTPS (e.g. Cloudflare Tunnel: `cloudflared tunnel --url http://localhost:8000`, or a named tunnel / Windows VPS).
2. In the Vercel project → Settings → Environment Variables set `VITE_API_BASE=https://<public-api-host>` (no trailing slash), then redeploy — Vite bakes it in at build time.
3. In the API `.env` keep `WEB_ORIGINS=https://cacsms-traders.vercel.app` (CORS) and set strong `SUPER_ADMIN_PASSWORD` / `BOOTSTRAP_PASSWORD`; restart the API.

Without `VITE_API_BASE` the deployed site calls `cacsms-traders.vercel.app/auth/login` itself and every sign-in returns 404.

## Market Intelligence layer
Integrated from the detailed Market Intelligence package (see `docs/MARKET_INTELLIGENCE_INTEGRATION.md`):
- Backend: `apps/api/app/market/`, `/api/market-intelligence/*` routes, migration `003_market_intelligence_foundation.sql`
- UI: **Strength Matrix** in the shell (Market Intelligence nav), `apps/web/src/features/market-intelligence/`
- Worker: `apps/api/app/workers/market_intelligence_worker.py` (run as a separate backend process when MT5 data is wired)

Apply migrations after pull: `python scripts/init_db.py`

## Safety boundary
Platform mode remains ANALYSIS_ONLY for trading. Market intelligence provides strength and relationship inspection only—no BUY/SELL signals or order execution. AI reasoning, opportunity contracts, risk authorization and execution are later layers.

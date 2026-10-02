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

## Safety boundary
This foundation is ANALYSIS_ONLY. It cannot place real trades. Market intelligence, AI reasoning, opportunity contracts, risk authorization and execution will be added as separate approved layers.

# Architecture

Cacsms-Traders starts as a modular monolith plus autonomous workers. The browser is an observability/control client; autonomous services will not depend on an open browser.

## Layers
1. Web UI — React/TypeScript, light design system.
2. API — authentication, tenant isolation, RBAC, administration, accounts, health and audit.
3. Application services — business use cases; no HTTP or SQLite concerns.
4. Domain — tenant, identity, account, configuration and gateway contracts.
5. Infrastructure — SQLite repositories, migrations, logging and MT5 adapter.
6. Workers — reserved runtime boundary for market/analysis/trading workers.

## Multi-tenancy
Every tenant-owned row carries `tenant_id`. Tenant access is verified in the backend. Platform administrators are explicit and audited. Cross-tenant reads are never authorized by frontend filtering.

## Trading safety
Trading accounts have separate `trading_enabled` and `autonomous_trading_enabled` controls. System operating mode defaults to `ANALYSIS_ONLY`. No execution gateway exists in this foundation.

## Future layers
Market Intelligence -> Market World Model -> AI Reasoning -> Opportunity/Confirmation -> Hard Risk -> Execution -> Learning.

# Foundation data model

Core entities: tenants, users, roles, permissions, role_permissions, tenant_memberships, auth_sessions, user_preferences, trading_accounts, trading_connections, account_risk_profiles, system_settings, tenant_settings, audit_events, security_events, system_events, worker_heartbeats, reference_currencies, reference_instruments (29-symbol FX/metal universe), schema_migrations.

The market-intelligence schema is intentionally absent from this foundation. It will be introduced with the approved Market Intelligence layer rather than prematurely coupling the platform database to an unfinished strategy model.

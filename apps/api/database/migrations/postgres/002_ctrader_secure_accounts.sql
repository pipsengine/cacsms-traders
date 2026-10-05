ALTER TABLE ctrader_connections ADD COLUMN IF NOT EXISTS authorization_status TEXT NOT NULL DEFAULT 'NEEDS_REAUTH';
ALTER TABLE ctrader_connections ADD COLUMN IF NOT EXISTS connection_status TEXT NOT NULL DEFAULT 'DISCONNECTED';
ALTER TABLE ctrader_connections ADD COLUMN IF NOT EXISTS token_key_version INTEGER NOT NULL DEFAULT 0;
ALTER TABLE ctrader_connections ADD COLUMN IF NOT EXISTS permission_scope TEXT;
ALTER TABLE ctrader_connections ADD COLUMN IF NOT EXISTS last_successful_connection_at TEXT;
ALTER TABLE ctrader_connections ADD COLUMN IF NOT EXISTS last_sync_at TEXT;
ALTER TABLE ctrader_connections ADD COLUMN IF NOT EXISTS last_error_code TEXT;

CREATE TABLE IF NOT EXISTS ctrader_accounts(
  tenant_id TEXT NOT NULL REFERENCES tenants(id),
  ctid_trader_account_id TEXT NOT NULL,
  trader_login TEXT,
  broker_name TEXT,
  account_type TEXT,
  environment TEXT NOT NULL CHECK(environment='demo'),
  currency_code TEXT,
  authorization_status TEXT NOT NULL DEFAULT 'AUTHORIZED',
  last_synced_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(tenant_id, ctid_trader_account_id)
);

CREATE INDEX IF NOT EXISTS ix_ctrader_accounts_tenant_status
  ON ctrader_accounts(tenant_id, authorization_status, environment);
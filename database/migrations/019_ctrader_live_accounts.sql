-- Allow discovered live accounts. Trading execution remains disabled.
CREATE TABLE IF NOT EXISTS ctrader_accounts_env(
  tenant_id TEXT NOT NULL REFERENCES tenants(id),
  ctid_trader_account_id TEXT NOT NULL,
  trader_login TEXT,
  broker_name TEXT,
  account_type TEXT,
  environment TEXT NOT NULL CHECK(environment IN ('demo', 'live')),
  currency_code TEXT,
  authorization_status TEXT NOT NULL DEFAULT 'AUTHORIZED',
  last_synced_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(tenant_id, ctid_trader_account_id)
);
INSERT INTO ctrader_accounts_env(
  tenant_id, ctid_trader_account_id, trader_login, broker_name, account_type, environment, currency_code,
  authorization_status, last_synced_at, created_at, updated_at)
SELECT tenant_id, ctid_trader_account_id, trader_login, broker_name, account_type, environment, currency_code,
  authorization_status, last_synced_at, created_at, updated_at
FROM ctrader_accounts;
DROP TABLE ctrader_accounts;
ALTER TABLE ctrader_accounts_env RENAME TO ctrader_accounts;
CREATE INDEX IF NOT EXISTS ix_ctrader_accounts_tenant_status
  ON ctrader_accounts(tenant_id, authorization_status, environment);

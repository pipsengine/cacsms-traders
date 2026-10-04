-- cTrader Open API OAuth: one-time authorization states and tenant-scoped connection tokens.
-- Tokens are server-side only; API responses never include them.
CREATE TABLE IF NOT EXISTS ctrader_oauth_states(
  state_hash TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(id),
  user_id TEXT NOT NULL REFERENCES users(id),
  environment TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  used_at TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ctrader_connections(
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(id),
  environment TEXT NOT NULL,
  access_token TEXT NOT NULL,
  refresh_token TEXT,
  token_type TEXT,
  expires_at TEXT,
  connected_by TEXT REFERENCES users(id),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, environment)
);

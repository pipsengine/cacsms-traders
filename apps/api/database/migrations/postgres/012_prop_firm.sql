-- Prop firm accounts, versioned rules, snapshots, compliance decisions and audit.
-- Broker passwords are stored only as ciphertext. The API never returns them.

CREATE TABLE IF NOT EXISTS pf_firm (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  name TEXT NOT NULL,
  slug TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'ACTIVE',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (tenant_id, slug)
);
CREATE INDEX IF NOT EXISTS ix_pf_firm_tenant ON pf_firm(tenant_id, name);

CREATE TABLE IF NOT EXISTS pf_rule_version (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  firm_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  rules_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE (firm_id, version)
);

CREATE TABLE IF NOT EXISTS pf_account (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  firm_id TEXT NOT NULL,
  rule_version_id TEXT NOT NULL,
  trading_account_id TEXT,
  display_name TEXT NOT NULL,
  external_id TEXT NOT NULL,
  broker TEXT NOT NULL,
  broker_login TEXT,
  broker_server TEXT,
  credential_cipher TEXT,
  environment TEXT NOT NULL,
  lifecycle TEXT NOT NULL,
  phase_label TEXT NOT NULL,
  account_size REAL NOT NULL,
  currency TEXT NOT NULL DEFAULT 'USD',
  firm_confirmed INTEGER NOT NULL DEFAULT 0,
  automation_confirmed INTEGER NOT NULL DEFAULT 0,
  phase_ends_at TEXT,
  status_note TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_pf_account_tenant ON pf_account(tenant_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS ix_pf_account_login ON pf_account(broker_login);

CREATE TABLE IF NOT EXISTS pf_snapshot (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  account_id TEXT NOT NULL,
  balance REAL NOT NULL,
  equity REAL NOT NULL,
  floating_pnl REAL NOT NULL,
  commission REAL NOT NULL DEFAULT 0,
  open_positions INTEGER NOT NULL DEFAULT 0,
  pending_orders INTEGER NOT NULL DEFAULT 0,
  equity_high REAL NOT NULL,
  eod_equity_high REAL NOT NULL,
  day_start_balance REAL NOT NULL,
  day_start_equity REAL NOT NULL,
  recorded_at TEXT NOT NULL,
  source TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_pf_snapshot_account ON pf_snapshot(account_id, recorded_at DESC);

CREATE TABLE IF NOT EXISTS pf_evaluation (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  account_id TEXT NOT NULL,
  snapshot_id TEXT,
  decision TEXT NOT NULL,
  protection TEXT NOT NULL,
  daily_drawdown_pct REAL,
  max_drawdown_pct REAL,
  reasons_json TEXT NOT NULL,
  close_positions INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_pf_evaluation_account ON pf_evaluation(account_id, created_at DESC);

CREATE TABLE IF NOT EXISTS pf_deal (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  account_id TEXT NOT NULL,
  broker_deal_id TEXT NOT NULL,
  symbol TEXT NOT NULL,
  direction TEXT NOT NULL,
  volume REAL NOT NULL,
  profit REAL NOT NULL,
  commission REAL NOT NULL DEFAULT 0,
  strategy TEXT,
  closed_at TEXT NOT NULL,
  UNIQUE (account_id, broker_deal_id)
);

CREATE TABLE IF NOT EXISTS pf_order_intent (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  account_id TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  symbol TEXT NOT NULL,
  decision TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE (account_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS pf_audit (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  account_id TEXT,
  firm_id TEXT,
  action TEXT NOT NULL,
  actor TEXT NOT NULL,
  detail_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_pf_audit_tenant ON pf_audit(tenant_id, created_at DESC);

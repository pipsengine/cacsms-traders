-- Native account-currency execution for PostgreSQL production.
-- Money is stored as exact decimal text. Live submission stays off until the account owner enables it.

ALTER TABLE trading_accounts ADD COLUMN IF NOT EXISTS margin_level DOUBLE PRECISION;
ALTER TABLE trading_accounts ADD COLUMN IF NOT EXISTS floating_pnl DOUBLE PRECISION;
ALTER TABLE trading_accounts ADD COLUMN IF NOT EXISTS trade_allowed INTEGER;
ALTER TABLE trading_accounts ADD COLUMN IF NOT EXISTS trade_expert INTEGER;

ALTER TABLE account_risk_profiles ADD COLUMN IF NOT EXISTS max_weekly_loss_pct DOUBLE PRECISION;
ALTER TABLE account_risk_profiles ADD COLUMN IF NOT EXISTS max_drawdown_pct DOUBLE PRECISION;
ALTER TABLE account_risk_profiles ADD COLUMN IF NOT EXISTS max_spread_points DOUBLE PRECISION;
ALTER TABLE account_risk_profiles ADD COLUMN IF NOT EXISTS margin_floor_pct DOUBLE PRECISION;
ALTER TABLE account_risk_profiles ADD COLUMN IF NOT EXISTS emergency_stop INTEGER NOT NULL DEFAULT 0;
ALTER TABLE account_risk_profiles ADD COLUMN IF NOT EXISTS live_trading_enabled INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS equity_baselines (
  trading_account_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  currency TEXT NOT NULL,
  peak_equity TEXT NOT NULL,
  day_start_equity TEXT NOT NULL,
  week_start_equity TEXT NOT NULL,
  day_key TEXT NOT NULL,
  week_key TEXT NOT NULL,
  source TEXT NOT NULL,
  recorded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS currency_snapshots (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  trading_account_id TEXT,
  from_currency TEXT NOT NULL,
  to_currency TEXT NOT NULL,
  rate TEXT NOT NULL,
  as_of TEXT NOT NULL,
  source TEXT NOT NULL,
  broker_ref TEXT,
  reconciliation_status TEXT NOT NULL DEFAULT 'UNVERIFIED'
);
CREATE INDEX IF NOT EXISTS ix_currency_snapshots_pair ON currency_snapshots(tenant_id, from_currency, to_currency, as_of DESC);

CREATE TABLE IF NOT EXISTS broker_contract_specs (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  trading_account_id TEXT NOT NULL,
  canonical_symbol TEXT NOT NULL,
  broker_symbol TEXT NOT NULL,
  currency_profit TEXT,
  currency_margin TEXT,
  digits INTEGER,
  point TEXT,
  tick_size TEXT NOT NULL,
  tick_value TEXT NOT NULL,
  tick_value_currency TEXT NOT NULL,
  volume_min TEXT NOT NULL,
  volume_max TEXT NOT NULL,
  volume_step TEXT NOT NULL,
  stops_level_points INTEGER NOT NULL DEFAULT 0,
  spread_points TEXT,
  margin_per_lot TEXT,
  commission_per_lot TEXT NOT NULL DEFAULT '0',
  updated_at TEXT NOT NULL,
  UNIQUE (trading_account_id, canonical_symbol)
);

CREATE TABLE IF NOT EXISTS trade_requests (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  trading_account_id TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  mode TEXT NOT NULL,
  action TEXT NOT NULL DEFAULT 'PLACE',
  symbol TEXT NOT NULL,
  broker_symbol TEXT,
  direction TEXT,
  entry_price TEXT,
  stop_price TEXT,
  target_price TEXT,
  volume TEXT,
  risk_amount TEXT,
  projected_loss TEXT,
  currency TEXT NOT NULL,
  status TEXT NOT NULL,
  rejection_reason TEXT,
  ticket TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (tenant_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS ix_trade_requests_account ON trade_requests(tenant_id, trading_account_id, status);

CREATE TABLE IF NOT EXISTS execution_results (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  trade_request_id TEXT NOT NULL,
  retcode INTEGER,
  ticket TEXT,
  deal TEXT,
  outcome TEXT NOT NULL,
  broker_comment TEXT,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_execution_results_request ON execution_results(trade_request_id, created_at);

CREATE TABLE IF NOT EXISTS execution_audit (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  trading_account_id TEXT NOT NULL,
  trade_request_id TEXT,
  stage TEXT NOT NULL,
  detail_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_execution_audit_account ON execution_audit(tenant_id, trading_account_id, created_at);

CREATE TABLE IF NOT EXISTS execution_locks (
  trading_account_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  holder TEXT NOT NULL,
  acquired_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS broker_deals (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  trading_account_id TEXT NOT NULL,
  deal_ticket TEXT NOT NULL,
  order_ticket TEXT,
  symbol TEXT,
  profit TEXT,
  commission TEXT,
  swap TEXT,
  volume TEXT,
  price TEXT,
  dealt_at TEXT NOT NULL,
  entry TEXT,
  currency TEXT NOT NULL,
  reconciliation_status TEXT NOT NULL DEFAULT 'BROKER_REPORTED',
  UNIQUE (trading_account_id, deal_ticket)
);

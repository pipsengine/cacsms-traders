CREATE TABLE IF NOT EXISTS schema_migrations (
  version TEXT PRIMARY KEY,
  applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tenants (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  slug TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL,
  reporting_currency TEXT NOT NULL DEFAULT 'USD',
  timezone TEXT NOT NULL DEFAULT 'Africa/Lagos',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  username TEXT NOT NULL UNIQUE,
  email TEXT UNIQUE,
  password_hash TEXT NOT NULL,
  first_name TEXT NOT NULL,
  middle_name TEXT,
  last_name TEXT NOT NULL,
  display_name TEXT NOT NULL,
  phone TEXT,
  timezone TEXT NOT NULL DEFAULT 'Africa/Lagos',
  preferred_currency TEXT NOT NULL DEFAULT 'USD',
  status TEXT NOT NULL,
  is_platform_admin SMALLINT NOT NULL DEFAULT 0,
  is_system_protected SMALLINT NOT NULL DEFAULT 0,
  last_login_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS roles (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(id),
  name TEXT NOT NULL,
  description TEXT,
  created_at TEXT NOT NULL,
  UNIQUE(tenant_id, name)
);

CREATE TABLE IF NOT EXISTS permissions (
  id TEXT PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS role_permissions (
  role_id TEXT NOT NULL REFERENCES roles(id),
  permission_id TEXT NOT NULL REFERENCES permissions(id),
  PRIMARY KEY(role_id, permission_id)
);

CREATE TABLE IF NOT EXISTS tenant_memberships (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(id),
  user_id TEXT NOT NULL REFERENCES users(id),
  role_id TEXT REFERENCES roles(id),
  status TEXT NOT NULL DEFAULT 'ACTIVE',
  created_at TEXT NOT NULL,
  UNIQUE(tenant_id, user_id)
);

CREATE TABLE IF NOT EXISTS auth_sessions (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id),
  token_hash TEXT NOT NULL UNIQUE,
  expires_at TEXT NOT NULL,
  revoked_at TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_preferences (
  user_id TEXT PRIMARY KEY REFERENCES users(id),
  theme TEXT NOT NULL DEFAULT 'LIGHT',
  compact_tables SMALLINT NOT NULL DEFAULT 0,
  default_tenant_id TEXT,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS system_settings (
  key TEXT PRIMARY KEY,
  value_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tenant_settings (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(id),
  key TEXT NOT NULL,
  value_json TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, key)
);

CREATE TABLE IF NOT EXISTS audit_events (
  id TEXT PRIMARY KEY,
  tenant_id TEXT REFERENCES tenants(id),
  user_id TEXT REFERENCES users(id),
  action TEXT NOT NULL,
  entity_type TEXT,
  entity_id TEXT,
  previous_json TEXT,
  new_json TEXT,
  reason TEXT,
  correlation_id TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS system_events (
  id TEXT PRIMARY KEY,
  tenant_id TEXT REFERENCES tenants(id),
  event_type TEXT NOT NULL,
  entity_type TEXT,
  entity_id TEXT,
  correlation_id TEXT,
  payload_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS security_events (
  id TEXT PRIMARY KEY,
  tenant_id TEXT REFERENCES tenants(id),
  user_id TEXT REFERENCES users(id),
  event_type TEXT NOT NULL,
  ip_address TEXT,
  user_agent TEXT,
  detail_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS worker_heartbeats (
  worker_name TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  last_heartbeat_at TEXT NOT NULL,
  detail_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS trading_accounts (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(id),
  account_name TEXT NOT NULL,
  account_number TEXT,
  broker TEXT,
  server TEXT,
  environment TEXT NOT NULL,
  account_currency TEXT NOT NULL DEFAULT 'USD',
  balance DOUBLE PRECISION NOT NULL DEFAULT 0,
  equity DOUBLE PRECISION NOT NULL DEFAULT 0,
  free_margin DOUBLE PRECISION NOT NULL DEFAULT 0,
  margin DOUBLE PRECISION NOT NULL DEFAULT 0,
  leverage TEXT,
  status TEXT NOT NULL DEFAULT 'ACTIVE',
  connection_type TEXT NOT NULL DEFAULT 'LOCAL_MT5',
  connection_status TEXT NOT NULL DEFAULT 'DISCONNECTED',
  trading_enabled SMALLINT NOT NULL DEFAULT 0,
  autonomous_trading_enabled SMALLINT NOT NULL DEFAULT 0,
  last_synced_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trading_connections (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(id),
  trading_account_id TEXT NOT NULL REFERENCES trading_accounts(id),
  adapter_type TEXT NOT NULL DEFAULT 'LOCAL_MT5',
  terminal_path TEXT,
  server_name TEXT,
  status TEXT NOT NULL DEFAULT 'DISCONNECTED',
  last_heartbeat_at TEXT,
  last_error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS account_risk_profiles (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(id),
  trading_account_id TEXT NOT NULL UNIQUE REFERENCES trading_accounts(id),
  max_open_positions INTEGER NOT NULL DEFAULT 3,
  max_total_risk_pct DOUBLE PRECISION NOT NULL DEFAULT 3.0,
  max_trade_risk_pct DOUBLE PRECISION NOT NULL DEFAULT 1.0,
  max_daily_loss_pct DOUBLE PRECISION,
  max_total_loss_pct DOUBLE PRECISION,
  profit_target_pct DOUBLE PRECISION,
  weekend_holding_allowed SMALLINT NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ctrader_oauth_states (
  state_hash TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(id),
  user_id TEXT NOT NULL REFERENCES users(id),
  environment TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  used_at TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ctrader_connections (
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

CREATE TABLE IF NOT EXISTS reference_currencies (
  code TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  kind TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reference_instruments (
  symbol TEXT PRIMARY KEY,
  base_code TEXT NOT NULL,
  quote_code TEXT NOT NULL,
  enabled SMALLINT NOT NULL DEFAULT 1
);

INSERT INTO reference_currencies(code, name, kind) VALUES
  ('AUD','Australian Dollar','FIAT'),('CAD','Canadian Dollar','FIAT'),
  ('CHF','Swiss Franc','FIAT'),('EUR','Euro','FIAT'),('GBP','Pound Sterling','FIAT'),
  ('JPY','Japanese Yen','FIAT'),('NZD','New Zealand Dollar','FIAT'),
  ('USD','US Dollar','FIAT'),('XAU','Gold','METAL'),('NGN','Nigerian Naira','FIAT')
ON CONFLICT (code) DO NOTHING;

INSERT INTO reference_instruments(symbol, base_code, quote_code, enabled) VALUES
  ('AUDCAD','AUD','CAD',1),('AUDCHF','AUD','CHF',1),('AUDJPY','AUD','JPY',1),
  ('AUDNZD','AUD','NZD',1),('AUDUSD','AUD','USD',1),('CADCHF','CAD','CHF',1),
  ('CADJPY','CAD','JPY',1),('CHFJPY','CHF','JPY',1),('EURAUD','EUR','AUD',1),
  ('EURCAD','EUR','CAD',1),('EURCHF','EUR','CHF',1),('EURGBP','EUR','GBP',1),
  ('EURJPY','EUR','JPY',1),('EURNZD','EUR','NZD',1),('EURUSD','EUR','USD',1),
  ('GBPAUD','GBP','AUD',1),('GBPCAD','GBP','CAD',1),('GBPCHF','GBP','CHF',1),
  ('GBPJPY','GBP','JPY',1),('GBPNZD','GBP','NZD',1),('GBPUSD','GBP','USD',1),
  ('NZDCAD','NZD','CAD',1),('NZDCHF','NZD','CHF',1),('NZDJPY','NZD','JPY',1),
  ('NZDUSD','NZD','USD',1),('USDCAD','USD','CAD',1),('USDCHF','USD','CHF',1),
  ('USDJPY','USD','JPY',1),('XAUUSD','XAU','USD',1)
ON CONFLICT (symbol) DO NOTHING;

CREATE TABLE IF NOT EXISTS mi_candle (
  id BIGSERIAL PRIMARY KEY,
  symbol TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  open_time TEXT NOT NULL,
  close_time TEXT NOT NULL,
  open DOUBLE PRECISION NOT NULL,
  high DOUBLE PRECISION NOT NULL,
  low DOUBLE PRECISION NOT NULL,
  close DOUBLE PRECISION NOT NULL,
  tick_volume INTEGER NOT NULL DEFAULT 0,
  spread DOUBLE PRECISION NOT NULL DEFAULT 0,
  source TEXT NOT NULL DEFAULT 'MT5',
  is_closed SMALLINT NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP::text),
  UNIQUE(symbol, timeframe, open_time)
);

CREATE TABLE IF NOT EXISTS mi_data_quality (
  id BIGSERIAL PRIMARY KEY,
  symbol TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  state TEXT NOT NULL,
  last_closed_at TEXT,
  age_seconds DOUBLE PRECISION,
  missing_bars INTEGER NOT NULL DEFAULT 0,
  reason TEXT,
  updated_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP::text),
  UNIQUE(symbol, timeframe)
);

CREATE TABLE IF NOT EXISTS mi_strength_snapshot (
  id BIGSERIAL PRIMARY KEY,
  currency TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  as_of TEXT NOT NULL,
  value DOUBLE PRECISION NOT NULL,
  slope DOUBLE PRECISION NOT NULL DEFAULT 0,
  velocity DOUBLE PRECISION NOT NULL DEFAULT 0,
  acceleration DOUBLE PRECISION NOT NULL DEFAULT 0,
  persistence DOUBLE PRECISION NOT NULL DEFAULT 0,
  confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
  sample_count INTEGER NOT NULL DEFAULT 0,
  quality TEXT NOT NULL DEFAULT 'FRESH',
  score DOUBLE PRECISION,
  created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP::text),
  UNIQUE(currency, timeframe, as_of)
);

CREATE TABLE IF NOT EXISTS mi_relationship_snapshot (
  id BIGSERIAL PRIMARY KEY,
  pair TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  as_of TEXT NOT NULL,
  base_value DOUBLE PRECISION NOT NULL,
  quote_value DOUBLE PRECISION NOT NULL,
  gap DOUBLE PRECISION NOT NULL,
  abs_gap DOUBLE PRECISION NOT NULL,
  gap_velocity DOUBLE PRECISION NOT NULL DEFAULT 0,
  gap_acceleration DOUBLE PRECISION NOT NULL DEFAULT 0,
  persistence DOUBLE PRECISION NOT NULL DEFAULT 0,
  state TEXT NOT NULL,
  confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
  inspection_priority TEXT NOT NULL DEFAULT 'NORMAL',
  reason_codes TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP::text),
  UNIQUE(pair, timeframe, as_of)
);

CREATE TABLE IF NOT EXISTS mi_calculation_run (
  id TEXT PRIMARY KEY,
  tenant_id TEXT,
  timeframe TEXT NOT NULL,
  started_at TEXT NOT NULL,
  completed_at TEXT,
  status TEXT NOT NULL,
  pair_count INTEGER NOT NULL DEFAULT 0,
  currency_count INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS mi_ingestion_checkpoint (
  symbol TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  last_open_time TEXT,
  last_close_time TEXT,
  last_sync_at TEXT,
  status TEXT NOT NULL DEFAULT 'PENDING',
  error TEXT,
  PRIMARY KEY(symbol, timeframe)
);

CREATE TABLE IF NOT EXISTS mi_pair_intel_snapshot (
  id BIGSERIAL PRIMARY KEY,
  tenant_id TEXT NOT NULL DEFAULT '',
  trading_account_id TEXT NOT NULL DEFAULT '',
  pair TEXT NOT NULL,
  base_currency TEXT NOT NULL,
  quote_currency TEXT NOT NULL,
  as_of TEXT NOT NULL,
  base_strength DOUBLE PRECISION NOT NULL,
  quote_strength DOUBLE PRECISION NOT NULL,
  differential DOUBLE PRECISION NOT NULL,
  abs_differential DOUBLE PRECISION NOT NULL,
  relationship TEXT NOT NULL,
  dynamics TEXT NOT NULL,
  alignment TEXT NOT NULL,
  aligned_count INTEGER NOT NULL DEFAULT 0,
  timeframe_count INTEGER NOT NULL DEFAULT 0,
  tf_differentials_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP::text),
  UNIQUE(tenant_id, trading_account_id, pair, as_of)
);

CREATE TABLE IF NOT EXISTS mi_scanner_snapshot (
  id BIGSERIAL PRIMARY KEY,
  tenant_id TEXT NOT NULL DEFAULT '',
  trading_account_id TEXT NOT NULL DEFAULT '',
  cycle_id INTEGER NOT NULL,
  as_of TEXT NOT NULL,
  symbol TEXT NOT NULL,
  status TEXT NOT NULL,
  score INTEGER NOT NULL,
  price DOUBLE PRECISION,
  change_24h_pct DOUBLE PRECISION,
  structure TEXT,
  channel TEXT,
  volatility TEXT,
  differential DOUBLE PRECISION,
  reasons_json TEXT NOT NULL DEFAULT '[]',
  details_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP::text),
  UNIQUE(tenant_id, trading_account_id, symbol, as_of)
);

CREATE TABLE IF NOT EXISTS mi_range_structure_snapshot (
  id BIGSERIAL PRIMARY KEY,
  tenant_id TEXT NOT NULL DEFAULT '',
  trading_account_id TEXT NOT NULL DEFAULT '',
  cycle_id INTEGER NOT NULL,
  as_of TEXT NOT NULL,
  symbol TEXT NOT NULL,
  regime TEXT NOT NULL,
  range_state TEXT,
  range_high DOUBLE PRECISION,
  range_low DOUBLE PRECISION,
  position DOUBLE PRECISION,
  developing_fractal TEXT,
  evidence_score INTEGER,
  quality INTEGER,
  hypothesis TEXT,
  decision TEXT,
  details_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP::text),
  UNIQUE(tenant_id, trading_account_id, symbol, as_of)
);

CREATE TABLE IF NOT EXISTS mi_structure_overview_snapshot (
  id BIGSERIAL PRIMARY KEY,
  tenant_id TEXT NOT NULL DEFAULT '',
  trading_account_id TEXT NOT NULL DEFAULT '',
  cycle_id INTEGER NOT NULL,
  as_of TEXT NOT NULL,
  symbol TEXT NOT NULL,
  regime_w TEXT,
  regime_d1 TEXT,
  regime_h8 TEXT,
  regime_h1 TEXT,
  current_state TEXT,
  alignment_score INTEGER,
  details_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP::text),
  UNIQUE(tenant_id, trading_account_id, symbol, as_of)
);

CREATE TABLE IF NOT EXISTS mi_h8_bos_btl_snapshot (
  id BIGSERIAL PRIMARY KEY,
  tenant_id TEXT NOT NULL DEFAULT '',
  trading_account_id TEXT NOT NULL DEFAULT '',
  cycle_id INTEGER NOT NULL,
  as_of TEXT NOT NULL,
  symbol TEXT NOT NULL,
  event_kind TEXT NOT NULL,
  confirmed SMALLINT NOT NULL DEFAULT 0,
  direction TEXT,
  event_at TEXT,
  bos_level DOUBLE PRECISION,
  btl_level DOUBLE PRECISION,
  break_strength_atr DOUBLE PRECISION,
  retest_status TEXT,
  h1_status TEXT,
  m30_status TEXT,
  analysis_id TEXT,
  details_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP::text),
  UNIQUE(tenant_id, trading_account_id, symbol, as_of)
);

CREATE TABLE IF NOT EXISTS mi_trend_structure_snapshot (
  id BIGSERIAL PRIMARY KEY,
  tenant_id TEXT NOT NULL DEFAULT '',
  trading_account_id TEXT NOT NULL DEFAULT '',
  cycle_id INTEGER NOT NULL,
  as_of TEXT NOT NULL,
  symbol TEXT NOT NULL,
  direction TEXT,
  trend_state TEXT NOT NULL,
  strength INTEGER NOT NULL,
  age_weeks DOUBLE PRECISION,
  cell_w TEXT,
  cell_d1 TEXT,
  cell_h8 TEXT,
  cell_h1 TEXT,
  setup TEXT NOT NULL,
  pullback_depth_pct DOUBLE PRECISION,
  analysis_close_at TEXT,
  details_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP::text),
  UNIQUE(tenant_id, trading_account_id, symbol, as_of)
);

CREATE INDEX IF NOT EXISTS idx_membership_tenant ON tenant_memberships(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_membership_user ON tenant_memberships(user_id, status);
CREATE INDEX IF NOT EXISTS idx_accounts_tenant ON trading_accounts(tenant_id, environment, status);
CREATE INDEX IF NOT EXISTS idx_connections_account ON trading_connections(trading_account_id, status);
CREATE INDEX IF NOT EXISTS idx_audit_tenant_created ON audit_events(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_tenant_created ON system_events(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_user_expiry ON auth_sessions(user_id, expires_at);
CREATE INDEX IF NOT EXISTS ix_mi_candle_lookup ON mi_candle(symbol, timeframe, open_time DESC);
CREATE INDEX IF NOT EXISTS ix_mi_strength_latest ON mi_strength_snapshot(currency, timeframe, as_of DESC);
CREATE INDEX IF NOT EXISTS ix_mi_strength_tf_asof ON mi_strength_snapshot(timeframe, as_of DESC);
CREATE INDEX IF NOT EXISTS ix_mi_relationship_latest ON mi_relationship_snapshot(pair, timeframe, as_of DESC);
CREATE INDEX IF NOT EXISTS ix_mi_relationship_state ON mi_relationship_snapshot(state, inspection_priority, as_of DESC);
CREATE INDEX IF NOT EXISTS ix_mi_pair_intel_scope ON mi_pair_intel_snapshot(tenant_id, trading_account_id, pair, as_of DESC);
CREATE INDEX IF NOT EXISTS ix_mi_pair_intel_asof ON mi_pair_intel_snapshot(tenant_id, trading_account_id, as_of DESC);
CREATE INDEX IF NOT EXISTS ix_mi_scanner_scope ON mi_scanner_snapshot(tenant_id, trading_account_id, as_of DESC);
CREATE INDEX IF NOT EXISTS ix_mi_scanner_symbol ON mi_scanner_snapshot(tenant_id, trading_account_id, symbol, as_of DESC);
CREATE INDEX IF NOT EXISTS ix_mi_range_scope ON mi_range_structure_snapshot(tenant_id, trading_account_id, as_of DESC);
CREATE INDEX IF NOT EXISTS ix_mi_structure_overview_scope ON mi_structure_overview_snapshot(tenant_id, trading_account_id, as_of DESC);
CREATE INDEX IF NOT EXISTS ix_mi_h8_bos_btl_scope ON mi_h8_bos_btl_snapshot(tenant_id, trading_account_id, as_of DESC);
CREATE INDEX IF NOT EXISTS ix_mi_trend_structure_scope ON mi_trend_structure_snapshot(tenant_id, trading_account_id, as_of DESC);

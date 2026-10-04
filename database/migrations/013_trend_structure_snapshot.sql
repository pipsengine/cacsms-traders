-- Trend Structure intelligence per tenant / trading account (closed-bar view only, never trade direction).
-- Rows are evaluated on the last closed analysis-timeframe bar; live-quote (developing) states are not stored.
CREATE TABLE IF NOT EXISTS mi_trend_structure_snapshot(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id TEXT NOT NULL DEFAULT '',
  trading_account_id TEXT NOT NULL DEFAULT '',
  cycle_id INTEGER NOT NULL,
  as_of TEXT NOT NULL,
  symbol TEXT NOT NULL,
  direction TEXT,
  trend_state TEXT NOT NULL,
  strength INTEGER NOT NULL,
  age_weeks REAL,
  cell_w TEXT,
  cell_d1 TEXT,
  cell_h8 TEXT,
  cell_h1 TEXT,
  setup TEXT NOT NULL,
  pullback_depth_pct REAL,
  analysis_close_at TEXT,
  details_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(tenant_id, trading_account_id, symbol, as_of)
);
CREATE INDEX IF NOT EXISTS ix_mi_trend_structure_scope
  ON mi_trend_structure_snapshot(tenant_id, trading_account_id, as_of DESC);

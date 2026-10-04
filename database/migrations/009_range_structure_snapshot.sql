-- Weekly Range Structure intelligence per tenant / trading account (evidence states only, never trade direction).
-- Developing fractals are stored as evidence (developing_fractal), never as confirmed fractals.
CREATE TABLE IF NOT EXISTS mi_range_structure_snapshot(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id TEXT NOT NULL DEFAULT '',
  trading_account_id TEXT NOT NULL DEFAULT '',
  cycle_id INTEGER NOT NULL,
  as_of TEXT NOT NULL,
  symbol TEXT NOT NULL,
  regime TEXT NOT NULL,
  range_state TEXT,
  range_high REAL,
  range_low REAL,
  position REAL,
  developing_fractal TEXT,
  evidence_score INTEGER,
  quality INTEGER,
  hypothesis TEXT,
  decision TEXT,
  details_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(tenant_id, trading_account_id, symbol, as_of)
);
CREATE INDEX IF NOT EXISTS ix_mi_range_scope
  ON mi_range_structure_snapshot(tenant_id, trading_account_id, as_of DESC);

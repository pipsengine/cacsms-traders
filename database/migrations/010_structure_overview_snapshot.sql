-- Multi-timeframe structure overview per tenant / trading account (closed-bar regimes, never trade direction).
CREATE TABLE IF NOT EXISTS mi_structure_overview_snapshot(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
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
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(tenant_id, trading_account_id, symbol, as_of)
);
CREATE INDEX IF NOT EXISTS ix_mi_structure_overview_scope
  ON mi_structure_overview_snapshot(tenant_id, trading_account_id, as_of DESC);

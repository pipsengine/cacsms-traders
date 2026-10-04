-- Market Scanner classification per tenant / trading account (inspection priority only, never trade direction).
CREATE TABLE IF NOT EXISTS mi_scanner_snapshot(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id TEXT NOT NULL DEFAULT '',
  trading_account_id TEXT NOT NULL DEFAULT '',
  cycle_id INTEGER NOT NULL,
  as_of TEXT NOT NULL,
  symbol TEXT NOT NULL,
  status TEXT NOT NULL,
  score INTEGER NOT NULL,
  price REAL,
  change_24h_pct REAL,
  structure TEXT,
  channel TEXT,
  volatility TEXT,
  differential REAL,
  reasons_json TEXT NOT NULL DEFAULT '[]',
  details_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(tenant_id, trading_account_id, symbol, as_of)
);
CREATE INDEX IF NOT EXISTS ix_mi_scanner_scope
  ON mi_scanner_snapshot(tenant_id, trading_account_id, as_of DESC);
CREATE INDEX IF NOT EXISTS ix_mi_scanner_symbol
  ON mi_scanner_snapshot(tenant_id, trading_account_id, symbol, as_of DESC);

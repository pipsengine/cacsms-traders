-- Pair Relationship intelligence persisted per tenant / trading account for Market Scanner and the
-- autonomous pipeline. Analysis only: rows describe strength differentials, never trade direction.
CREATE TABLE IF NOT EXISTS mi_pair_intel_snapshot(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id TEXT NOT NULL DEFAULT '',
  trading_account_id TEXT NOT NULL DEFAULT '',
  pair TEXT NOT NULL,
  base_currency TEXT NOT NULL,
  quote_currency TEXT NOT NULL,
  as_of TEXT NOT NULL,
  base_strength REAL NOT NULL,
  quote_strength REAL NOT NULL,
  differential REAL NOT NULL,
  abs_differential REAL NOT NULL,
  relationship TEXT NOT NULL,
  dynamics TEXT NOT NULL,
  alignment TEXT NOT NULL,
  aligned_count INTEGER NOT NULL DEFAULT 0,
  timeframe_count INTEGER NOT NULL DEFAULT 0,
  tf_differentials_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(tenant_id, trading_account_id, pair, as_of)
);
CREATE INDEX IF NOT EXISTS ix_mi_pair_intel_scope
  ON mi_pair_intel_snapshot(tenant_id, trading_account_id, pair, as_of DESC);
CREATE INDEX IF NOT EXISTS ix_mi_pair_intel_asof
  ON mi_pair_intel_snapshot(tenant_id, trading_account_id, as_of DESC);

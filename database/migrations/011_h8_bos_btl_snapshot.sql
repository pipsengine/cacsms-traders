-- H8 BOS & BTL structural break intelligence per tenant / trading account (closed-bar events, never trade direction).
-- confirmed = 1 only for closed-bar BOS / BTL / BOS + BTL events; DEVELOPING and MONITORING rows carry confirmed = 0.
CREATE TABLE IF NOT EXISTS mi_h8_bos_btl_snapshot(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id TEXT NOT NULL DEFAULT '',
  trading_account_id TEXT NOT NULL DEFAULT '',
  cycle_id INTEGER NOT NULL,
  as_of TEXT NOT NULL,
  symbol TEXT NOT NULL,
  event_kind TEXT NOT NULL,
  confirmed INTEGER NOT NULL DEFAULT 0,
  direction TEXT,
  event_at TEXT,
  bos_level REAL,
  btl_level REAL,
  break_strength_atr REAL,
  retest_status TEXT,
  h1_status TEXT,
  m30_status TEXT,
  analysis_id TEXT,
  details_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(tenant_id, trading_account_id, symbol, as_of)
);
CREATE INDEX IF NOT EXISTS ix_mi_h8_bos_btl_scope
  ON mi_h8_bos_btl_snapshot(tenant_id, trading_account_id, as_of DESC);

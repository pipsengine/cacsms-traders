-- Unified executable book for strategy setups and AI Market Outlook campaigns.
CREATE TABLE IF NOT EXISTS ce_opportunity (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  trading_account_id TEXT NOT NULL DEFAULT '',
  symbol TEXT NOT NULL,
  source_mode TEXT NOT NULL,
  strategy_type TEXT,
  outlook_horizon TEXT,
  analysis_id TEXT NOT NULL,
  scenario_id TEXT,
  direction TEXT NOT NULL,
  evidence_score REAL,
  entry_zone REAL,
  stop_loss REAL,
  targets_json TEXT NOT NULL DEFAULT '[]',
  invalidation REAL,
  confirmation_requirements TEXT,
  lifecycle_status TEXT NOT NULL,
  stage TEXT NOT NULL,
  conflict TEXT,
  linked_json TEXT NOT NULL DEFAULT '[]',
  campaign_id TEXT,
  next_action TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ce_opportunity_scope ON ce_opportunity(tenant_id, trading_account_id, source_mode, updated_at DESC);

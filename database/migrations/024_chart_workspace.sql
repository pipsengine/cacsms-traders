-- Advanced Chart Analysis: per-user workspace, saved analyses, and manual opportunity drafts.
CREATE TABLE IF NOT EXISTS chart_workspaces (
  tenant_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  symbol TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  indicators TEXT NOT NULL,
  layers TEXT NOT NULL,
  drawings TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, user_id, symbol, timeframe)
);
CREATE TABLE IF NOT EXISTS chart_analyses (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  symbol TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  title TEXT NOT NULL,
  notes TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chart_analyses_scope ON chart_analyses(tenant_id, user_id, symbol, created_at DESC);
CREATE TABLE IF NOT EXISTS chart_opportunity_drafts (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  account_id TEXT NOT NULL,
  symbol TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  direction TEXT NOT NULL,
  strategy TEXT NOT NULL,
  notes TEXT NOT NULL,
  analysis_id TEXT,
  created_at TEXT NOT NULL,
  status TEXT NOT NULL,
  ae_opportunity_id TEXT
);

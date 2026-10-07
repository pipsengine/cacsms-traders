-- AI Market Outlook (Daily): autonomous daily cycle, immutable predictions, intraday revisions, outcomes, calibration.
-- Published symbol outlooks are append-only; monitoring and evaluation write to separate tables.
CREATE TABLE IF NOT EXISTS ai_outlook_run(
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL DEFAULT '',
  trading_account_id TEXT NOT NULL DEFAULT '',
  analysis_date TEXT NOT NULL,
  origin TEXT NOT NULL DEFAULT 'LIVE',
  state TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  snapshot_id TEXT,
  close_at TEXT NOT NULL,
  engine_version TEXT NOT NULL,
  symbols_total INTEGER NOT NULL DEFAULT 0,
  symbols_published INTEGER NOT NULL DEFAULT 0,
  symbols_failed INTEGER NOT NULL DEFAULT 0,
  symbols_insufficient INTEGER NOT NULL DEFAULT 0,
  qualified INTEGER NOT NULL DEFAULT 0,
  started_at TEXT,
  published_at TEXT,
  monitored_at TEXT,
  evaluated_at TEXT,
  next_retry_at TEXT,
  error TEXT,
  log_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, trading_account_id, analysis_date, origin)
);
CREATE INDEX IF NOT EXISTS ix_ai_outlook_run_scope ON ai_outlook_run(tenant_id, trading_account_id, analysis_date DESC);

CREATE TABLE IF NOT EXISTS ai_outlook_snapshot(
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  analysis_date TEXT NOT NULL,
  cutoff_at TEXT NOT NULL,
  frozen_at TEXT NOT NULL,
  manifest_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ai_outlook_snapshot_run ON ai_outlook_snapshot(run_id);

CREATE TABLE IF NOT EXISTS ai_outlook_symbol(
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL DEFAULT '',
  trading_account_id TEXT NOT NULL DEFAULT '',
  analysis_date TEXT NOT NULL,
  origin TEXT NOT NULL DEFAULT 'LIVE',
  symbol TEXT NOT NULL,
  status TEXT NOT NULL,
  qualified INTEGER NOT NULL DEFAULT 0,
  opportunity_rank INTEGER,
  opportunity_score REAL,
  direction TEXT,
  confidence REAL,
  regime TEXT,
  engine_version TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(run_id, symbol)
);
CREATE INDEX IF NOT EXISTS ix_ai_outlook_symbol_scope ON ai_outlook_symbol(tenant_id, trading_account_id, symbol, analysis_date DESC);
CREATE TRIGGER IF NOT EXISTS ai_outlook_symbol_immutable BEFORE UPDATE ON ai_outlook_symbol
BEGIN
  SELECT RAISE(ABORT, 'published outlooks are immutable');
END;

CREATE TABLE IF NOT EXISTS ai_outlook_revision(
  id TEXT PRIMARY KEY,
  outlook_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  symbol TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  status TEXT NOT NULL,
  previous_status TEXT,
  price REAL,
  detail_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ai_outlook_revision_outlook ON ai_outlook_revision(outlook_id, observed_at DESC);

CREATE TABLE IF NOT EXISTS ai_outlook_evaluation(
  outlook_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL DEFAULT '',
  trading_account_id TEXT NOT NULL DEFAULT '',
  symbol TEXT NOT NULL,
  analysis_date TEXT NOT NULL,
  evaluated_date TEXT NOT NULL,
  direction TEXT,
  confidence REAL,
  qualified INTEGER NOT NULL DEFAULT 0,
  outcome TEXT NOT NULL,
  scenario_result TEXT NOT NULL,
  direction_correct INTEGER,
  target1_hit INTEGER NOT NULL DEFAULT 0,
  target2_hit INTEGER NOT NULL DEFAULT 0,
  invalidated INTEGER NOT NULL DEFAULT 0,
  erz_touched INTEGER NOT NULL DEFAULT 0,
  move_pct REAL,
  detail_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ai_outlook_eval_scope ON ai_outlook_evaluation(tenant_id, trading_account_id, symbol, analysis_date DESC);

CREATE TABLE IF NOT EXISTS ai_outlook_calibration(
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL DEFAULT '',
  trading_account_id TEXT NOT NULL DEFAULT '',
  table_json TEXT NOT NULL,
  samples INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_outlook_lock(
  name TEXT PRIMARY KEY,
  owner TEXT NOT NULL,
  expires_at TEXT NOT NULL
);

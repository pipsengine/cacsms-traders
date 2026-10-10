-- Multi-horizon AI Market Outlook. Daily rows stay on horizon DAILY.
-- Weekly, monthly and H8 runs keep their own broker close key in analysis_date (prefix|timestamp).
ALTER TABLE ai_outlook_run ADD COLUMN horizon TEXT NOT NULL DEFAULT 'DAILY';
ALTER TABLE ai_outlook_symbol ADD COLUMN horizon TEXT NOT NULL DEFAULT 'DAILY';
CREATE INDEX IF NOT EXISTS ix_ai_outlook_run_horizon ON ai_outlook_run(tenant_id, trading_account_id, horizon, close_at DESC);
CREATE INDEX IF NOT EXISTS ix_ai_outlook_symbol_horizon ON ai_outlook_symbol(tenant_id, trading_account_id, horizon, symbol, analysis_date DESC);

CREATE TABLE IF NOT EXISTS ai_outlook_handoff(
  id TEXT PRIMARY KEY,
  outlook_id TEXT NOT NULL UNIQUE,
  run_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL DEFAULT '',
  trading_account_id TEXT NOT NULL DEFAULT '',
  symbol TEXT NOT NULL,
  horizon TEXT NOT NULL,
  close_at TEXT NOT NULL,
  lifecycle TEXT NOT NULL,
  execution_ref TEXT,
  evidence_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ai_outlook_handoff_scope ON ai_outlook_handoff(tenant_id, trading_account_id, symbol, close_at DESC);

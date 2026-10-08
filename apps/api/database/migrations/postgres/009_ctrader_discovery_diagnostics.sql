ALTER TABLE ctrader_connections ADD COLUMN IF NOT EXISTS last_diagnostic_json TEXT;
ALTER TABLE ctrader_connections ADD COLUMN IF NOT EXISTS last_attempt_at TEXT;

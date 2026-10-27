-- Default platform mode: live autonomous execution (AI outlook + strategy), not analysis-only shadow.
UPDATE system_settings SET value_json = '"LIVE_AUTONOMOUS"', updated_at = datetime('now') WHERE key = 'system.mode';

-- 0–100 normalized strength score alongside the raw CSM value (sparklines, history, ML features)
ALTER TABLE mi_strength_snapshot ADD COLUMN score REAL;
CREATE INDEX IF NOT EXISTS ix_mi_strength_tf_asof ON mi_strength_snapshot(timeframe, as_of DESC);

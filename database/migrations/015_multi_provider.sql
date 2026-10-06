CREATE TABLE IF NOT EXISTS mi_provider_candle (
 symbol TEXT NOT NULL, timeframe TEXT NOT NULL, open_time TEXT NOT NULL,
 close_time TEXT NOT NULL, open REAL NOT NULL, high REAL NOT NULL,
 low REAL NOT NULL, close REAL NOT NULL, tick_volume INTEGER NOT NULL DEFAULT 0,
 spread REAL, source TEXT NOT NULL, account_id TEXT NOT NULL DEFAULT '', is_closed INTEGER NOT NULL DEFAULT 1,
 PRIMARY KEY (source,account_id,symbol,timeframe,open_time)
);
INSERT INTO mi_provider_candle SELECT symbol,timeframe,open_time,close_time,open,high,low,close,tick_volume,spread,LOWER(source),'',is_closed FROM mi_candle WHERE is_closed=1 ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS mi_provider_snapshot (
 id TEXT PRIMARY KEY, provider TEXT NOT NULL, account_id TEXT NOT NULL DEFAULT '',
 started_at TEXT NOT NULL, finalized_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_provider_snapshot_active ON mi_provider_snapshot ((1)) WHERE finalized_at IS NULL;
CREATE TABLE IF NOT EXISTS mi_provider_health (provider TEXT PRIMARY KEY, state_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS mi_analysis_provenance (
 kind TEXT NOT NULL, as_of TEXT NOT NULL, snapshot_id TEXT NOT NULL REFERENCES mi_provider_snapshot(id),
 PRIMARY KEY(kind,as_of)
);
CREATE TABLE IF NOT EXISTS execution_provider_binding (
 campaign_id TEXT PRIMARY KEY, provider TEXT NOT NULL, account_id TEXT NOT NULL,
 created_at TEXT NOT NULL
);

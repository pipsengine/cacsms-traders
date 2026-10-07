-- Email alert notifications: per-tenant alert settings, recipients, normalized alert events (deduplicated),
-- per-recipient deliveries with bounded retries, and re-arm state for edge-triggered alerts (touch, TiT).
CREATE TABLE IF NOT EXISTS notification_settings (
 tenant_id TEXT PRIMARY KEY, email_enabled INTEGER NOT NULL DEFAULT 1, alert_types_json TEXT NOT NULL DEFAULT '{}',
 timeframes_json TEXT NOT NULL DEFAULT '[]', symbols_json TEXT NOT NULL DEFAULT '[]', xauusd_enabled INTEGER NOT NULL DEFAULT 1,
 touch_rearm_bars INTEGER NOT NULL DEFAULT 2, cooldown_minutes INTEGER NOT NULL DEFAULT 0, max_event_age_bars INTEGER NOT NULL DEFAULT 2,
 max_attempts INTEGER NOT NULL DEFAULT 4, updated_by TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notification_recipients (
 id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, email TEXT NOT NULL, name TEXT, enabled INTEGER NOT NULL DEFAULT 1,
 alert_types TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id, email)
);
CREATE INDEX IF NOT EXISTS ix_notification_recipients_tenant ON notification_recipients(tenant_id, enabled);
CREATE TABLE IF NOT EXISTS alert_events (
 id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, trading_account_id TEXT NOT NULL DEFAULT '', event_type TEXT NOT NULL,
 symbol TEXT NOT NULL, timeframe TEXT, direction TEXT, provider TEXT, event_time TEXT NOT NULL, detected_at TEXT NOT NULL,
 price DOUBLE PRECISION, level DOUBLE PRECISION, channel_id TEXT, structure_id TEXT, tit_level TEXT, confidence DOUBLE PRECISION,
 metadata_json TEXT NOT NULL DEFAULT '{}', status TEXT NOT NULL, status_reason TEXT, deduplication_key TEXT NOT NULL,
 history_json TEXT NOT NULL DEFAULT '[]', queued_at TEXT, sent_at TEXT, attempt_count INTEGER NOT NULL DEFAULT 0,
 last_attempt_at TEXT, failure_reason TEXT, updated_at TEXT NOT NULL, UNIQUE(tenant_id, deduplication_key)
);
CREATE INDEX IF NOT EXISTS ix_alert_events_tenant_time ON alert_events(tenant_id, event_time DESC);
CREATE INDEX IF NOT EXISTS ix_alert_events_type ON alert_events(event_type);
CREATE INDEX IF NOT EXISTS ix_alert_events_symbol ON alert_events(symbol);
CREATE INDEX IF NOT EXISTS ix_alert_events_event_time ON alert_events(event_time);
CREATE INDEX IF NOT EXISTS ix_alert_events_status ON alert_events(status);
CREATE INDEX IF NOT EXISTS ix_alert_events_dedup ON alert_events(deduplication_key);
CREATE TABLE IF NOT EXISTS notification_deliveries (
 id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, alert_event_id TEXT, recipient_id TEXT, recipient_email TEXT NOT NULL,
 kind TEXT NOT NULL DEFAULT 'ALERT', channel TEXT NOT NULL DEFAULT 'EMAIL', status TEXT NOT NULL, subject TEXT,
 attempt_count INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 4, next_attempt_at TEXT, queued_at TEXT,
 last_attempt_at TEXT, sent_at TEXT, failure_reason TEXT, error_kind TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 UNIQUE(alert_event_id, recipient_id)
);
CREATE INDEX IF NOT EXISTS ix_notification_deliveries_due ON notification_deliveries(status, next_attempt_at);
CREATE INDEX IF NOT EXISTS ix_notification_deliveries_tenant ON notification_deliveries(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_notification_deliveries_event ON notification_deliveries(alert_event_id);
CREATE TABLE IF NOT EXISTS alert_rearm_state (
 tenant_id TEXT NOT NULL, rearm_key TEXT NOT NULL, armed INTEGER NOT NULL DEFAULT 1, last_fired_at TEXT, last_seen_at TEXT,
 updated_at TEXT NOT NULL, PRIMARY KEY(tenant_id, rearm_key)
);

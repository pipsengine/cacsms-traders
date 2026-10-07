-- Autonomous Trading Engine: persistent stage state machine. Cycles, per-stage live state, per-symbol progress,
-- autonomously created opportunities, channel lifecycles, an append-only transition audit trail, worker heartbeats
-- and a lease lock so a single worker advances the machine at a time.
CREATE TABLE IF NOT EXISTS ae_cycle (
 id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, trading_account_id TEXT NOT NULL DEFAULT '', origin TEXT NOT NULL,
 status TEXT NOT NULL, operating_mode TEXT NOT NULL, safety_status TEXT NOT NULL, provider TEXT, snapshot_id TEXT,
 scanner_cycle_id INTEGER, data_as_of TEXT, owner TEXT, counts_json TEXT NOT NULL DEFAULT '{}',
 safety_json TEXT NOT NULL DEFAULT '{}', error TEXT, started_at TEXT NOT NULL, completed_at TEXT, duration_ms INTEGER
);
CREATE INDEX IF NOT EXISTS ix_ae_cycle_scope ON ae_cycle(tenant_id, trading_account_id, started_at DESC);
CREATE INDEX IF NOT EXISTS ix_ae_cycle_status ON ae_cycle(status, started_at DESC);
CREATE TABLE IF NOT EXISTS ae_stage_state (
 tenant_id TEXT NOT NULL, trading_account_id TEXT NOT NULL DEFAULT '', stage TEXT NOT NULL, status TEXT NOT NULL,
 current_operation TEXT, next_operation TEXT, processed INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 0,
 waiting INTEGER NOT NULL DEFAULT 0, errors INTEGER NOT NULL DEFAULT 0, metrics_json TEXT NOT NULL DEFAULT '{}',
 blockers_json TEXT NOT NULL DEFAULT '[]', detail_json TEXT NOT NULL DEFAULT '{}', provider TEXT, cycle_id TEXT,
 last_update TEXT NOT NULL, last_success_at TEXT, PRIMARY KEY(tenant_id, trading_account_id, stage)
);
CREATE TABLE IF NOT EXISTS ae_symbol_state (
 tenant_id TEXT NOT NULL, trading_account_id TEXT NOT NULL DEFAULT '', symbol TEXT NOT NULL, stage TEXT NOT NULL,
 state TEXT NOT NULL, reason_code TEXT, provider TEXT, data_as_of TEXT, evidence_json TEXT NOT NULL DEFAULT '{}',
 updated_at TEXT NOT NULL, PRIMARY KEY(tenant_id, trading_account_id, symbol)
);
CREATE TABLE IF NOT EXISTS ae_opportunity (
 id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, trading_account_id TEXT NOT NULL DEFAULT '', family_key TEXT NOT NULL,
 symbol TEXT NOT NULL, direction TEXT NOT NULL, opp_type TEXT NOT NULL, tit_level TEXT, parent_tf TEXT, trigger_tf TEXT,
 stage TEXT NOT NULL, state TEXT NOT NULL, status TEXT NOT NULL, outcome TEXT, entry_lo DOUBLE PRECISION,
 entry_hi DOUBLE PRECISION, invalidation DOUBLE PRECISION, target_1 DOUBLE PRECISION, target_2 DOUBLE PRECISION,
 current_price DOUBLE PRECISION, price_at TEXT, confidence DOUBLE PRECISION, quality DOUBLE PRECISION,
 reward_risk DOUBLE PRECISION, next_condition TEXT, reason_code TEXT, provider TEXT, snapshot_id TEXT,
 evidence_json TEXT NOT NULL DEFAULT '{}', blockers_json TEXT NOT NULL DEFAULT '[]', origin_at TEXT NOT NULL,
 stage_entered_at TEXT NOT NULL, evaluated_through TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 closed_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_ae_opportunity_active_family ON ae_opportunity(tenant_id, trading_account_id, family_key)
 WHERE status = 'ACTIVE';
CREATE INDEX IF NOT EXISTS ix_ae_opportunity_scope ON ae_opportunity(tenant_id, trading_account_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS ix_ae_opportunity_family ON ae_opportunity(tenant_id, trading_account_id, family_key, closed_at);
CREATE INDEX IF NOT EXISTS ix_ae_opportunity_symbol ON ae_opportunity(symbol);
CREATE TABLE IF NOT EXISTS ae_channel (
 id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, trading_account_id TEXT NOT NULL DEFAULT '', symbol TEXT NOT NULL,
 timeframe TEXT NOT NULL, status TEXT NOT NULL, state TEXT NOT NULL, direction TEXT, validity TEXT,
 upper DOUBLE PRECISION, mid DOUBLE PRECISION, lower DOUBLE PRECISION, width DOUBLE PRECISION,
 width_atr DOUBLE PRECISION, atr DOUBLE PRECISION, position DOUBLE PRECISION, touches_upper INTEGER NOT NULL DEFAULT 0,
 touches_lower INTEGER NOT NULL DEFAULT 0, quality DOUBLE PRECISION, age_bars INTEGER, erz_lo DOUBLE PRECISION,
 erz_hi DOUBLE PRECISION, break_direction TEXT, break_level DOUBLE PRECISION, break_at TEXT, retest_at TEXT,
 continuation_at TEXT, last_touch_at TEXT, last_touch_side TEXT, state_entered_at TEXT, started_at TEXT NOT NULL,
 last_bar_at TEXT, closed_at TEXT, provider TEXT, lines_json TEXT NOT NULL DEFAULT '{}', updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_ae_channel_active ON ae_channel(tenant_id, trading_account_id, symbol, timeframe)
 WHERE status = 'ACTIVE';
CREATE INDEX IF NOT EXISTS ix_ae_channel_scope ON ae_channel(tenant_id, trading_account_id, status, updated_at DESC);
CREATE TABLE IF NOT EXISTS ae_transition (
 id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, trading_account_id TEXT NOT NULL DEFAULT '', entity_type TEXT NOT NULL,
 entity_id TEXT NOT NULL, symbol TEXT, timeframe TEXT, from_stage TEXT, from_state TEXT, to_stage TEXT NOT NULL,
 to_state TEXT NOT NULL, reason_code TEXT NOT NULL, detail TEXT, evidence_json TEXT NOT NULL DEFAULT '{}', provider TEXT,
 evidence_at TEXT NOT NULL, cycle_id TEXT, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ae_transition_scope ON ae_transition(tenant_id, trading_account_id, evidence_at DESC);
CREATE INDEX IF NOT EXISTS ix_ae_transition_entity ON ae_transition(entity_id, evidence_at);
CREATE INDEX IF NOT EXISTS ix_ae_transition_state ON ae_transition(tenant_id, trading_account_id, entity_type, to_state, evidence_at);
CREATE OR REPLACE FUNCTION ae_transition_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'autonomous transitions are append-only';
END;
$$;
DROP TRIGGER IF EXISTS ae_transition_append_only ON ae_transition;
CREATE TRIGGER ae_transition_append_only BEFORE UPDATE OR DELETE ON ae_transition FOR EACH ROW EXECUTE FUNCTION ae_transition_append_only();
CREATE TABLE IF NOT EXISTS ae_worker (
 worker TEXT PRIMARY KEY, label TEXT NOT NULL, state TEXT NOT NULL, owner TEXT, heartbeat_at TEXT, last_success_at TEXT,
 last_error TEXT, detail_json TEXT NOT NULL DEFAULT '{}', updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ae_lock (name TEXT PRIMARY KEY, owner TEXT NOT NULL, expires_at TEXT NOT NULL);

"""Autonomous engine persistence (SQLite locally, PostgreSQL/Neon in production). Every query is scope-bound.

Writes are idempotent: rows have deterministic ids derived from their evidence, inserts use ON CONFLICT DO NOTHING,
and transitions are append-only (a database trigger rejects UPDATE/DELETE).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

CYCLE_COLUMNS = ("id", "tenant_id", "trading_account_id", "origin", "status", "operating_mode", "safety_status", "provider",
                 "snapshot_id", "scanner_cycle_id", "data_as_of", "owner", "counts_json", "safety_json", "error", "started_at",
                 "completed_at", "duration_ms")
STAGE_COLUMNS = ("tenant_id", "trading_account_id", "stage", "status", "current_operation", "next_operation", "processed", "active",
                 "waiting", "errors", "metrics_json", "blockers_json", "detail_json", "provider", "cycle_id", "last_update",
                 "last_success_at")
SYMBOL_COLUMNS = ("tenant_id", "trading_account_id", "symbol", "stage", "state", "reason_code", "provider", "data_as_of",
                  "evidence_json", "updated_at")
OPP_COLUMNS = ("id", "tenant_id", "trading_account_id", "family_key", "symbol", "direction", "opp_type", "tit_level", "parent_tf",
               "trigger_tf", "stage", "state", "status", "outcome", "entry_lo", "entry_hi", "invalidation", "target_1", "target_2",
               "current_price", "price_at", "confidence", "quality", "reward_risk", "next_condition", "reason_code", "provider",
               "snapshot_id", "evidence_json", "blockers_json", "origin_at", "stage_entered_at", "evaluated_through", "created_at",
               "updated_at", "closed_at")
CHANNEL_COLUMNS = ("id", "tenant_id", "trading_account_id", "symbol", "timeframe", "status", "state", "direction", "validity", "upper",
                   "mid", "lower", "width", "width_atr", "atr", "position", "touches_upper", "touches_lower", "quality", "age_bars",
                   "erz_lo", "erz_hi", "break_direction", "break_level", "break_at", "retest_at", "continuation_at",
                   "last_touch_at", "last_touch_side", "state_entered_at", "started_at", "last_bar_at", "closed_at", "provider",
                   "lines_json", "updated_at")
TRANSITION_COLUMNS = ("id", "tenant_id", "trading_account_id", "entity_type", "entity_id", "symbol", "timeframe", "from_stage",
                      "from_state", "to_stage", "to_state", "reason_code", "detail", "evidence_json", "provider", "evidence_at",
                      "cycle_id", "created_at")
WORKER_COLUMNS = ("worker", "label", "state", "owner", "heartbeat_at", "last_success_at", "last_error", "detail_json", "updated_at")
JSON_DEFAULTS = {"counts_json": {}, "safety_json": {}, "metrics_json": {}, "blockers_json": [], "detail_json": {}, "evidence_json": {},
                 "lines_json": {}}


def now_iso(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).isoformat()


def det_id(prefix: str, *parts) -> str:
    """Deterministic id: replaying the same evidence yields the same row (idempotent inserts)."""
    digest = hashlib.sha1("|".join("" if p is None else str(p) for p in parts).encode()).hexdigest()
    return f"{prefix}-{digest[:16]}"


def _dump(value) -> str:
    return json.dumps(value, default=str, separators=(",", ":"))


def _row(r, columns) -> dict:
    d = dict(r) if hasattr(r, "keys") else dict(zip(columns, tuple(r)))
    for key in [k for k in d if k.endswith("_json")]:
        raw = d.pop(key)
        try:
            value = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            value = None
        d[key[:-5]] = JSON_DEFAULTS.get(key) if value is None else value
    return d


def _encode(fields: dict) -> dict:
    out = {}
    for k, v in fields.items():
        if k.endswith("_json") and not isinstance(v, str):
            v = _dump(v)
        out[k] = v
    return out


class AERepository:
    def __init__(self, conn, scope: tuple[str, str]):
        self.conn = conn
        self.tenant, self.account = scope

    # ----- lease lock -----

    def acquire_lock(self, name: str, owner: str, seconds: float, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        expires = (now + timedelta(seconds=seconds)).isoformat()
        self.conn.execute(
            "INSERT INTO ae_lock(name, owner, expires_at) VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET "
            "owner=excluded.owner, expires_at=excluded.expires_at WHERE ae_lock.expires_at < ? OR ae_lock.owner = ?",
            (name, owner, expires, now.isoformat(), owner),
        )
        self.conn.commit()
        row = self.conn.execute("SELECT owner FROM ae_lock WHERE name=?", (name,)).fetchone()
        return bool(row) and _row(row, ("owner",))["owner"] == owner

    def release_lock(self, name: str, owner: str) -> None:
        self.conn.execute("DELETE FROM ae_lock WHERE name=? AND owner=?", (name, owner))
        self.conn.commit()

    def lock_state(self, name: str) -> dict | None:
        row = self.conn.execute("SELECT name, owner, expires_at FROM ae_lock WHERE name=?", (name,)).fetchone()
        return _row(row, ("name", "owner", "expires_at")) if row else None

    # ----- cycles -----

    def start_cycle(self, cycle: dict) -> None:
        row = _encode({**{c: None for c in CYCLE_COLUMNS}, "counts_json": {}, "safety_json": {}, **cycle,
                       "tenant_id": self.tenant, "trading_account_id": self.account})
        self.conn.execute(f"INSERT INTO ae_cycle({','.join(CYCLE_COLUMNS)}) VALUES({','.join('?' * len(CYCLE_COLUMNS))}) "
                          "ON CONFLICT(id) DO NOTHING", tuple(row[c] for c in CYCLE_COLUMNS))

    def finish_cycle(self, cycle_id: str, **fields) -> None:
        fields = _encode(fields)
        cols = ", ".join(f"{k}=?" for k in fields)
        self.conn.execute(f"UPDATE ae_cycle SET {cols} WHERE id=?", (*fields.values(), cycle_id))

    def last_cycle(self, status: str | None = None) -> dict | None:
        sql = f"SELECT {','.join(CYCLE_COLUMNS)} FROM ae_cycle WHERE tenant_id=? AND trading_account_id=?"
        params: list = [self.tenant, self.account]
        if status:
            sql += " AND status=?"
            params.append(status)
        r = self.conn.execute(sql + " ORDER BY started_at DESC LIMIT 1", params).fetchone()
        return _row(r, CYCLE_COLUMNS) if r else None

    def cycles(self, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(f"SELECT {','.join(CYCLE_COLUMNS)} FROM ae_cycle WHERE tenant_id=? AND trading_account_id=? "
                                 "ORDER BY started_at DESC LIMIT ?", (self.tenant, self.account, limit)).fetchall()
        return [_row(r, CYCLE_COLUMNS) for r in rows]

    # ----- stage & symbol state -----

    def put_stage(self, stage: str, fields: dict) -> None:
        row = _encode({**{c: None for c in STAGE_COLUMNS}, "processed": 0, "active": 0, "waiting": 0, "errors": 0,
                       "metrics_json": {}, "blockers_json": [], "detail_json": {}, **fields,
                       "tenant_id": self.tenant, "trading_account_id": self.account, "stage": stage})
        keys = ("tenant_id", "trading_account_id", "stage")
        updates = ",".join(f"{c}=excluded.{c}" for c in STAGE_COLUMNS if c not in keys and c != "last_success_at")
        # last_success_at only moves forward when a stage succeeded in this cycle.
        updates += ",last_success_at=COALESCE(excluded.last_success_at, ae_stage_state.last_success_at)"
        self.conn.execute(f"INSERT INTO ae_stage_state({','.join(STAGE_COLUMNS)}) VALUES({','.join('?' * len(STAGE_COLUMNS))}) "
                          f"ON CONFLICT(tenant_id, trading_account_id, stage) DO UPDATE SET {updates}",
                          tuple(row[c] for c in STAGE_COLUMNS))

    def stages(self) -> dict[str, dict]:
        rows = self.conn.execute(f"SELECT {','.join(STAGE_COLUMNS)} FROM ae_stage_state WHERE tenant_id=? AND trading_account_id=?",
                                 (self.tenant, self.account)).fetchall()
        return {d["stage"]: d for d in (_row(r, STAGE_COLUMNS) for r in rows)}

    def put_symbol(self, symbol: str, fields: dict) -> None:
        row = _encode({**{c: None for c in SYMBOL_COLUMNS}, "evidence_json": {}, **fields,
                       "tenant_id": self.tenant, "trading_account_id": self.account, "symbol": symbol})
        keys = ("tenant_id", "trading_account_id", "symbol")
        updates = ",".join(f"{c}=excluded.{c}" for c in SYMBOL_COLUMNS if c not in keys)
        self.conn.execute(f"INSERT INTO ae_symbol_state({','.join(SYMBOL_COLUMNS)}) VALUES({','.join('?' * len(SYMBOL_COLUMNS))}) "
                          f"ON CONFLICT(tenant_id, trading_account_id, symbol) DO UPDATE SET {updates}",
                          tuple(row[c] for c in SYMBOL_COLUMNS))

    def symbols(self) -> list[dict]:
        rows = self.conn.execute(f"SELECT {','.join(SYMBOL_COLUMNS)} FROM ae_symbol_state WHERE tenant_id=? AND trading_account_id=? "
                                 "ORDER BY symbol", (self.tenant, self.account)).fetchall()
        return [_row(r, SYMBOL_COLUMNS) for r in rows]

    # ----- opportunities -----

    def insert_opportunity(self, opp: dict) -> bool:
        row = _encode({**{c: None for c in OPP_COLUMNS}, "evidence_json": {}, "blockers_json": [], **opp,
                       "tenant_id": self.tenant, "trading_account_id": self.account})
        cur = self.conn.execute(f"INSERT INTO ae_opportunity({','.join(OPP_COLUMNS)}) VALUES({','.join('?' * len(OPP_COLUMNS))}) "
                                "ON CONFLICT(id) DO NOTHING", tuple(row[c] for c in OPP_COLUMNS))
        return (cur.rowcount or 0) > 0

    def update_opportunity(self, opp_id: str, **fields) -> None:
        fields = _encode(fields)
        cols = ", ".join(f"{k}=?" for k in fields)
        self.conn.execute(f"UPDATE ae_opportunity SET {cols} WHERE id=? AND tenant_id=? AND trading_account_id=?",
                          (*fields.values(), opp_id, self.tenant, self.account))

    def opportunity(self, opp_id: str) -> dict | None:
        r = self.conn.execute(f"SELECT {','.join(OPP_COLUMNS)} FROM ae_opportunity WHERE id=? AND tenant_id=? AND trading_account_id=?",
                              (opp_id, self.tenant, self.account)).fetchone()
        return _row(r, OPP_COLUMNS) if r else None

    def active_opportunities(self) -> list[dict]:
        rows = self.conn.execute(f"SELECT {','.join(OPP_COLUMNS)} FROM ae_opportunity WHERE tenant_id=? AND trading_account_id=? "
                                 "AND status='ACTIVE' ORDER BY created_at, id", (self.tenant, self.account)).fetchall()
        return [_row(r, OPP_COLUMNS) for r in rows]

    def opportunities(self, *, status: str | None = None, symbol: str | None = None, stage: str | None = None,
                      opp_type: str | None = None, since: str | None = None, limit: int = 200) -> list[dict]:
        sql = f"SELECT {','.join(OPP_COLUMNS)} FROM ae_opportunity WHERE tenant_id=? AND trading_account_id=?"
        params: list = [self.tenant, self.account]
        for col, val in (("status", status), ("symbol", symbol), ("stage", stage), ("opp_type", opp_type)):
            if val:
                sql += f" AND {col}=?"
                params.append(val)
        if since:
            sql += " AND updated_at>=?"
            params.append(since)
        sql += " ORDER BY updated_at DESC, id LIMIT ?"
        params.append(limit)
        return [_row(r, OPP_COLUMNS) for r in self.conn.execute(sql, params).fetchall()]

    def last_closed_family(self, family_key: str) -> dict | None:
        r = self.conn.execute(f"SELECT {','.join(OPP_COLUMNS)} FROM ae_opportunity WHERE tenant_id=? AND trading_account_id=? "
                              "AND family_key=? AND status='CLOSED' ORDER BY evaluated_through DESC LIMIT 1",
                              (self.tenant, self.account, family_key)).fetchone()
        return _row(r, OPP_COLUMNS) if r else None

    def closed_opportunities(self, since: str | None = None, limit: int = 2000) -> list[dict]:
        sql = f"SELECT {','.join(OPP_COLUMNS)} FROM ae_opportunity WHERE tenant_id=? AND trading_account_id=? AND status='CLOSED'"
        params: list = [self.tenant, self.account]
        if since:
            sql += " AND closed_at>=?"
            params.append(since)
        sql += " ORDER BY closed_at DESC LIMIT ?"
        params.append(limit)
        return [_row(r, OPP_COLUMNS) for r in self.conn.execute(sql, params).fetchall()]

    # ----- channels -----

    def insert_channel(self, ch: dict) -> bool:
        row = _encode({**{c: None for c in CHANNEL_COLUMNS}, "touches_upper": 0, "touches_lower": 0, "lines_json": {}, **ch,
                       "tenant_id": self.tenant, "trading_account_id": self.account})
        cur = self.conn.execute(f"INSERT INTO ae_channel({','.join(CHANNEL_COLUMNS)}) VALUES({','.join('?' * len(CHANNEL_COLUMNS))}) "
                                "ON CONFLICT(id) DO NOTHING", tuple(row[c] for c in CHANNEL_COLUMNS))
        return (cur.rowcount or 0) > 0

    def update_channel(self, channel_id: str, **fields) -> None:
        fields = _encode(fields)
        cols = ", ".join(f"{k}=?" for k in fields)
        self.conn.execute(f"UPDATE ae_channel SET {cols} WHERE id=? AND tenant_id=? AND trading_account_id=?",
                          (*fields.values(), channel_id, self.tenant, self.account))

    def channel(self, channel_id: str) -> dict | None:
        r = self.conn.execute(f"SELECT {','.join(CHANNEL_COLUMNS)} FROM ae_channel WHERE id=? AND tenant_id=? AND trading_account_id=?",
                              (channel_id, self.tenant, self.account)).fetchone()
        return _row(r, CHANNEL_COLUMNS) if r else None

    def active_channels(self) -> list[dict]:
        rows = self.conn.execute(f"SELECT {','.join(CHANNEL_COLUMNS)} FROM ae_channel WHERE tenant_id=? AND trading_account_id=? "
                                 "AND status='ACTIVE' ORDER BY symbol, timeframe", (self.tenant, self.account)).fetchall()
        return [_row(r, CHANNEL_COLUMNS) for r in rows]

    def channels(self, *, status: str | None = None, symbol: str | None = None, timeframe: str | None = None,
                 limit: int = 300) -> list[dict]:
        sql = f"SELECT {','.join(CHANNEL_COLUMNS)} FROM ae_channel WHERE tenant_id=? AND trading_account_id=?"
        params: list = [self.tenant, self.account]
        for col, val in (("status", status), ("symbol", symbol), ("timeframe", timeframe)):
            if val:
                sql += f" AND {col}=?"
                params.append(val)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        return [_row(r, CHANNEL_COLUMNS) for r in self.conn.execute(sql, params).fetchall()]

    # ----- transitions (append-only audit trail) -----

    def add_transition(self, t: dict) -> bool:
        tid = t.get("id") or det_id("TR", t["entity_id"], t.get("from_state"), t["to_state"], t["evidence_at"], t["reason_code"])
        row = _encode({**{c: None for c in TRANSITION_COLUMNS}, "evidence_json": {}, "created_at": now_iso(), **t, "id": tid,
                       "tenant_id": self.tenant, "trading_account_id": self.account})
        cur = self.conn.execute(f"INSERT INTO ae_transition({','.join(TRANSITION_COLUMNS)}) "
                                f"VALUES({','.join('?' * len(TRANSITION_COLUMNS))}) ON CONFLICT(id) DO NOTHING",
                                tuple(row[c] for c in TRANSITION_COLUMNS))
        return (cur.rowcount or 0) > 0

    def transitions(self, *, entity_id: str | None = None, entity_type: str | None = None, symbol: str | None = None,
                    timeframe: str | None = None, to_state: str | None = None, since: str | None = None,
                    limit: int = 100) -> list[dict]:
        sql = f"SELECT {','.join(TRANSITION_COLUMNS)} FROM ae_transition WHERE tenant_id=? AND trading_account_id=?"
        params: list = [self.tenant, self.account]
        for col, val in (("entity_id", entity_id), ("entity_type", entity_type), ("symbol", symbol), ("timeframe", timeframe),
                         ("to_state", to_state)):
            if val:
                sql += f" AND {col}=?"
                params.append(val)
        if since:
            sql += " AND evidence_at>=?"
            params.append(since)
        order = "ASC" if entity_id else "DESC"
        sql += f" ORDER BY evidence_at {order}, created_at {order} LIMIT ?"
        params.append(limit)
        return [_row(r, TRANSITION_COLUMNS) for r in self.conn.execute(sql, params).fetchall()]

    def transition_counts(self, entity_type: str, since: str) -> dict[str, int]:
        rows = self.conn.execute("SELECT to_state, COUNT(*) AS n FROM ae_transition WHERE tenant_id=? AND trading_account_id=? "
                                 "AND entity_type=? AND evidence_at>=? GROUP BY to_state",
                                 (self.tenant, self.account, entity_type, since)).fetchall()
        return {d["to_state"]: int(d["n"] or 0) for d in (_row(r, ("to_state", "n")) for r in rows)}

    # ----- workers -----

    def heartbeat(self, worker: str, label: str, state: str, *, owner: str | None = None, success_at: str | None = None,
                  error: str | None = None, detail: dict | None = None, at: str | None = None) -> None:
        stamp = at or now_iso()
        self.conn.execute(
            f"INSERT INTO ae_worker({','.join(WORKER_COLUMNS)}) VALUES({','.join('?' * len(WORKER_COLUMNS))}) ON CONFLICT(worker) DO UPDATE SET "
            "label=excluded.label, state=excluded.state, owner=excluded.owner, heartbeat_at=excluded.heartbeat_at, "
            "last_success_at=COALESCE(excluded.last_success_at, ae_worker.last_success_at), last_error=excluded.last_error, "
            "detail_json=excluded.detail_json, updated_at=excluded.updated_at",
            (worker, label, state, owner, stamp, success_at, error, _dump(detail or {}), stamp),
        )

    def workers(self) -> list[dict]:
        rows = self.conn.execute(f"SELECT {','.join(WORKER_COLUMNS)} FROM ae_worker ORDER BY worker").fetchall()
        return [_row(r, WORKER_COLUMNS) for r in rows]

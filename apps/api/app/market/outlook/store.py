"""HistoricalOutlookRepository and the cross-instance job lock (works on SQLite and PostgreSQL/Neon)."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

from ..provenance import values

RUN_STATES = (
    "SCHEDULED", "SNAPSHOTTING", "VALIDATING_DATA", "ANALYSING", "GENERATING_HYPOTHESES", "SCORING", "PROJECTING",
    "RANKING_OPPORTUNITIES", "PUBLISHING", "PUBLISHED", "MONITORING", "EVALUATING", "ARCHIVED",
    "FAILED", "RETRY", "INSUFFICIENT_DATA", "MISSED",
)
DONE_STATES = ("PUBLISHED", "MONITORING", "EVALUATING", "ARCHIVED")
RUN_COLUMNS = ("id", "tenant_id", "trading_account_id", "analysis_date", "origin", "state", "attempts", "snapshot_id", "close_at",
               "engine_version", "symbols_total", "symbols_published", "symbols_failed", "symbols_insufficient", "qualified",
               "started_at", "published_at", "monitored_at", "evaluated_at", "next_retry_at", "error", "log_json", "created_at", "updated_at")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row(r) -> dict:
    return dict(r) if hasattr(r, "keys") else dict(zip(RUN_COLUMNS, values(r)))


class OutlookRepository:
    def __init__(self, conn, scope: tuple[str, str]):
        self.conn = conn
        self.tenant, self.account = scope

    # ----- locks -----

    def acquire_lock(self, name: str, owner: str, seconds: float) -> bool:
        now = datetime.now(timezone.utc)
        expires = (now + timedelta(seconds=seconds)).isoformat()
        self.conn.execute(
            "INSERT INTO ai_outlook_lock(name, owner, expires_at) VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET "
            "owner=excluded.owner, expires_at=excluded.expires_at WHERE ai_outlook_lock.expires_at < ? OR ai_outlook_lock.owner = ?",
            (name, owner, expires, now.isoformat(), owner),
        )
        self.conn.commit()
        row = self.conn.execute("SELECT owner FROM ai_outlook_lock WHERE name=?", (name,)).fetchone()
        return bool(row) and values(row)[0] == owner

    def release_lock(self, name: str, owner: str) -> None:
        self.conn.execute("DELETE FROM ai_outlook_lock WHERE name=? AND owner=?", (name, owner))
        self.conn.commit()

    # ----- runs -----

    def run(self, analysis_date: str, origin: str = "LIVE") -> dict | None:
        r = self.conn.execute(
            f"SELECT {','.join(RUN_COLUMNS)} FROM ai_outlook_run WHERE tenant_id=? AND trading_account_id=? AND analysis_date=? AND origin=?",
            (self.tenant, self.account, analysis_date, origin),
        ).fetchone()
        return _row(r) if r else None

    def run_by_id(self, run_id: str) -> dict | None:
        r = self.conn.execute(f"SELECT {','.join(RUN_COLUMNS)} FROM ai_outlook_run WHERE id=?", (run_id,)).fetchone()
        return _row(r) if r else None

    def create_run(self, analysis_date: str, origin: str, close_at: str, engine_version: str) -> dict:
        stamp = now_iso()
        rid = str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO ai_outlook_run(id, tenant_id, trading_account_id, analysis_date, origin, state, close_at, engine_version, created_at, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
            (rid, self.tenant, self.account, analysis_date, origin, "SCHEDULED", close_at, engine_version, stamp, stamp),
        )
        self.conn.commit()
        return self.run(analysis_date, origin)  # type: ignore[return-value]

    def update_run(self, run_id: str, **fields) -> None:
        if "log" in fields:
            entry = fields.pop("log")
            cur = self.conn.execute("SELECT log_json FROM ai_outlook_run WHERE id=?", (run_id,)).fetchone()
            log = json.loads(values(cur)[0] or "[]") if cur else []
            log.append(entry)
            fields["log_json"] = json.dumps(log[-80:])
        fields["updated_at"] = now_iso()
        cols = ", ".join(f"{k}=?" for k in fields)
        self.conn.execute(f"UPDATE ai_outlook_run SET {cols} WHERE id=?", (*fields.values(), run_id))
        self.conn.commit()

    def runs(self, origin: str | None = None, states: tuple[str, ...] | None = None, limit: int = 120) -> list[dict]:
        sql = f"SELECT {','.join(RUN_COLUMNS)} FROM ai_outlook_run WHERE tenant_id=? AND trading_account_id=?"
        params: list = [self.tenant, self.account]
        if origin:
            sql += " AND origin=?"
            params.append(origin)
        if states:
            sql += f" AND state IN ({','.join('?' * len(states))})"
            params += list(states)
        sql += " ORDER BY analysis_date DESC LIMIT ?"
        params.append(limit)
        return [_row(r) for r in self.conn.execute(sql, params).fetchall()]

    def latest_published(self) -> dict | None:
        rows = self.runs(states=DONE_STATES, limit=4)
        live = [r for r in rows if r["origin"] == "LIVE"]
        return (live or rows or [None])[0]

    def dates_with_outlooks(self) -> set[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT analysis_date FROM ai_outlook_run WHERE tenant_id=? AND trading_account_id=? AND state IN ("
            + ",".join("?" * len(DONE_STATES)) + ")", (self.tenant, self.account, *DONE_STATES)).fetchall()
        return {str(values(r)[0]) for r in rows}

    # ----- snapshots and symbol outlooks (append-only) -----

    def save_snapshot(self, run_id: str, analysis_date: str, cutoff: str, manifest: dict) -> str:
        sid = manifest["snapshot_id"]
        self.conn.execute(
            "INSERT INTO ai_outlook_snapshot(id, run_id, analysis_date, cutoff_at, frozen_at, manifest_json, created_at) VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT DO NOTHING", (sid, run_id, analysis_date, cutoff, manifest["frozen_at"], json.dumps(manifest), now_iso()))
        self.conn.commit()
        return sid

    def snapshot(self, sid: str) -> dict | None:
        r = self.conn.execute("SELECT manifest_json FROM ai_outlook_snapshot WHERE id=?", (sid,)).fetchone()
        return json.loads(values(r)[0]) if r else None

    def insert_outlooks(self, run: dict, outlooks: list[dict]) -> None:
        stamp = now_iso()
        for o in outlooks:
            self.conn.execute(
                "INSERT INTO ai_outlook_symbol(id, run_id, tenant_id, trading_account_id, analysis_date, origin, symbol, status, qualified, "
                "opportunity_rank, opportunity_score, direction, confidence, regime, engine_version, payload_json, created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
                (o["outlook_id"], run["id"], self.tenant, self.account, run["analysis_date"], run["origin"], o["symbol"], o["status"],
                 1 if o.get("qualified") else 0, o.get("opportunity_rank"), o.get("opportunity_score"), o.get("expected_direction"),
                 (o.get("confidence") or {}).get("primary"), (o.get("regime") or {}).get("key"), o["engine_version"],
                 json.dumps(o, default=str), stamp),
            )
        self.conn.commit()

    def outlook_rows(self, run_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, symbol, status, qualified, opportunity_rank, opportunity_score, direction, confidence, regime FROM ai_outlook_symbol "
            "WHERE run_id=? ORDER BY opportunity_rank IS NULL, opportunity_rank, symbol", (run_id,)).fetchall()
        keys = ("id", "symbol", "status", "qualified", "opportunity_rank", "opportunity_score", "direction", "confidence", "regime")
        return [dict(zip(keys, values(r))) for r in rows]

    def outlook(self, run_id: str, symbol: str) -> dict | None:
        r = self.conn.execute("SELECT id, payload_json FROM ai_outlook_symbol WHERE run_id=? AND symbol=?", (run_id, symbol)).fetchone()
        if not r:
            return None
        oid, payload = values(r)
        return {**json.loads(payload), "outlook_id": oid}

    def summaries(self, run_id: str) -> list[dict]:
        """Per-instrument summary rows for the published-run table, without transferring every full payload."""
        cols = "id, symbol, status, qualified, opportunity_rank, opportunity_score, direction, confidence"
        # Every extracted column needs an alias: PostgreSQL dict rows would otherwise collapse them all into "?column?".
        if getattr(self.conn, "provider", "sqlite") == "sqlite":
            sql = (f"SELECT {cols}, json_extract(payload_json,'$.regime.label') AS regime_label, json_extract(payload_json,'$.reason') AS reason, "
                   "json_extract(payload_json,'$.system_action') AS system_action, json_extract(payload_json,'$.price') AS price, "
                   "json_extract(payload_json,'$.digits') AS digits, json_extract(payload_json,'$.late') AS late "
                   "FROM ai_outlook_symbol WHERE run_id=?")
        else:
            sql = (f"SELECT {cols}, p->'regime'->>'label' AS regime_label, p->>'reason' AS reason, (p->'system_action')::text AS system_action, "
                   "p->>'price' AS price, p->>'digits' AS digits, p->>'late' AS late "
                   f"FROM (SELECT {cols}, payload_json::json AS p FROM ai_outlook_symbol WHERE run_id=?) s")
        out = []
        for r in self.conn.execute(sql, (run_id,)).fetchall():
            oid, sym, status, qualified, rank, score, direction, conf, regime, reason, action, price, digits, late = values(r)
            out.append({"outlook_id": oid, "symbol": sym, "status": status, "qualified": bool(qualified), "opportunity_rank": rank,
                        "opportunity_score": score, "expected_direction": direction, "confidence": conf, "regime": regime, "reason": reason,
                        "system_action": json.loads(action) if isinstance(action, str) else action,
                        "price": None if price is None else float(price), "digits": None if digits is None else int(digits),
                        "late": None if late is None else late in (True, 1, "true")})
        return out

    def latest_revisions(self, outlook_ids: list[str]) -> dict[str, dict]:
        """Newest revision per outlook in one round trip (status and live system action)."""
        if not outlook_ids:
            return {}
        marks = ",".join("?" * len(outlook_ids))
        rows = self.conn.execute(
            "SELECT outlook_id, status, detail_json FROM (SELECT outlook_id, status, detail_json, ROW_NUMBER() OVER "
            f"(PARTITION BY outlook_id ORDER BY observed_at DESC, created_at DESC) AS n FROM ai_outlook_revision WHERE outlook_id IN ({marks})) r "
            "WHERE n=1", tuple(outlook_ids)).fetchall()
        out = {}
        for r in rows:
            oid, status, detail = values(r)
            out[str(oid)] = {"status": status, "system_action": json.loads(detail or "{}").get("system_action")}
        return out

    def outlooks(self, run_id: str) -> list[dict]:
        rows = self.conn.execute("SELECT id, payload_json FROM ai_outlook_symbol WHERE run_id=?", (run_id,)).fetchall()
        return [{**json.loads(values(r)[1]), "outlook_id": values(r)[0]} for r in rows]

    # ----- intraday revisions (status/evidence only; the original prediction never changes) -----

    def latest_revision(self, outlook_id: str) -> dict | None:
        r = self.conn.execute(
            "SELECT status, observed_at, price, detail_json FROM ai_outlook_revision WHERE outlook_id=? ORDER BY observed_at DESC, created_at DESC LIMIT 1",
            (outlook_id,)).fetchone()
        if not r:
            return None
        status, at, price, detail = values(r)
        return {"status": status, "observed_at": at, "price": price, **json.loads(detail or "{}")}

    def revisions(self, outlook_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT status, previous_status, observed_at, price, detail_json FROM ai_outlook_revision WHERE outlook_id=? ORDER BY observed_at", (outlook_id,)).fetchall()
        return [{"status": s, "previous_status": p, "observed_at": at, "price": px, **json.loads(d or "{}")} for s, p, at, px, d in (values(r) for r in rows)]

    def add_revision(self, outlook: dict, run_id: str, status: str, previous: str | None, observed_at: str, price: float | None, detail: dict) -> None:
        self.conn.execute(
            "INSERT INTO ai_outlook_revision(id, outlook_id, run_id, symbol, observed_at, status, previous_status, price, detail_json, created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), outlook["outlook_id"], run_id, outlook["symbol"], observed_at, status, previous, price, json.dumps(detail, default=str), now_iso()))

    # ----- evaluations and calibration -----

    def evaluated_ids(self, run_id: str) -> set[str]:
        return {str(values(r)[0]) for r in self.conn.execute("SELECT outlook_id FROM ai_outlook_evaluation WHERE run_id=?", (run_id,)).fetchall()}

    def add_evaluation(self, run: dict, outlook: dict, ev: dict) -> None:
        self.conn.execute(
            "INSERT INTO ai_outlook_evaluation(outlook_id, run_id, tenant_id, trading_account_id, symbol, analysis_date, evaluated_date, direction, "
            "confidence, qualified, outcome, scenario_result, direction_correct, target1_hit, target2_hit, invalidated, erz_touched, move_pct, detail_json, created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
            (outlook["outlook_id"], run["id"], self.tenant, self.account, outlook["symbol"], run["analysis_date"], ev["evaluated_date"],
             outlook.get("expected_direction"), (outlook.get("confidence") or {}).get("primary"), 1 if outlook.get("qualified") else 0,
             ev["outcome"], ev["scenario_result"], ev["direction_correct"], int(ev["target1_hit"]), int(ev["target2_hit"]), int(ev["invalidated"]),
             int(ev["erz_touched"]), ev["move_pct"], json.dumps(ev, default=str), now_iso()))

    def evaluations(self, symbol: str | None = None, since: str | None = None, qualified_only: bool = False) -> list[dict]:
        sql = ("SELECT symbol, analysis_date, evaluated_date, direction, confidence, qualified, outcome, scenario_result, direction_correct, "
               "target1_hit, target2_hit, invalidated, erz_touched, move_pct, detail_json, outlook_id FROM ai_outlook_evaluation "
               "WHERE tenant_id=? AND trading_account_id=?")
        params: list = [self.tenant, self.account]
        if symbol:
            sql += " AND symbol=?"
            params.append(symbol)
        if since:
            sql += " AND analysis_date>=?"
            params.append(since)
        if qualified_only:
            sql += " AND qualified=1"
        sql += " ORDER BY analysis_date DESC"
        keys = ("symbol", "analysis_date", "evaluated_date", "direction", "confidence", "qualified", "outcome", "scenario_result", "direction_correct",
                "target1_hit", "target2_hit", "invalidated", "erz_touched", "move_pct", "detail", "outlook_id")
        out = []
        for r in self.conn.execute(sql, params).fetchall():
            d = dict(zip(keys, values(r)))
            d["detail"] = json.loads(d["detail"] or "{}")
            out.append(d)
        return out

    def history(self, symbol: str, since: str) -> list[dict]:
        """Every published outlook for one symbol joined with its evaluation (if the next day has closed)."""
        rows = self.conn.execute(
            "SELECT s.id, s.analysis_date, s.origin, s.status, s.qualified, s.direction, s.confidence, s.regime, s.engine_version, s.payload_json, "
            "e.outcome, e.scenario_result, e.direction_correct, e.target1_hit, e.target2_hit, e.invalidated, e.erz_touched, e.move_pct, e.detail_json "
            "FROM ai_outlook_symbol s LEFT JOIN ai_outlook_evaluation e ON e.outlook_id = s.id "
            "WHERE s.tenant_id=? AND s.trading_account_id=? AND s.symbol=? AND s.analysis_date>=? ORDER BY s.analysis_date DESC, s.origin",
            (self.tenant, self.account, symbol, since)).fetchall()
        seen, out = set(), []
        for r in rows:
            (oid, date, origin, status, qualified, direction, conf, regime, version, payload, outcome, sres, dc, t1, t2, inv, erz, move, detail) = values(r)
            if date in seen:
                continue
            seen.add(date)
            out.append({"outlook_id": oid, "analysis_date": date, "origin": origin, "status": status, "qualified": bool(qualified), "direction": direction,
                        "confidence": conf, "regime": regime, "engine_version": version, "payload": json.loads(payload),
                        "evaluation": None if outcome is None else {"outcome": outcome, "scenario_result": sres, "direction_correct": dc, "target1_hit": bool(t1),
                                                                    "target2_hit": bool(t2), "invalidated": bool(inv), "erz_touched": bool(erz), "move_pct": move,
                                                                    **json.loads(detail or "{}")}})
        return out

    def save_calibration(self, run_id: str, table: dict, samples: int) -> None:
        self.conn.execute(
            "INSERT INTO ai_outlook_calibration(id, run_id, tenant_id, trading_account_id, table_json, samples, created_at) VALUES(?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), run_id, self.tenant, self.account, json.dumps(table), samples, now_iso()))

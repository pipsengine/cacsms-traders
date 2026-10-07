import json
import os
import re
import smtplib
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from apps.api.app.market import channel_events as ce
from apps.api.app.market import channel_intelligence as chan
from apps.api.app.market.channel_events import DomainEvent, Observation
from apps.api.app.market.scanner_analytics import Bar

APP_PASSWORD = "abcd efgh ijkl mnop"
SECRET = APP_PASSWORD.replace(" ", "")
SMTP_ENV = {
    "SMTP_ENABLED": "true", "SMTP_HOST": "smtp.gmail.com", "SMTP_PORT": "587", "SMTP_SECURITY": "starttls",
    "SMTP_USERNAME": "pipsengine@gmail.com", "SMTP_PASSWORD": APP_PASSWORD, "SMTP_FROM_EMAIL": "pipsengine@gmail.com",
    "SMTP_FROM_NAME": "Cacsms Traders",
}
NOW = datetime(2026, 10, 7, 9, 5, tzinfo=timezone.utc)
TRADE_WORDS = re.compile(r"\b(BUY|SELL|Buy|Sell)\b")


class FakeSMTP:
    instances: list["FakeSMTP"] = []
    fail_login: Exception | None = None
    fail_send: list[Exception] = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port, self.calls, self.sent = host, port, [], []
        FakeSMTP.instances.append(self)

    @classmethod
    def reset(cls):
        cls.instances, cls.fail_login, cls.fail_send = [], None, []

    @classmethod
    def all_sent(cls):
        return [m for i in cls.instances for m in i.sent]

    def ehlo(self):
        self.calls.append("ehlo")

    def starttls(self, context=None):
        self.calls.append("starttls")

    def login(self, user, password):
        self.calls.append(("login", user))
        self.password = password
        if FakeSMTP.fail_login:
            raise FakeSMTP.fail_login

    def send_message(self, msg):
        if FakeSMTP.fail_send:
            raise FakeSMTP.fail_send.pop(0)
        self.sent.append(msg)

    def quit(self):
        self.calls.append("quit")

    def close(self):
        pass


@pytest.fixture()
def env(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("DATABASE_PATH", path)
    monkeypatch.setenv("BOOTSTRAP_PASSWORD", "TestPass!123")
    for k, v in SMTP_ENV.items():
        monkeypatch.setenv(k, v)
    for k in ("SMTP_ENCRYPTION_KEY", "API_PROXY_SECRET", "CTRADER_CLIENT_SECRET"):
        monkeypatch.delenv(k, raising=False)
    FakeSMTP.reset()
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    from apps.api.app.services.bootstrap import bootstrap

    bootstrap()
    yield path
    try:
        Path(path).unlink(missing_ok=True)
    except PermissionError:
        pass


def _db():
    from apps.api.app.core.database import db

    return db()


def _tenant(conn):
    from apps.api.app.notifications.worker import alert_scope

    return alert_scope(conn)[0]


def _store(conn, tenant=None):
    from apps.api.app.notifications.store import NotificationStore

    return NotificationStore(conn, tenant or _tenant(conn))


def _process(events, observations=(), now=NOW, tenant=None):
    from apps.api.app.notifications.engine import AlertEngine

    with _db() as conn:
        return AlertEngine(conn, tenant or _tenant(conn)).process(list(events), list(observations), now)


def _recipient(email="ops@example.com", enabled=True, types=(), tenant=None):
    with _db() as conn:
        return _store(conn, tenant).add_recipient(email, "Ops", enabled, list(types))


def _audits(action):
    with _db() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM audit_events WHERE action=?", (action,)).fetchall()]


def _event(event_type="CHANNEL_BREAK", symbol="EURUSD", tf="H1", provider="mt5", at="2026-10-07T09:00:00+00:00", **kw):
    meta = kw.pop("metadata", {"channel_type": "Ascending regression channel", "upper_boundary": 1.1012, "lower_boundary": 1.0988,
                               "break_level": 1.1012, "break_price": 1.1040, "break_candle_close": at, "closes_beyond": 2,
                               "confirm_closes": 2, "context": {"summary": "H1 channel uptrend; parent H8 uptrend"}})
    return DomainEvent(event_type, symbol, tf, kw.pop("direction", "BULLISH"), provider, at, kw.pop("price", 1.104), kw.pop("level", 1.1012),
                       channel_id=kw.pop("channel_id", "CH-TEST"), identity=kw.pop("identity", at), metadata=meta, **kw)


def _body(msg) -> str:
    return "\n".join(part.get_content() for part in msg.walk() if part.get_content_type() in ("text/plain", "text/html"))


# ----- synthetic closed candles -----


def _flat(n, start=datetime(2026, 10, 1, tzinfo=timezone.utc)):
    out = []
    for i in range(n):
        mid = 1.1000 + 0.0008 * __import__("math").sin(i * 2 * 3.14159 / 24)
        out.append(Bar(start + timedelta(hours=i), mid, mid + 0.0003, mid - 0.0003, mid, 100))
    return out


def _extend(bars, rows):
    t = bars[-1].t
    return bars + [Bar(t + timedelta(hours=i + 1), o, h, l, c, 100) for i, (o, h, l, c) in enumerate(rows)]


def _core(bars):
    s = chan.channel_settings()
    return {tf: ({"available": False} if tf != "H1" else chan.tf_core(bars, "H1", s)) for tf in chan.CHANNEL_TIMEFRAMES}


# ----- SMTP configuration -----


def test_gmail_smtp_configuration_comes_from_environment(env):
    from apps.api.app.notifications.smtp import smtp_config

    with _db() as conn:
        cfg = smtp_config(conn)
    assert (cfg.host, cfg.port, cfg.security, cfg.username, cfg.from_email, cfg.from_name) == (
        "smtp.gmail.com", 587, "starttls", "pipsengine@gmail.com", "pipsengine@gmail.com", "Cacsms Traders")
    assert cfg.password == SECRET and cfg.password_source == "environment" and cfg.ready
    public = json.dumps(cfg.public())
    assert SECRET not in public and APP_PASSWORD not in public and "password\"" not in public.replace("password_", "")


def test_test_email_uses_starttls_and_creates_no_alert_event(env):
    from apps.api.app.notifications.worker import send_test_email

    with _db() as conn:
        result = send_test_email(conn, _tenant(conn), "user-cacsms", ["ops@example.com"])
    assert result["status"] == "SENT" and result["at"]
    smtp = FakeSMTP.instances[0]
    assert (smtp.host, smtp.port) == ("smtp.gmail.com", 587)
    assert smtp.calls[:4] == ["ehlo", "starttls", "ehlo", ("login", "pipsengine@gmail.com")]
    msg = smtp.sent[0]
    assert msg["Subject"] == "[Cacsms Traders] Email Notification Test"
    assert "Cacsms Traders email notification service is configured successfully." in _body(msg)
    assert "pipsengine@gmail.com" in msg["From"]
    with _db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM alert_events").fetchone()[0] == 0
        assert _store(conn).stats("2000")["last_sent_at"] is None  # tests are not counted as alert emails
    assert _audits("SMTP_TEST_SENT")


def test_smtp_authentication_failure_is_surfaced_without_the_password(env):
    from apps.api.app.notifications import smtp as smtp_mod
    from apps.api.app.notifications.worker import send_test_email

    FakeSMTP.fail_login = smtplib.SMTPAuthenticationError(535, f"5.7.8 Username and Password not accepted {SECRET}".encode())
    with _db() as conn:
        result = send_test_email(conn, _tenant(conn), "user-cacsms", ["ops@example.com"])
        health = smtp_mod.health(conn)
    assert result["status"] == "FAILED" and result["error_kind"] == "AUTH"
    assert "authentication failed" in result["error"].lower()
    assert SECRET not in result["error"] and SECRET not in json.dumps(health)
    assert health["last_test"]["status"] == "FAILED" and health["last_error_kind"] == "AUTH"
    audits = _audits("SMTP_TEST_FAILED")
    assert audits and all(SECRET not in json.dumps(a) for a in audits)


# ----- domain events from the Channel Intelligence engine -----


def test_channel_break_event_from_closed_candles():
    bars = _extend(_flat(70), [(1.1010, 1.1042, 1.1009, 1.1040), (1.1040, 1.1052, 1.1038, 1.1050), (1.1050, 1.1062, 1.1048, 1.1060)])
    events, _ = ce.channel_events("EURUSD", _core(bars), "mt5")
    breaks = [e for e in events if e.event_type == "CHANNEL_BREAK"]
    assert len(breaks) == 1
    e = breaks[0]
    assert (e.symbol, e.timeframe, e.direction, e.provider) == ("EURUSD", "H1", "BULLISH", "mt5")
    assert e.metadata["closes_beyond"] >= 2 and e.metadata["break_price"] == pytest.approx(1.1040)
    assert e.metadata["upper_boundary"] > e.metadata["lower_boundary"]
    assert e.event_time == (bars[-2].t + timedelta(hours=1)).isoformat()  # second closed candle confirms (2-close rule)
    assert e.metadata["break_candle_close"] == (bars[-3].t + timedelta(hours=1)).isoformat()


def test_unconfirmed_intrabar_style_break_is_not_an_event():
    bars = _extend(_flat(70), [(1.1010, 1.1042, 1.1009, 1.1040)])  # one close beyond: not yet confirmed
    events, _ = ce.channel_events("EURUSD", _core(bars), "mt5")
    assert not [e for e in events if e.event_type == "CHANNEL_BREAK"]


def test_break_and_retest_continuation_event():
    rows = [(1.1010, 1.1042, 1.1009, 1.1040), (1.1040, 1.1052, 1.1042, 1.1050), (1.1050, 1.1045, 1.1012, 1.1030),
            (1.1030, 1.1062, 1.1029, 1.1060)]
    bars = _extend(_flat(70), rows)
    events, _ = ce.channel_events("EURUSD", _core(bars), "ctrader")
    cont = [e for e in events if e.event_type == "BREAK_RETEST_CONTINUATION"]
    assert len(cont) == 1
    m = cont[0].metadata
    assert m["label"] == "BULLISH TREND CONTINUATION" and cont[0].direction == "BULLISH"
    assert m["retest_time"] == (bars[-2].t + timedelta(hours=1)).isoformat()
    assert cont[0].event_time == (bars[-1].t + timedelta(hours=1)).isoformat()
    assert m["break_time"] and m["confirmation_state"].startswith("Retest held") and cont[0].provider == "ctrader"


def _touch_core(last_high, prev_highs, t0=datetime(2026, 10, 7, tzinfo=timezone.utc)):
    highs = [*prev_highs, last_high]
    candles = [{"t": (t0 + timedelta(hours=i)).isoformat(), "o": 1.1000, "h": h, "l": 1.0995, "c": min(h, 1.1018)} for i, h in enumerate(highs)]
    return {"available": True, "spark": {"candles": candles}, "atr": 0.0010, "upper": 1.1020, "lower": 1.0980, "slope": 0.0,
            "validity": {"key": "VALID", "label": "Valid (Respecting Channel)"}, "fit_start": "2026-10-01T00:00:00+00:00",
            "touches_upper": 3, "touches_lower": 3, "period": 60}


@pytest.fixture()
def touch_context(monkeypatch):
    monkeypatch.setattr(ce, "_context", lambda core, tf, s: {"channel_direction": "UPTREND", "validity": "Valid", "channel_state": "Testing Upper",
                                                              "summary": "H1 channel uptrend"})


def test_channel_touch_event_reports_boundary_and_tolerance(touch_context):
    c = _touch_core(1.1019, [1.1005, 1.1004, 1.1006])
    events, obs = ce._touch_events("EURUSD", "H1", c, {}, "mt5", chan.channel_settings())
    assert [e.metadata["boundary"] for e in events] == ["UPPER"]
    e = events[0]
    assert e.event_type == "CHANNEL_TOUCH" and e.level == pytest.approx(1.1020) and e.price == pytest.approx(1.1019)
    assert e.metadata["tolerance"] == pytest.approx(0.25 * 0.0010) and e.metadata["label"] == "Upper Channel Touch"
    assert e.inactive_before == 3 and e.rearm_key == "CHANNEL_TOUCH|EURUSD|H1|UPPER"
    assert {o.rearm_key: o.inactive_bars for o in obs}["CHANNEL_TOUCH|EURUSD|H1|UPPER"] == 0


def test_touch_alert_rearms_only_after_price_leaves_the_zone(env, touch_context):
    _recipient()
    s = chan.channel_settings()
    sequence = [1.1019, 1.1019, 1.1005, 1.1004, 1.1019]
    highs = [1.1005, 1.1004, 1.1006]
    fired = []
    for i, h in enumerate(sequence):
        c = _touch_core(h, highs, datetime(2026, 10, 7, tzinfo=timezone.utc) + timedelta(hours=i))
        events, obs = ce._touch_events("EURUSD", "H1", c, {}, "mt5", s)
        fired.append(_process(events, obs, NOW + timedelta(hours=i))["queued"])
        _process(events, obs, NOW + timedelta(hours=i, minutes=5))  # repeated cycles on the same bar
        highs = highs[1:] + [h]
    assert fired == [1, 0, 0, 0, 1]


def test_tit_event_carries_l1_to_l4_hierarchy(env, monkeypatch):
    layers = [{"id": "L1", "tf": "W", "available": True, "trend": {"key": "UPTREND", "label": "Bullish"}, "state": {"key": "ACTIVE"}, "position": 62, "alignment": "—"},
              {"id": "L2", "tf": "D1", "available": True, "trend": {"key": "UPTREND", "label": "Bullish"}, "state": {"key": "ACTIVE"}, "position": 40, "alignment": "With L1"},
              {"id": "L3", "tf": "H8", "available": True, "trend": {"key": "DOWNTREND", "label": "Bearish"}, "state": {"key": "PULLBACK"}, "position": 20, "alignment": "Countertrend"},
              {"id": "L4", "tf": "H1", "available": True, "trend": {"key": "UPTREND", "label": "Bullish"}, "state": {"key": "ACTIVE"}, "position": 55, "alignment": "With L1"}]
    active = {"available": True, "state": {"key": "ACTIVE", "label": "Active"}, "price": 2650.5, "summary": "Bullish continuation setup",
              "parent": {"layer": "L1", "tf": "W", "direction": "UPTREND", "state": {"label": "Active"}}, "layers": layers,
              "countertrend": {"layer": "L3", "tf": "H8", "type": "Pullback Channel", "phase": "Late Pullback", "maturity": 78, "position": 20,
                               "rejoin_level": 2662.0, "rejoin_score": 71, "exec_tf": "H1", "exec_layer": "L4"},
              "setup": {"zone": [2640.0, 2648.0], "objective_1": 2662.0, "objective_2": 2700.0, "invalidation": 2620.0,
                        "type": "Channel Rejoin (Trend Continuation)", "quality": 74},
              "takeaways": ["Higher timeframe (W) trend is bullish and active.", "Price is in H8 countertrend channel (pullback)."]}
    state = {"view": active}
    monkeypatch.setattr(chan, "tit_view", lambda *a, **k: state["view"])
    core = {"H8": {"closed_at": "2026-10-07T08:00:00+00:00", "fit_start": "2026-09-01T00:00:00+00:00"}}
    _recipient()
    events, obs = ce._tit_events("XAUUSD", core, "mt5", chan.channel_settings())
    e = events[0]
    assert (e.event_type, e.tit_level, e.timeframe, e.direction) == ("TIT_DETECTED", "L3", "H8", "BULLISH")
    assert [l["id"] for l in e.metadata["layers"]] == ["L1", "L2", "L3", "L4"]
    assert e.metadata["htf_direction"] == "UPTREND" and e.metadata["parent_tf"] == "W" and e.metadata["counter_trend_tf"] == "H8"
    assert "countertrend" in e.metadata["reason"]
    assert _process(events, obs)["queued"] == 1
    core["H8"]["closed_at"] = "2026-10-07T16:00:00+00:00"
    assert _process(*ce._tit_events("XAUUSD", core, "mt5", chan.channel_settings()))["queued"] == 0  # still the same TiT episode
    state["view"] = {"available": False}
    _process(*ce._tit_events("XAUUSD", core, "mt5", chan.channel_settings()))  # condition reset → re-armed
    state["view"] = active
    core["H8"]["closed_at"] = "2026-10-08T00:00:00+00:00"
    assert _process(*ce._tit_events("XAUUSD", core, "mt5", chan.channel_settings()))["queued"] == 1

    from apps.api.app.notifications.worker import dispatch

    assert dispatch(NOW)["sent"] == 2
    msg = FakeSMTP.all_sent()[0]
    assert msg["Subject"] == "[Cacsms Traders] XAUUSD — TiT L3 Detected"
    body = _body(msg)
    assert "L1 W" in body and "L4 H1" in body and "MT5" in body


# ----- alert engine, queue and delivery -----


def test_channel_break_alert_is_queued_and_emailed(env):
    from apps.api.app.notifications.worker import dispatch

    _recipient()
    assert _process([_event()])["queued"] == 1
    assert dispatch(NOW)["sent"] == 1
    msg = FakeSMTP.all_sent()[0]
    assert msg["Subject"] == "[Cacsms Traders] EURUSD H1 — Bullish Channel Break"
    body = _body(msg)
    for label in ("CACSMS TRADERS", "Autonomous Market Intelligence Alert", "ALERT TYPE", "SYMBOL", "TIMEFRAME", "DIRECTION", "PRICE",
                  "EVENT LEVEL", "MARKET / STRUCTURAL CONTEXT", "EVENT TIME", "DATA PROVIDER", "This is an automated market intelligence alert."):
        assert label.lower() in body.lower()
    assert not TRADE_WORDS.search(body)
    with _db() as conn:
        ev = _store(conn).events()[0]
    assert ev["status"] == "SENT" and ev["sent_at"] and [h["status"] for h in ev["history"]][:3] == ["DETECTED", "VALIDATED", "QUEUED"]
    assert ev["deduplication_key"] == "CHANNEL_BREAK|EURUSD|H1|CH-TEST|BULLISH|2026-10-07T09:00"
    assert _audits("ALERT_DETECTED") and _audits("ALERT_QUEUED") and _audits("ALERT_SENT")


def test_channel_touch_email_subject(env):
    from apps.api.app.notifications.worker import dispatch

    _recipient()
    e = _event("CHANNEL_TOUCH", identity="LOWER", direction="BULLISH",
               metadata={"boundary": "LOWER", "label": "Lower Channel Touch", "boundary_level": 1.098, "touch_price": 1.0981, "tolerance": 0.00025,
                         "tolerance_atr": 0.25, "distance": 0.0001, "trend_direction": "UPTREND", "channel_status": "Valid · Testing Lower"})
    _process([e])
    dispatch(NOW)
    assert FakeSMTP.all_sent()[0]["Subject"] == "[Cacsms Traders] EURUSD H1 — Lower Channel Touch"


def test_duplicate_events_are_not_emailed_twice(env):
    from apps.api.app.notifications.worker import dispatch

    _recipient()
    first = _process([_event(), _event()])
    second = _process([_event()], now=NOW + timedelta(minutes=5))
    assert first["queued"] == 1 and first["duplicates"] == 1 and second["duplicates"] == 1
    dispatch(NOW)
    dispatch(NOW + timedelta(minutes=10))
    assert len(FakeSMTP.all_sent()) == 1


def test_restart_does_not_resend_processed_events(env):
    from apps.api.app.notifications import worker

    _recipient()
    _process([_event()])
    worker.dispatch(NOW)
    # A fresh process: new engine, new connections, same database.
    import importlib

    importlib.reload(worker)
    assert _process([_event()], now=NOW + timedelta(hours=1))["duplicates"] == 1
    assert worker.dispatch(NOW + timedelta(hours=1))["sent"] == 0
    assert len(FakeSMTP.all_sent()) == 1


def test_multiple_recipients_disabled_recipient_and_type_filter(env):
    from apps.api.app.notifications.worker import dispatch

    _recipient("a@example.com")
    _recipient("b@example.com", types=["CHANNEL_BREAK"])
    _recipient("off@example.com", enabled=False)
    _recipient("tit-only@example.com", types=["TIT_DETECTED"])
    _process([_event()])
    assert dispatch(NOW)["sent"] == 2
    assert sorted(m["To"] for m in FakeSMTP.all_sent()) == ["a@example.com", "b@example.com"]


def test_disabled_alert_type_is_suppressed(env):
    _recipient()
    with _db() as conn:
        store = _store(conn)
        s = store.settings()
        s["alert_types"]["CHANNEL_BREAK"] = False
        store.save_settings(s, "user-cacsms")
    report = _process([_event()])
    assert report["suppressed"] == 1 and report["queued"] == 0
    with _db() as conn:
        ev = _store(conn).events()[0]
        assert ev["status"] == "SUPPRESSED" and "disabled" in ev["status_reason"]
        assert conn.execute("SELECT COUNT(*) FROM notification_deliveries").fetchone()[0] == 0
    assert _audits("ALERT_SUPPRESSED")


def test_xauusd_toggle_and_timeframe_filter(env):
    _recipient()
    with _db() as conn:
        store = _store(conn)
        s = store.settings()
        s.update(xauusd_enabled=False, timeframes=["H8", "D1"])
        store.save_settings(s, None)
    report = _process([_event(symbol="XAUUSD", tf="H8"), _event(tf="H1", at="2026-10-07T08:00:00+00:00")])
    assert report["suppressed"] == 2
    with _db() as conn:
        reasons = sorted(e["status_reason"] for e in _store(conn).events())
    assert any("XAUUSD" in r for r in reasons) and any("H1" in r for r in reasons)


def test_temporary_smtp_failure_retries_with_backoff(env):
    from apps.api.app.notifications.worker import dispatch

    _recipient()
    _process([_event()])
    FakeSMTP.fail_send = [smtplib.SMTPServerDisconnected("Connection unexpectedly closed")]
    assert dispatch(NOW)["retry"] == 1
    with _db() as conn:
        d = conn.execute("SELECT status, next_attempt_at, attempt_count, failure_reason FROM notification_deliveries").fetchone()
        ev = _store(conn).events()[0]
    assert d["status"] == "RETRY_PENDING" and d["attempt_count"] == 1
    assert datetime.fromisoformat(d["next_attempt_at"]) == NOW + timedelta(minutes=1)
    assert ev["status"] == "RETRY_PENDING" and ev["failure_reason"]
    assert dispatch(NOW + timedelta(seconds=30))["sent"] == 0  # not due yet
    assert dispatch(NOW + timedelta(seconds=61))["sent"] == 1
    with _db() as conn:
        assert _store(conn).events()[0]["status"] == "SENT"


def test_retries_are_bounded_then_failed(env):
    from apps.api.app.notifications.worker import dispatch

    _recipient()
    with _db() as conn:
        store = _store(conn)
        s = store.settings()
        s["max_attempts"] = 3
        store.save_settings(s, None)
    _process([_event()])
    FakeSMTP.fail_send = [OSError("Network unreachable")] * 5
    t = NOW
    results = []
    for wait in (0, 1, 5):
        t += timedelta(minutes=wait, seconds=1)
        results.append(dispatch(t))
    assert [r["retry"] for r in results] == [1, 1, 0] and results[-1]["failed"] == 1
    with _db() as conn:
        d = conn.execute("SELECT status, attempt_count FROM notification_deliveries").fetchone()
        assert (d["status"], d["attempt_count"]) == ("FAILED", 3)
        assert _store(conn).events()[0]["status"] == "FAILED"
    assert dispatch(t + timedelta(hours=1))["sent"] == 0
    assert _audits("ALERT_FAILED")


def test_smtp_authentication_failure_fails_fast_and_is_redacted(env):
    from apps.api.app.notifications import smtp as smtp_mod
    from apps.api.app.notifications.worker import dispatch

    _recipient()
    _process([_event()])
    FakeSMTP.fail_login = smtplib.SMTPAuthenticationError(535, f"bad credentials for {SECRET}".encode())
    report = dispatch(NOW)
    assert report["failed"] == 1 and report["retry"] == 0
    with _db() as conn:
        d = conn.execute("SELECT status, error_kind, failure_reason FROM notification_deliveries").fetchone()
        health = smtp_mod.health(conn)
    assert (d["status"], d["error_kind"]) == ("FAILED", "AUTH")
    assert SECRET not in d["failure_reason"] and SECRET not in json.dumps(health)
    assert health["last_error_kind"] == "AUTH"


@pytest.mark.parametrize("provider,label", [("mt5", "MT5"), ("ctrader", "cTrader")])
def test_alerts_are_provider_independent(env, provider, label):
    from apps.api.app.notifications.worker import dispatch

    _recipient()
    _process([_event(provider=provider)])
    dispatch(NOW)
    with _db() as conn:
        assert _store(conn).events()[0]["provider"] == provider
    assert label in _body(FakeSMTP.all_sent()[0])


def test_tenant_isolation(env):
    from apps.api.app.notifications.worker import dispatch

    with _db() as conn:
        tenant_a = _tenant(conn)
        now = NOW.isoformat()
        conn.execute("INSERT INTO tenants(id,name,slug,status,reporting_currency,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                     ("tenant-other", "Other", "other", "ACTIVE", "USD", now, now))
    a = _recipient("a@example.com", tenant=tenant_a)
    _recipient("b@example.com", tenant="tenant-other")
    _process([_event()], tenant=tenant_a)
    dispatch(NOW)
    assert [m["To"] for m in FakeSMTP.all_sent()] == ["a@example.com"]
    with _db() as conn:
        other = _store(conn, "tenant-other")
        assert other.events() == [] and other.recipient(a["id"]) is None and other.stats("2000")["last_sent_at"] is None
        assert len(_store(conn, tenant_a).events()) == 1


def test_secret_redaction_and_encrypted_vault(env, monkeypatch):
    import base64

    from apps.api.app.notifications import smtp as smtp_mod
    from apps.api.app.routers.notifications import _overview

    assert SECRET not in smtp_mod.redact(f"auth {SECRET} / {base64.b64encode(SECRET.encode()).decode()}")
    monkeypatch.setenv("SMTP_ENCRYPTION_KEY", "server-side-key")
    stored = "zyxw vuts rqpo nmlk"
    with _db() as conn:
        smtp_mod.store_password(conn, stored)
        raw = conn.execute("SELECT value_json FROM system_settings WHERE key=?", (smtp_mod.SECRET_KEY,)).fetchone()[0]
        cfg = smtp_mod.smtp_config(conn)
        overview = json.dumps(_overview(conn, {"id": "user-cacsms", "is_platform_admin": 1}, _tenant(conn)), default=str)
    assert stored.replace(" ", "") not in raw and cfg.password == stored.replace(" ", "") and cfg.password_source == "database"
    for secret in (SECRET, stored.replace(" ", ""), APP_PASSWORD):
        assert secret not in overview
    assert '"password_configured": true' in overview


def test_scanner_survives_notification_failures(monkeypatch):
    from apps.api.app.market.scanner_engine import MarketScannerEngine
    from apps.api.app.notifications import worker

    def boom(*a, **k):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(worker, "publish_channel_events", boom)
    MarketScannerEngine()._publish_events(NOW)  # must not raise


def test_email_settings_api_never_returns_the_password(env, monkeypatch):
    from fastapi.testclient import TestClient

    for k in ("STRENGTH_ENGINE_ENABLED", "AI_OUTLOOK_SCHEDULER_ENABLED", "NOTIFICATIONS_ENABLED", "MARKET_SCANNER_ENABLED"):
        monkeypatch.setenv(k, "0")
    from apps.api.app.main import app

    with TestClient(app) as client:
        r = client.post("/api/auth/login", json={"username": "cacsms", "password": "TestPass!123"})
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        with _db() as conn:
            tenant = _tenant(conn)
        overview = client.get(f"/api/notifications/email?tenant_id={tenant}", headers=h)
        assert overview.status_code == 200 and SECRET not in overview.text
        added = client.post(f"/api/notifications/email/recipients?tenant_id={tenant}", headers=h,
                            json={"email": "Desk@Example.com", "name": "Desk", "alert_types": ["CHANNEL_BREAK", "TIT_DETECTED"]})
        assert added.status_code == 200 and added.json()["recipients"][0]["email"] == "desk@example.com"
        smtp = client.put(f"/api/notifications/email/smtp?tenant_id={tenant}", headers=h,
                          json={"enabled": True, "host": "smtp.gmail.com", "port": 587, "security": "starttls", "username": "pipsengine@gmail.com",
                                "from_email": "pipsengine@gmail.com", "from_name": "Cacsms Traders Desk"})
        assert smtp.status_code == 200 and smtp.json()["smtp"]["from_name"] == "Cacsms Traders Desk" and SECRET not in smtp.text
        test = client.post(f"/api/notifications/email/test?tenant_id={tenant}", headers=h, json={"to": []})
        assert test.status_code == 200 and test.json()["result"]["status"] == "SENT" and SECRET not in test.text
    audits = _audits("SMTP_CONFIGURATION_UPDATED")
    assert audits and all(SECRET not in json.dumps(a) for a in audits)


def test_bell_inbox_counts_unread_and_skips_suppressed(env, monkeypatch):
    from fastapi.testclient import TestClient

    for k in ("STRENGTH_ENGINE_ENABLED", "AI_OUTLOOK_SCHEDULER_ENABLED", "NOTIFICATIONS_ENABLED", "MARKET_SCANNER_ENABLED"):
        monkeypatch.setenv(k, "0")
    _recipient()
    with _db() as conn:
        store = _store(conn)
        s = store.settings()
        s["alert_types"]["CHANNEL_TOUCH"] = False
        store.save_settings(s, "user-cacsms")
    _process([_event()])
    _process([_event("CHANNEL_TOUCH", identity="LOWER")], now=NOW + timedelta(minutes=1))
    from apps.api.app.main import app

    with TestClient(app) as client:
        r = client.post("/api/auth/login", json={"username": "cacsms", "password": "TestPass!123"})
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        with _db() as conn:
            tenant = _tenant(conn)
        url = "/api/notifications/inbox"

        def inbox(since, headers=h):
            return client.get(url, headers=headers, params={"tenant_id": tenant, "since": since})

        first = inbox((NOW - timedelta(hours=1)).isoformat()).json()
        assert first["unread"] == 1 and [i["event_type"] for i in first["items"]] == ["CHANNEL_BREAK"]
        item = first["items"][0]
        assert item["unread"] and item["label"] == "Channel Break" and item["symbol"] == "EURUSD" and "metadata_json" not in item
        read = inbox(item["detected_at"]).json()
        assert read["unread"] == 0 and not read["items"][0]["unread"]
        _process([_event(at="2026-10-07T10:00:00+00:00")], now=NOW + timedelta(hours=1))
        assert inbox(item["detected_at"]).json()["unread"] == 1
        with _db() as conn:
            store = _store(conn)
            s = store.settings()
            s["email_enabled"] = False
            store.save_settings(s, "user-cacsms")
        _process([_event("TIT_DETECTED", at="2026-10-07T11:00:00+00:00")], now=NOW + timedelta(hours=2))
        latest = inbox(item["detected_at"]).json()
        assert latest["unread"] == 2 and latest["items"][0]["event_type"] == "TIT_DETECTED" and latest["items"][0]["status"] == "SUPPRESSED"
        assert inbox("yesterday").status_code == 400
        client.cookies.clear()
        assert inbox(item["detected_at"], headers={}).status_code == 401

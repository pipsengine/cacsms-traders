from datetime import timedelta

from test_notifications import NOW, SECRET, TRADE_WORDS, FakeSMTP, _body, _db, _recipient, _store, env  # noqa: F401

RUN = {"id": "run-1", "analysis_date": "2026-10-06", "origin": "LIVE"}
COUNTS = {"published": 3, "qualified": 2, "insufficient": 1, "failed": 0}
ON_TIME = "2026-10-06T21:20:00+00:00"
LATE = "2026-10-07T01:10:00+00:00"


def _outlook(symbol, rank, direction="BULLISH", qualified=True):
    return {"symbol": symbol, "digits": 5, "expected_direction": direction, "confidence": {"primary": 72},
            "expected_next_move": "Pullback into the ERZ, then continuation", "erz": {"lo": 1.1000, "hi": 1.1010},
            "targets": [{"price": 1.1080, "label": "Target 1"}, {"price": 1.1120, "label": "Target 2"}],
            "invalidation": {"price": 1.0960}, "opportunity_score": 81.5, "qualified": qualified, "opportunity_rank": rank}


OUTLOOKS = [_outlook("GBPUSD", 2, "BEARISH"), _outlook("EURUSD", 1), _outlook("AUDCAD", None, qualified=False)]


def _publish(run=RUN, published_at=ON_TIME, late=False, now=NOW):
    from apps.api.app.notifications.outlook_alert import publish_outlook_published

    with _db() as conn:
        return publish_outlook_published(conn, run, OUTLOOKS, COUNTS, published_at, late, now)


def _settings(**changes):
    with _db() as conn:
        store = _store(conn)
        s = store.settings()
        for key, value in changes.items():
            if key == "alert_type_off":
                s["alert_types"][value] = False
            else:
                s[key] = value
        store.save_settings(s, "user-cacsms")


def test_analysis_complete_email_lists_top_opportunities(env, monkeypatch):
    from apps.api.app.notifications.worker import dispatch

    monkeypatch.setenv("APP_PUBLIC_URL", "https://cacsms-traders.vercel.app/")
    _recipient()
    assert _publish()["queued"] == 1
    assert dispatch(NOW)["sent"] == 1
    msg = FakeSMTP.all_sent()[0]
    assert msg["Subject"] == "[Cacsms Traders] AI Analysis Complete — Outlook for Wed 07 Oct 2026 (2 qualified opportunities)"
    body = _body(msg)
    assert "On time" in body and "Late" not in body
    assert body.index("EURUSD") < body.index("GBPUSD") and "AUDCAD" not in body
    for text in ("Bullish (72% confidence)", "Bearish (72% confidence)", "1.10000", "1.10800", "1.09600", "Open AI Market Outlook",
                 "https://cacsms-traders.vercel.app/#/ai-market-outlook/daily"):
        assert text in body
    assert not TRADE_WORDS.search(body) and SECRET not in body
    with _db() as conn:
        ev = _store(conn).events()[0]
    assert ev["event_type"] == "AI_OUTLOOK_PUBLISHED" and ev["symbol"] == "ALL" and ev["status"] == "SENT"
    assert ev["metadata"]["opportunities"][0]["symbol"] == "EURUSD" and ev["metadata"]["late"] is False


def test_rerun_of_the_same_analysis_day_is_not_emailed_twice(env):
    from apps.api.app.notifications.worker import dispatch

    _recipient()
    assert _publish()["queued"] == 1
    again = _publish({**RUN, "id": "run-2"}, now=NOW + timedelta(hours=2))
    assert again["queued"] == 0 and again["duplicates"] == 1
    dispatch(NOW + timedelta(hours=3))
    assert len(FakeSMTP.all_sent()) == 1
    assert _publish({**RUN, "id": "run-3", "analysis_date": "2026-10-07"})["queued"] == 1


def test_late_analysis_is_still_sent_and_flagged(env):
    from apps.api.app.notifications.worker import dispatch

    _recipient()
    _publish(published_at=LATE, late=True)
    dispatch(NOW)
    msg = FakeSMTP.all_sent()[0]
    assert msg["Subject"].startswith("[Cacsms Traders] [Late] AI Analysis Complete")
    assert "Late — completed after market open" in _body(msg)


def test_replay_runs_never_alert(env):
    _recipient()
    assert _publish({**RUN, "origin": "REPLAY"}) == {"skipped": "not_live"}
    with _db() as conn:
        assert _store(conn).events() == []


def test_alert_type_toggle_suppresses_but_symbol_and_timeframe_filters_do_not(env):
    _recipient()
    _settings(symbols=["XAUUSD"], timeframes=["H1"], xauusd_enabled=False)
    assert _publish()["queued"] == 1
    _settings(alert_type_off="AI_OUTLOOK_PUBLISHED")
    report = _publish({**RUN, "analysis_date": "2026-10-07"})
    assert report["suppressed"] == 1 and report["queued"] == 0


def test_recipient_type_filter_applies(env):
    from apps.api.app.notifications.worker import dispatch

    _recipient("all@example.com")
    _recipient("outlook@example.com", types=["AI_OUTLOOK_PUBLISHED"])
    _recipient("breaks@example.com", types=["CHANNEL_BREAK"])
    _publish()
    assert dispatch(NOW)["sent"] == 2
    assert sorted(m["To"] for m in FakeSMTP.all_sent()) == ["all@example.com", "outlook@example.com"]


def test_alert_failure_never_breaks_the_outlook_run(env, monkeypatch):
    from apps.api.app.market.outlook.service import OutlookService
    from apps.api.app.notifications import outlook_alert

    def boom(*a, **k):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(outlook_alert, "publish_outlook_published", boom)
    with _db() as conn:
        OutlookService()._notify_published(conn, RUN, OUTLOOKS, COUNTS, ON_TIME, False)

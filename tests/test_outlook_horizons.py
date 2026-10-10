"""Multi-horizon outlook: broker-close identity, shared ordering, Gold M15, alerts and recovery."""
from datetime import datetime, timedelta, timezone

from apps.api.app.market.outlook import calendar as cal
from apps.api.app.market.outlook.horizons import coincident, gold_progress, ordered, run_key, trim_bars
from apps.api.app.market.outlook.lifecycle import lifecycle_for
from apps.api.app.market.scanner_analytics import Bar
from apps.api.app.notifications.engine import dedup_key
from apps.api.app.notifications.outlook_alert import outlook_event
from tests.test_ai_outlook import CUTOFF, DAY, market

NOW = CUTOFF + timedelta(hours=2)


def _bar(t: datetime, price: float, span_high: float, span_low: float) -> Bar:
    return Bar(t, price, max(price, span_high), min(price, span_low), price, 10)


def _outlook(**extra):
    base = {
        "anchor": CUTOFF.isoformat(),
        "expected_direction": "BULLISH",
        "price": 1.1000,
        "qualified": True,
        "horizon": "H8",
        "volatility": {"atr": 0.01},
        "erz": {"lo": 1.0960, "hi": 1.0980, "mid": 1.0970, "label": "1.0960 – 1.0980", "price_inside": False, "distance_atr": 1.2},
        "targets": [{"price": 1.1050}, {"price": 1.1100}],
        "invalidation": {"price": 1.0940},
        "range_scenario": {"range": [1.0940, 1.1050]},
        "confidence": {"primary": 64.0, "calibration": {"raw": 66.0}},
        "confirmation_sequence": [
            {"step": 1, "key": "REACTION", "label": "Reaction", "condition": {"type": "touch_zone", "lo": 1.0960, "hi": 1.0980}},
            {"step": 2, "key": "BOS", "label": "H1 BOS", "condition": {"type": "structure", "tf": "H1", "kind": "BOS", "dir": 1}},
            {"step": 3, "key": "RETEST", "label": "Retest", "condition": {"type": "retest", "lo": 1.0960, "hi": 1.0980, "dir": 1}},
        ],
    }
    base.update(extra)
    return base


def test_coincident_closes_run_monthly_then_weekly_then_daily_then_h8():
    assert ordered(["H8", "DAILY", "MONTHLY", "WEEKLY"]) == ["MONTHLY", "WEEKLY", "DAILY", "H8"]
    same = CUTOFF
    closes = {"H8": same, "DAILY": same + timedelta(minutes=2), "WEEKLY": same + timedelta(minutes=1)}
    assert coincident(closes, timedelta(minutes=5))
    assert not coincident({"H8": same, "DAILY": same + timedelta(hours=3)}, timedelta(minutes=5))


def test_run_key_is_idempotent_and_distinct_per_horizon():
    assert run_key("H8", CUTOFF) == run_key("H8", CUTOFF)
    assert run_key("H8", CUTOFF) != run_key("WEEKLY", CUTOFF)
    assert run_key("H8", CUTOFF) != run_key("H8", CUTOFF + timedelta(hours=8))
    assert not run_key("WEEKLY", CUTOFF).startswith(DAY.isoformat())


def test_shared_snapshot_trim_drops_bars_that_open_at_the_later_close():
    later = CUTOFF + timedelta(hours=8)
    bars = {"XAUUSD": {"H8": [_bar(CUTOFF - timedelta(hours=8), 2300, 2310, 2290), _bar(CUTOFF, 2310, 2320, 2300)]}}
    trimmed = trim_bars(bars, CUTOFF)
    assert [b.t for b in trimmed["XAUUSD"]["H8"]] == [CUTOFF - timedelta(hours=8)]
    assert trim_bars(bars, later)["XAUUSD"]["H8"][-1].t == CUTOFF


def test_gold_m15_confirmation_does_not_authorise_or_skip_h1():
    m15 = [_bar(CUTOFF + timedelta(minutes=15), 1.0972, 1.0990, 1.0962)]
    m15[0] = Bar(m15[0].t, 1.0964, 1.0990, 1.0961, 1.0976, 10)
    waiting = gold_progress(_outlook(), [], m15, NOW, CUTOFF + timedelta(hours=8))
    assert waiting["m15"]["confirmed"] is True
    assert waiting["lifecycle"] == "CONFIRMATION_PENDING"
    assert waiting["lifecycle"] != "AUTHORIZED"
    assert waiting["force_trade"] is False

    broken = [_bar(CUTOFF + timedelta(hours=1), 1.0930, 1.0940, 1.0920)]
    invalidated = gold_progress(_outlook(), broken, [], NOW, CUTOFF + timedelta(hours=8))
    assert invalidated["lifecycle"] == "INVALIDATED"

    expired = gold_progress(_outlook(), [], [], NOW, NOW - timedelta(minutes=1))
    assert expired["lifecycle"] == "EXPIRED"
    assert lifecycle_for(_outlook(qualified=False), {"status": "AWAITING_REACTION", "steps": [], "system_action": {}}, NOW, None) == "NO_OPPORTUNITY"


def test_weekly_sch_stays_off_the_price_pane():
    from apps.api.app.market.outlook.config import outlook_settings
    from apps.api.app.market.outlook.engine import build_outlook, validate
    from apps.api.app.market.outlook.horizons import decorate
    from apps.api.app.market.scanner_engine import analysis_cores

    bars = market()
    quality = validate(bars, CUTOFF, cal.d1_open_for(DAY))
    outlook = build_outlook("EURUSD", analysis_cores(bars, h8bb=False), bars["D1"][-1].c, CUTOFF, None, quality, {}, outlook_settings(),
                            analysis_date=DAY.isoformat(), snapshot_id="snap-weekly")
    decorate(outlook, "WEEKLY", bars)
    assert outlook["horizon"] == "WEEKLY"
    assert outlook["sch"]["pane"] == "below_price" and outlook["sch"]["only"] == "W"
    assert all(a.get("type") != "sch" for a in outlook["chart_annotations"])
    assert outlook["weekly"]["intact_range"] is not outlook["weekly"]["structural_breakout"] or not outlook["weekly"].get("fractal_state")
    monthly = {"conclusion": "Higher-timeframe bias holds.", "evidence_for": [], "evidence_against": [], "data_quality": {"checks": []}}
    decorate(monthly, "MONTHLY", {})
    assert monthly["strategic"]["overrides_shorter"] is False


def test_next_analysis_follows_each_horizon_clock():
    from apps.api.app.market.outlook.horizons import project_next_close

    now = datetime(2026, 10, 10, 8, 25, tzinfo=timezone.utc)
    weekly = project_next_close(
        [datetime(2026, 10, 4, tzinfo=timezone.utc), datetime(2026, 9, 27, tzinfo=timezone.utc)], "WEEKLY", now)
    monthly = project_next_close(
        [datetime(2026, 10, 1, tzinfo=timezone.utc), datetime(2026, 9, 1, tzinfo=timezone.utc)], "MONTHLY", now)
    h8 = [datetime(2026, 10, 9, hour, tzinfo=timezone.utc) for hour in (0, 8, 16)]
    h8 += [datetime(2026, 10, 8, hour, tzinfo=timezone.utc) for hour in (0, 8, 16)]
    h8.append(datetime(2026, 10, 5, 8, tzinfo=timezone.utc))
    gold = project_next_close(h8, "H8", now)
    assert weekly == datetime(2026, 10, 11, tzinfo=timezone.utc)
    assert monthly == datetime(2026, 11, 1, tzinfo=timezone.utc)
    assert gold == datetime(2026, 10, 12, 8, tzinfo=timezone.utc)
    assert weekly != monthly != gold


def test_weekend_h8_and_h1_stay_fresh_on_a_weekly_close():
    from apps.api.app.market.outlook.engine import validate

    sunday = datetime(2026, 10, 4, tzinfo=timezone.utc)
    friday_h8_open = datetime(2026, 10, 2, 8, tzinfo=timezone.utc)

    def series(n, end, step):
        start = end - step * (n - 1)
        return [Bar(start + step * i, 1.1, 1.11, 1.09, 1.1, 1) for i in range(n)]

    bars = {
        "MN": series(24, datetime(2026, 9, 1, tzinfo=timezone.utc), timedelta(days=31)),
        "W1": series(52, datetime(2026, 9, 27, tzinfo=timezone.utc), timedelta(days=7)),
        "D1": series(120, datetime(2026, 10, 2, tzinfo=timezone.utc), timedelta(days=1)),
        "H8": series(90, friday_h8_open, timedelta(hours=8)),
        "H1": series(120, datetime(2026, 10, 2, 20, tzinfo=timezone.utc), timedelta(hours=1)),
    }
    expected = datetime(2026, 10, 2, tzinfo=timezone.utc)
    weekly = validate(bars, sunday, expected, "WEEKLY")
    daily = validate(bars, sunday, expected, "DAILY")
    weekly_h8 = next(c for c in weekly["checks"] if c["tf"] == "H8")
    daily_h8 = next(c for c in daily["checks"] if c["tf"] == "H8")
    assert weekly_h8["fresh"] is True and weekly["status"] == "OK"
    assert daily_h8["fresh"] is False


def test_published_alert_dedup_key_is_stable_per_close_and_lifecycle():
    counts = {"published": 1, "qualified": 0, "insufficient": 0, "failed": 0}
    daily = {"id": "run-1", "analysis_date": DAY.isoformat(), "horizon": "DAILY", "close_at": CUTOFF.isoformat(), "origin": "LIVE"}
    first = outlook_event(daily, [], counts, NOW.isoformat(), False, "mt5")
    second = outlook_event(daily, [], counts, NOW.isoformat(), False, "mt5")
    assert dedup_key(first) == dedup_key(second)
    h8 = {**daily, "horizon": "H8", "analysis_date": run_key("H8", CUTOFF), "close_at": CUTOFF.isoformat()}
    assert dedup_key(outlook_event(h8, [], counts, NOW.isoformat(), False, "mt5")) != dedup_key(first)


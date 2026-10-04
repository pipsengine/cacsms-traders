from datetime import datetime, timedelta, timezone

from apps.api.app.market.pair_relationships import (
    alignment,
    classify_dynamics,
    classify_relationship,
    pair_relationships,
)
from apps.api.app.market.relationship_analysis import analyze_pair, classify_state, diff_series, htf_ltf
from apps.api.app.market.strength_history import (
    build_history,
    coverage,
    crossover_events,
    currency_stats,
    momentum,
    reversal_events,
)
from apps.api.app.market.strength_intel_config import (
    ANALYSIS_TIMEFRAMES,
    history_thresholds,
    relationship_thresholds,
)

T0 = datetime(2026, 10, 1, tzinfo=timezone.utc)
AVG = {"USD": 70.0, "JPY": 60.0, "CHF": 55.0, "EUR": 50.0, "GBP": 46.0, "CAD": 40.0, "AUD": 35.0, "NZD": 30.0}


def _scores(avg=AVG, tf_value=None):
    return {c: {"AVG": v, **{tf: (tf_value(c, tf) if tf_value else v) for tf in ANALYSIS_TIMEFRAMES}} for c, v in avg.items()}


def _series(values, step_min=5):
    return [(T0 + timedelta(minutes=i * step_min), float(v)) for i, v in enumerate(values)]


def test_relationship_classes_follow_central_thresholds():
    t = relationship_thresholds()
    assert classify_relationship(t.strong_divergence, t)["key"] == "STRONG_DIVERGENCE"
    assert classify_relationship(t.divergence, t)["key"] == "DIVERGENCE"
    assert classify_relationship(t.moderate, t)["key"] == "MODERATE"
    assert classify_relationship(t.moderate - 0.1, t)["key"] == "BALANCED"


def test_threshold_env_override(monkeypatch):
    monkeypatch.setenv("PAIR_RELATIONSHIP_THRESHOLDS", "40,20,10")
    assert classify_relationship(35.0)["key"] == "DIVERGENCE"
    monkeypatch.setenv("PAIR_RELATIONSHIP_THRESHOLDS", "1,2,3")  # not descending → defaults
    assert relationship_thresholds().strong_divergence == 30.0


def test_all_28_pairs_ranked_by_absolute_differential():
    rows = pair_relationships(_scores())
    assert len(rows) == 28
    assert rows[0]["pair"] == "NZDUSD" and rows[0]["differential"] == -40.0
    assert [r["abs_differential"] for r in rows] == sorted((r["abs_differential"] for r in rows), reverse=True)
    eurusd = next(r for r in rows if r["pair"] == "EURUSD")
    assert eurusd["base_strength"] == 50.0 and eurusd["quote_strength"] == 70.0
    assert eurusd["dominant"] == "QUOTE"
    assert eurusd["dynamics"]["key"] == "NO_HISTORY"
    assert not any(k in str(rows).upper() for k in ("BUY", "SELL"))


def test_dynamics_expanding_contracting_reversing():
    assert classify_dynamics(20.0, 15.0)["key"] == "EXPANDING"
    assert classify_dynamics(-12.0, -20.0)["key"] == "CONTRACTING"
    assert classify_dynamics(-10.0, 12.0)["key"] == "REVERSING"
    assert classify_dynamics(10.4, 10.0)["key"] == "STABLE"


def test_alignment_counts_timeframes_matching_composite():
    by_tf = {tf: 10.0 for tf in ANALYSIS_TIMEFRAMES}
    by_tf["M1"] = by_tf["M5"] = -10.0
    a = alignment(10.0, by_tf)
    assert (a["aligned"], a["total"], a["pct"], a["key"], a["direction"]) == (8, 10, 80.0, "ALIGNED", "BASE")
    assert alignment(0.5, by_tf)["key"] == "NEUTRAL"


def test_htf_ltf_disagreement():
    by_tf = {"YTD": 20, "Q": 15, "MN": 10, "W": 8, "D1": 5, "H8": -5, "H1": -8, "M15": -10, "M5": -6, "M1": -4}
    r = htf_ltf(by_tf, relationship_thresholds())
    assert (r["key"], r["htf"], r["ltf"]) == ("DISAGREE", "BASE", "QUOTE")


def test_state_classification():
    t = relationship_thresholds()
    assert classify_state(25.0, 20.0, None, t)["key"] == "EXPANDING_DIVERGENCE"
    assert classify_state(25.0, 30.0, None, t)["key"] == "CONTRACTING_DIVERGENCE"
    assert classify_state(12.0, 16.0, None, t)["key"] == "CONVERGENCE"
    assert classify_state(3.0, 2.5, None, t)["key"] == "EQUILIBRIUM"
    assert classify_state(-12.0, 10.0, None, t)["key"] == "REVERSAL"
    assert classify_state(25.0, 25.2, 0.95, t)["key"] == "PERSISTENT_DIVERGENCE"
    assert classify_state(25.0, 25.2, 0.4, t)["key"] == "STABLE_DIVERGENCE"


def test_history_stats_trend_and_extremes():
    t = history_thresholds()
    s = currency_stats("USD", _series([50, 55, 62, 58, 60]), t)
    assert (s["current"], s["start"], s["change"], s["high"], s["low"]) == (60.0, 50.0, 10.0, 62.0, 50.0)
    assert s["change_pct"] == 20.0 and s["trend"]["key"] == "STRENGTHENING" and s["average"] == 57.0
    assert currency_stats("EUR", [], t) == {"currency": "EUR", "available": False}


def test_momentum_accelerating_and_insufficient():
    t = history_thresholds()
    assert momentum(_series([50, 50.5, 51, 52, 55, 60, 66]), t)["key"] == "ACCELERATING"
    assert momentum(_series([50, 58, 64, 66, 67, 67.2, 67.3]), t)["key"] == "DECELERATING"
    assert momentum(_series([50, 51]), t)["key"] == "INSUFFICIENT"


def test_reversals_and_crossovers():
    rev = reversal_events("USD", _series([50, 56, 62, 55, 54, 60, 66]), 5.0)
    assert [e["direction"] for e in rev] == ["TURNED_DOWN", "TURNED_UP"]
    assert rev[0]["score"] == 62.0
    cross = crossover_events({"USD": _series([60, 55, 48]), "EUR": _series([50, 52, 56])}, 1.0)
    assert len(cross) == 1 and cross[0]["leader"] == "EUR" and cross[0]["laggard"] == "USD"


def test_coverage_flags_incomplete_history():
    end = T0 + timedelta(days=7)
    c = coverage(T0, end, T0 + timedelta(days=6), 300)
    assert not c["complete"] and round(c["pct"]) == 14
    assert coverage(T0, end, T0, 300)["complete"]
    assert coverage(T0, end, None, 300) == {"complete": False, "pct": 0.0, "first_available": None}


def test_build_history_never_fills_missing_currencies():
    series = {"USD": _series([50, 52, 54]), "EUR": _series([50, 49])}
    out = build_history(series, period="24H", start=T0, end=T0 + timedelta(hours=1), first_available=T0, snapshot_interval_s=300)
    assert out["chart"]["values"]["EUR"][-1] is None
    gbp = next(s for s in out["currencies"] if s["currency"] == "GBP")
    assert gbp["available"] is False


def test_analyze_pair_produces_matrix_and_interpretation_without_signals():
    scores = _scores()
    reference = _scores({**AVG, "EUR": 52.0, "USD": 66.0})
    hist = {"AVG": diff_series(_series([60, 62, 66, 68]), _series([50, 50, 50, 50]))}
    out = analyze_pair("EURUSD", scores, reference, hist, lookback_minutes=60)
    assert out is not None
    assert len(out["matrix"]) == len(ANALYSIS_TIMEFRAMES)
    assert out["relationship"]["differential"] == -20.0
    assert out["summary"]["state"]["key"] == "EXPANDING_DIVERGENCE"
    assert out["summary"]["base_direction"]["key"] == "WEAKENING"
    assert out["summary"]["quote_direction"]["key"] == "STRENGTHENING"
    text = " ".join(out["interpretation"]).upper()
    assert "BUY" not in text and "SELL" not in text

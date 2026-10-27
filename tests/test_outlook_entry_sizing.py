from apps.api.app.execution.outlook_entry import outlook_price_ready, outlook_size_reference, outlook_volume_plan


def _payload():
    return {
        "expected_direction": "BEARISH",
        "erz": {"lo": 1.5779, "hi": 1.5805, "mid": 1.5792, "distance_atr": 1.01, "price_inside": False},
        "invalidation": {"price": 1.5856},
    }


def test_outside_erz_blocks_send():
    ok, reason = outlook_price_ready(_payload(), 1.562)
    assert not ok and reason.startswith("PRICE_OUTSIDE_ERZ")


def test_bearish_sizes_from_erz_high():
    assert outlook_size_reference(_payload(), "BEARISH") == 1.5805


def test_volume_plan_fails_far_from_zone():
    spec = {
        "tick_size": "0.00001", "tick_value": "948.92", "volume_min": "0.01", "volume_max": "60",
        "volume_step": "0.01", "point": "0.00001", "spread_points": "0", "commission_per_lot": "0",
        "stops_level_points": 0,
    }
    ok, volume, err = outlook_volume_plan(
        payload=_payload(), direction="BEARISH", live_price=1.562, stop=1.5856, equity=50_000,
        risk_pct=1, spec=spec, tick_value=948.92, profile={"max_trade_risk_pct": 1},
    )
    assert not ok and volume is None and err.startswith("PRICE_OUTSIDE_ERZ")

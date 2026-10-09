def test_unified_status_synchronizing_when_connected_not_ready(monkeypatch):
    from apps.api.app.market.unified_status import compute_platform_status

    class _Conn:
        def execute(self, *args, **kwargs):
            class _Row:
                def fetchone(self):
                    return None

            return _Row()

    def fake_context(conn):
        return {
            "active_provider": "mt5",
            "market_data_ready": False,
            "market_data_scope": {"tenant_id": "t1", "account_id": "srv/1"},
            "providers": {"mt5": {"connected": True, "healthy": True, "context": {"market_data_ready": False}}},
        }

    monkeypatch.setattr("apps.api.app.market.market_data.market_context", fake_context)
    monkeypatch.setattr("apps.api.app.market.market_data.ensure_active_provider_snapshot", lambda c: "snap")
    monkeypatch.setattr("apps.api.app.market.market_data.configuration", lambda c: {"account_id": "srv/1"})
    monkeypatch.setattr(
        "apps.api.app.market.strength_engine.get_strength_engine",
        lambda: type("E", (), {"engine_meta": lambda self: {"pairs_loaded": 27, "engine_state": "INCOMPLETE_BASKET"}})(),
    )
    ps = compute_platform_status(_Conn())
    assert ps["provider_phase"] == "SYNCHRONIZING"
    assert ps["strength_pairs_loaded"] == 27
    assert ps["connections_label"] == "Syncing"

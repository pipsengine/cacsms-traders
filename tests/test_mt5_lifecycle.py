from apps.api.app.domain.mt5_lifecycle import compute_connection_lifecycle


def test_lifecycle_not_configured_without_path():
    out = compute_connection_lifecycle(
        {"status": "DISCONNECTED"},
        {"session_status": "DISCONNECTED", "terminal_path": ""},
        None,
    )
    assert out["gateway_phase"] == "NOT_CONFIGURED"


def test_lifecycle_synchronizing_when_connected_and_incomplete_basket():
    out = compute_connection_lifecycle(
        {"status": "CONNECTED"},
        {"session_status": "CONNECTED", "terminal_path": "C:\\MT5\\terminal64.exe"},
        {"market_data_ready": True, "engine_state": "INCOMPLETE_BASKET", "pairs_loaded": 0, "pairs_total": 28},
    )
    assert out["gateway_phase"] == "CONNECTED"
    assert out["market_sync_phase"] == "SYNCHRONIZING"
    assert out["overall_phase"] == "SYNCHRONIZING"


def test_lifecycle_waiting_provider_when_mt5_disconnected():
    out = compute_connection_lifecycle(
        {"status": "DISCONNECTED"},
        {"session_status": "DISCONNECTED", "terminal_path": "C:\\MT5\\terminal64.exe"},
        {"market_data_ready": False, "engine_state": "SYNCING"},
    )
    assert out["market_sync_phase"] == "WAITING_PROVIDER"
    assert out["overall_phase"] == "DISCONNECTED"

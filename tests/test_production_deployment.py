import importlib
from pathlib import Path


def test_production_cors_defaults_are_cloud_only(monkeypatch):
    import apps.api.app.core.config as config_module

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("WEB_ORIGINS", "https://cacsms-traders.vercel.app")
    monkeypatch.delenv("WEB_ORIGIN", raising=False)
    monkeypatch.delenv("API_ORIGIN", raising=False)

    importlib.reload(config_module)
    origins = config_module.cors_origins()

    assert "https://cacsms-traders.vercel.app" in origins
    assert "http://localhost:5173" not in origins
    assert "http://127.0.0.1:5173" not in origins


def test_cloud_runtime_binds_globally(monkeypatch):
    run_api = Path(__file__).resolve().parents[1] / "scripts" / "run_api.py"
    text = run_api.read_text(encoding="utf-8")

    assert '0.0.0.0' in text
    assert 'APP_HOST' in text

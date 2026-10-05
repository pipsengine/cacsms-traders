import importlib

import pytest


def test_missing_production_database_raises_database_unavailable(monkeypatch):
    import apps.api.app.core.database as database_module

    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.setenv('DATABASE_PATH', 'C:/tmp/cacsms/production-missing/db.sqlite')
    monkeypatch.delenv('DATABASE_ALLOW_CREATE', raising=False)

    importlib.reload(database_module)

    with pytest.raises(database_module.DatabaseUnavailable):
        database_module.connect()

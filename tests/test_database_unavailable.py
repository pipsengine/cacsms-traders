import importlib
from types import SimpleNamespace

import pytest


def test_missing_production_database_raises_database_unavailable(monkeypatch):
    import apps.api.app.core.database as database_module

    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.setenv('DATABASE_PATH', 'C:/tmp/cacsms/production-missing/db.sqlite')
    monkeypatch.delenv('DATABASE_ALLOW_CREATE', raising=False)

    importlib.reload(database_module)

    with pytest.raises(database_module.DatabaseUnavailable):
        database_module.connect()


def test_production_sql_uses_postgres_placeholders_and_conflicts(monkeypatch):
    import apps.api.app.core.database as database_module

    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.setenv('DATABASE_URL', 'postgresql://example.invalid/database')

    sql, params = database_module._rewrite_production_sql(
        'INSERT OR IGNORE INTO role_permissions(role_id,permission_id) VALUES(?,?)',
        ('role', 'permission'),
    )

    assert sql.endswith('ON CONFLICT DO NOTHING')
    assert '%s' in sql
    assert params == ('role', 'permission')


def test_postgres_connection_uses_named_rows(monkeypatch):
    import apps.api.app.core.database as database_module

    row_factory = object()
    raw_connection = object()
    connect_calls = []

    def connect(url, **kwargs):
        connect_calls.append((url, kwargs))
        return raw_connection

    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.setenv('DATABASE_URL', 'postgresql://example.invalid/database')
    monkeypatch.setattr(database_module, 'dict_row', row_factory)
    monkeypatch.setattr(database_module, 'psycopg', SimpleNamespace(connect=connect))

    conn = database_module.connect()

    assert conn._raw is raw_connection
    assert connect_calls[0][1]['row_factory'] is row_factory

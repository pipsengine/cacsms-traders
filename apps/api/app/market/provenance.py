"""Read history within an immutable analytical scope, never across provider changes."""
import re
import sqlite3
from uuid import UUID


def active_snapshot(conn):
    if isinstance(conn, sqlite3.Connection) or getattr(conn, 'provider', None) == 'sqlite':
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='mi_provider_snapshot'").fetchone():
            return None
    return conn.execute('SELECT * FROM mi_provider_snapshot WHERE finalized_at IS NULL LIMIT 1').fetchone()


def scoped_query(conn, sql, params=(), snapshot_id=None):
    scope = active_snapshot(conn) if snapshot_id is None else None
    identifier = snapshot_id or (scope['id'] if scope else None)
    if identifier:
        # UUID validation makes the generated SQL literal safe, regardless of query placeholder order.
        identifier = str(UUID(identifier))
        for table, kind in (('mi_strength_snapshot', 'strength'), ('mi_pair_intel_snapshot', 'strength'), ('mi_relationship_snapshot', 'relationship')):
            sql = re.sub(r'\bFROM\s+' + table + r'\b',
                         f"FROM (SELECT * FROM {table} WHERE as_of IN (SELECT as_of FROM mi_analysis_provenance WHERE kind='{kind}' AND snapshot_id='{identifier}')) AS {table}", sql, flags=re.I)
    return conn.execute(sql, params)


def values(row):
    return tuple(row.values()) if isinstance(row, dict) else tuple(row)

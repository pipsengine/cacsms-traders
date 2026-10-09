import logging
import os
import re
import sqlite3
import threading
import time
import traceback
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Iterable

from .config import ROOT, app_env

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # pragma: no cover - optional dependency in dev/test env
    psycopg = None
    dict_row = None

log = logging.getLogger(__name__)

# Single-process SQLite: serialize writers (strength/scanner/API) to avoid "database is locked".
_SQLITE_MUTEX = threading.RLock()


def _sqlite_backend() -> bool:
    return app_env() != 'production' or not database_url()


def _safe_database_error(exc: Exception) -> str:
    message = str(exc)
    for name in ('DATABASE_URL', 'BOOTSTRAP_PASSWORD', 'SUPER_ADMIN_PASSWORD', 'CTRADER_CLIENT_SECRET', 'API_PROXY_SECRET',
                 'SMTP_PASSWORD', 'SMTP_ENCRYPTION_KEY', 'CRON_SECRET'):
        secret = os.getenv(name, '')
        if secret:
            message = message.replace(secret, '[REDACTED]')
    return message[:2000]


def database_url() -> str | None:
    value = os.getenv('DATABASE_URL', '').strip()
    return value or None


def db_path() -> Path:
    if app_env() == 'production':
        return Path('DATABASE_URL')
    raw = os.getenv('DATABASE_PATH', 'database/db_cacsms-traders.db')
    p = Path(raw)
    resolved = p if p.is_absolute() else (ROOT / p).resolve()
    return resolved


class DatabaseUnavailable(RuntimeError):
    pass


def _creation_allowed() -> bool:
    if app_env() != 'production':
        return True
    return os.getenv('DATABASE_ALLOW_CREATE', '0').strip().lower() in ('1', 'true', 'yes')


def _ensure_database_directory(path: Path) -> None:
    parent = path.parent
    if not parent.exists():
        if _creation_allowed():
            parent.mkdir(parents=True, exist_ok=True)
            return
        raise DatabaseUnavailable(
            f'Production database directory is missing: {parent}. Set DATABASE_PATH to a durable writable location.'
        )
    if not os.access(str(parent), os.W_OK):
        raise DatabaseUnavailable(
            f'Production database directory is not writable: {parent}. The Vercel filesystem is not a durable database volume.'
        )


def _sqlite_connect():
    path = db_path()
    if not path.exists():
        if not _creation_allowed():
            raise DatabaseUnavailable(
                f'Production database not found at {path}; set DATABASE_PATH to the durable database file (or DATABASE_ALLOW_CREATE=1 for first provisioning)'
            )
        _ensure_database_directory(path)
    else:
        _ensure_database_directory(path)

    log.info('Opening SQLite database at %s (env=%s)', path, app_env())
    try:
        conn = sqlite3.connect(path, timeout=60, check_same_thread=False)
    except sqlite3.Error as exc:
        log.exception('SQLite connect failed for %s', path)
        raise DatabaseUnavailable(f'Unable to open SQLite database at {path}: {exc}') from exc
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA synchronous=NORMAL')
    conn.execute('PRAGMA busy_timeout=60000')
    return conn


def _postgres_connect():
    url = database_url()
    if not url:
        raise DatabaseUnavailable('Production requires DATABASE_URL to connect to PostgreSQL/Neon.')
    if psycopg is None:
        raise DatabaseUnavailable('psycopg is required in production for PostgreSQL/Neon support.')
    log.info('Opening PostgreSQL database using DATABASE_URL (env=%s)', app_env())
    try:
        conn = psycopg.connect(url, autocommit=False, row_factory=dict_row)
    except Exception as exc:  # pragma: no cover - environment-specific failure path
        detail = _safe_database_error(exc)
        frames = ''.join(traceback.format_tb(exc.__traceback__))
        log.error('PostgreSQL connection failed; error_type=%s; detail=%s\n%s', type(exc).__name__, detail, frames)
        raise DatabaseUnavailable(f'Unable to connect to PostgreSQL: {detail}') from exc
    return conn


def _convert_question_marks(sql: str, params):
    if '?' not in sql:
        return sql, params
    if params in (None, (), []):
        return sql.replace('?', '%s'), params
    values = tuple(params)
    return sql.replace('?', '%s'), values


def _sql_conflict_columns(table_name: str) -> str | None:
    mapping = {
        'mi_scanner_snapshot': 'tenant_id, trading_account_id, symbol, as_of',
        'mi_range_structure_snapshot': 'tenant_id, trading_account_id, symbol, as_of',
        'mi_structure_overview_snapshot': 'tenant_id, trading_account_id, symbol, as_of',
        'mi_h8_bos_btl_snapshot': 'tenant_id, trading_account_id, symbol, as_of',
        'mi_trend_structure_snapshot': 'tenant_id, trading_account_id, symbol, as_of',
        'mi_pair_intel_snapshot': 'tenant_id, trading_account_id, pair, as_of',
        'ctrader_oauth_states': 'state_hash',
        'ctrader_connections': 'tenant_id, environment',
    }
    return mapping.get(table_name.lower())


def _rewrite_production_sql(sql: str, params):
    if app_env() != 'production' or not database_url():
        return sql, params

    normalized = sql.strip()
    if not normalized:
        return sql, params

    upper = normalized.upper()
    if 'INSERT OR IGNORE' in upper:
        match = re.match(r'\s*INSERT\s+OR\s+IGNORE\s+INTO\s+([A-Za-z0-9_\.]+)\s*\((.*?)\)\s*VALUES\s*\((.*?)\)\s*', normalized, re.I | re.S)
        if match:
            table = match.group(1)
            columns = match.group(2).strip()
            values = match.group(3).strip()
            rewritten = f'INSERT INTO {table}({columns}) VALUES({values}) ON CONFLICT DO NOTHING'
            return _convert_question_marks(rewritten, params)

    if 'INSERT OR REPLACE' in upper:
        match = re.match(r'\s*INSERT\s+OR\s+REPLACE\s+INTO\s+([A-Za-z0-9_\.]+)\s*\((.*?)\)\s*VALUES\s*\((.*?)\)\s*', normalized, re.I | re.S)
        if match:
            table = match.group(1)
            columns = match.group(2).strip()
            values = match.group(3).strip()
            conflict_target = _sql_conflict_columns(table)
            if conflict_target:
                cols = [c.strip() for c in columns.split(',') if c.strip()]
                updates = ', '.join(f'{col}=EXCLUDED.{col}' for col in cols if col not in [x.strip() for x in conflict_target.split(',')])
                rewritten = f'INSERT INTO {table}({columns}) VALUES({values}) ON CONFLICT ({conflict_target}) DO UPDATE SET {updates}'
            else:
                rewritten = f'INSERT INTO {table}({columns}) VALUES({values}) ON CONFLICT DO NOTHING'
            return _convert_question_marks(rewritten, params)

    return _convert_question_marks(normalized, params)


def split_sql_script(sql: str) -> list[str]:
    """Split on ';' outside $$-quoted bodies (PL/pgSQL functions contain semicolons)."""
    statements, buf, quoted = [], [], False
    for token in re.split(r'(\$\$|;)', sql):
        if token == '$$':
            quoted = not quoted
            buf.append(token)
        elif token == ';' and not quoted:
            stmt = ''.join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
        else:
            buf.append(token)
    tail = ''.join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


def _sqlite_execute(raw: sqlite3.Connection, sql: str, params=(), **kwargs):
    for attempt in range(12):
        try:
            return raw.execute(sql, params, **kwargs)
        except sqlite3.OperationalError as exc:
            msg = str(exc).lower()
            if ('locked' not in msg and 'busy' not in msg and 'timeout' not in msg) or attempt >= 11:
                raise
            time.sleep(0.05 * (attempt + 1))
    raise RuntimeError('database is locked or busy')


class _CompatConnection:
    def __init__(self, raw_conn, provider: str):
        self._raw = raw_conn
        self.provider = provider

    def execute(self, sql, params=(), **kwargs):
        if self.provider == 'sqlite':
            return _sqlite_execute(self._raw, sql, params, **kwargs)
        sql2, params2 = _rewrite_production_sql(sql, params)
        return self._raw.execute(sql2, params2, **kwargs)

    def executemany(self, sql, seq_of_params):
        if self.provider == 'sqlite':
            for params in seq_of_params:
                _sqlite_execute(self._raw, sql, params)
            return None
        converted = []
        for params in seq_of_params:
            sql2, params2 = _rewrite_production_sql(sql, params)
            converted.append((sql2, params2))
        for sql2, params2 in converted:
            self._raw.execute(sql2, params2)
        return None

    def executescript(self, sql):
        if self.provider == 'sqlite':
            return self._raw.executescript(sql)
        for part in split_sql_script(sql):
            self.execute(part)
        return None

    def __getattr__(self, name):
        return getattr(self._raw, name)

    def commit(self):
        return self._raw.commit()

    def rollback(self):
        return self._raw.rollback()

    def close(self):
        return self._raw.close()


def connect():
    if app_env() == 'production':
        if not database_url():
            raise DatabaseUnavailable('Production requires DATABASE_URL to connect to PostgreSQL/Neon.')
        raw = _postgres_connect()
        return _CompatConnection(raw, 'postgresql')
    raw = _sqlite_connect()
    return _CompatConnection(raw, 'sqlite')


def execute_retry(conn, sql: str, params=(), *, attempts: int = 8, sleep_seconds: float = 0.05):
    for attempt in range(attempts):
        try:
            return conn.execute(sql, params)
        except Exception as exc:
            msg = str(exc).lower()
            if ('locked' not in msg and 'timeout' not in msg and 'busy' not in msg) or attempt >= attempts - 1:
                raise
            time.sleep(sleep_seconds * (attempt + 1))
    raise RuntimeError('database is locked or busy')


_process_lock_handle = None


def hold_sqlite_process_lock() -> None:
    """Call once at API startup so a second local API process fails fast instead of locking SQLite."""
    global _process_lock_handle
    if os.getenv('PYTEST_CURRENT_TEST') or os.getenv('CACSMS_SKIP_SQLITE_PROCESS_LOCK', '').strip() in ('1', 'true', 'yes'):
        return
    if _process_lock_handle is not None or not _sqlite_backend():
        return
    path = db_path()
    lock_path = path.with_suffix(path.suffix + '.api.lock')
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, 'a+b')
    try:
        if os.name == 'nt':
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        handle.close()
        raise DatabaseUnavailable(
            f'Another API process is already using {path}. Stop duplicate servers (only one npm run dev / run_api.py).'
        ) from exc
    _process_lock_handle = handle


def release_sqlite_process_lock() -> None:
    global _process_lock_handle
    handle = _process_lock_handle
    if handle is None:
        return
    _process_lock_handle = None
    try:
        if os.name == 'nt':
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def execute_values(conn, head: str, rows, tail: str = '', *, key=None, chunk: int = 50) -> None:
    """Multi-row ``INSERT head VALUES (...),(...) tail``: one round trip per chunk instead of per row.

    ``key`` maps a row to its conflict target; Postgres rejects an upsert that touches one row twice,
    so duplicates are collapsed (last wins)."""
    rows = [tuple(r) for r in rows]
    if key is not None:
        rows = list({key(r): r for r in rows}.values())
    if not rows:
        return
    width = len(rows[0])
    for start in range(0, len(rows), chunk):
        batch = rows[start:start + chunk]
        placeholders = ','.join(['(' + ','.join(['?'] * width) + ')'] * len(batch))
        execute_retry(conn, f'{head} VALUES {placeholders} {tail}', tuple(v for row in batch for v in row))


@contextmanager
def db():
    guard = _SQLITE_MUTEX if _sqlite_backend() else nullcontext()
    with guard:
        conn = connect()
        try:
            yield conn
            for attempt in range(8):
                try:
                    conn.commit()
                    break
                except Exception as exc:
                    msg = str(exc).lower()
                    if ('locked' not in msg and 'timeout' not in msg and 'busy' not in msg) or attempt >= 7:
                        raise
                    time.sleep(0.05 * (attempt + 1))
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

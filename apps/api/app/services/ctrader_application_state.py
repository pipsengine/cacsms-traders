"""Provider observations. An unverified application is not treated as inactive.

``CTRADER_APPLICATION_OBSERVATION`` is ignored. Inactive is recorded only after
cTrader rejects application authentication, and that observation expires so a
later activation is not hidden.
"""
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone

KEY = 'ctrader.application_state'
APP_INACTIVE = 'CTRADER_APP_INACTIVE'
INACTIVE_FRESH_SECONDS = 60
UNVERIFIED_FRESH_SECONDS = 900
INACTIVE_MESSAGE = (
    'cTrader rejected application authentication. The Open API application is not active.'
)
UNVERIFIED_MESSAGE = (
    'cTrader credentials are configured. Application activation has not been confirmed by the provider.'
)
ACTIVE_OAUTH_MESSAGE = (
    'The cTrader application accepted authentication. Select Connect cTrader to authorize an account.'
)


def provider_error_code(code, description=''):
    text = f'{code} {description}'.lower()
    if 'oa client is not in active state' in text or str(code).upper() == APP_INACTIVE:
        return APP_INACTIVE
    return str(code or 'provider_unavailable')[:80]


def _client_key():
    return hashlib.sha256(os.getenv('CTRADER_CLIENT_ID', '').strip().encode()).hexdigest()


def _observation(conn):
    row = conn.execute('SELECT value_json FROM system_settings WHERE key=?', (KEY,)).fetchone()
    observation = json.loads(row['value_json']) if row else None
    if observation and observation.get('client_key') != _client_key():
        return None
    return observation


def _age_seconds(observation) -> float | None:
    raw = (observation or {}).get('observed_at')
    if not raw:
        return None
    try:
        observed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - observed).total_seconds()


def application_state(conn):
    observation = _observation(conn)
    if not observation:
        return 'UNKNOWN'
    state = observation.get('state') or 'UNKNOWN'
    if state == 'AUTHORIZING':
        try:
            expires = datetime.fromisoformat(observation['expires_at'])
        except (KeyError, ValueError):
            return 'UNKNOWN'
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires <= datetime.now(timezone.utc):
            return 'UNKNOWN'
        return 'AUTHORIZING'
    # A provider rejection is evidence only while it is fresh. An old inactive
    # flag must not keep hiding an application that cTrader has since activated.
    if state == 'APP_INACTIVE':
        age = _age_seconds(observation)
        if age is None or age > INACTIVE_FRESH_SECONDS:
            return 'UNKNOWN'
    return state


def needs_application_probe(conn) -> bool:
    """True when status should ask cTrader whether the application authenticates."""
    observation = _observation(conn)
    if not observation:
        return True
    state = observation.get('state') or 'UNKNOWN'
    if state == 'AUTHORIZING':
        return False
    if state == 'ACTIVE':
        return False
    age = _age_seconds(observation)
    limit = INACTIVE_FRESH_SECONDS if state == 'APP_INACTIVE' else UNVERIFIED_FRESH_SECONDS
    if state in ('APP_INACTIVE', 'UNVERIFIED') and age is not None and age <= limit:
        return False
    return True


def record_application_state(conn, state):
    now = datetime.now(timezone.utc)
    observation = {'state': state, 'client_key': _client_key(), 'observed_at': now.isoformat()}
    if state == 'AUTHORIZING':
        observation['expires_at'] = (now + timedelta(minutes=10)).isoformat()
    conn.execute(
        'INSERT INTO system_settings(key,value_json,updated_at) VALUES(?,?,?) '
        'ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at',
        (KEY, json.dumps(observation), now.isoformat()),
    )


def diagnostic_state(configured, app_state, row, connected=False):
    """Authoritative lifecycle. Connected is only returned after account authentication succeeded."""
    if not configured:
        return 'NOT_CONFIGURED'
    if connected:
        return 'CONNECTED'
    if row and row.get('connection_status') == 'DISCOVERING':
        return 'CONNECTING'
    if row and row.get('authorization_status') == 'AUTHORIZED':
        return 'DEGRADED'
    if row and row.get('authorization_status') in ('REAUTH_REQUIRED', 'NEEDS_REAUTH'):
        return 'ERROR'
    if app_state == 'APP_INACTIVE':
        return 'APP_INACTIVE'
    if app_state == 'AUTHORIZING':
        return 'AUTHORIZING'
    if app_state != 'ACTIVE':
        return 'APPLICATION_UNVERIFIED'
    return 'OAUTH_NOT_AUTHORIZED'


def status_message(provider_status: str) -> str:
    return {
        'APP_INACTIVE': INACTIVE_MESSAGE,
        'APPLICATION_UNVERIFIED': UNVERIFIED_MESSAGE,
        'OAUTH_NOT_AUTHORIZED': ACTIVE_OAUTH_MESSAGE,
        'AUTHORIZING': 'cTrader authorization is in progress. Finish the provider window, or start again if it expired.',
        'CONNECTING': 'Authorization was saved. cTrader account authentication is still in progress.',
        'CONNECTED': 'cTrader account authentication succeeded. Trading execution stays disabled.',
        'DEGRADED': 'cTrader authorization is saved, but the broker connection is not healthy.',
        'ERROR': 'cTrader authorization must be renewed before the connection can be used.',
        'NOT_CONFIGURED': 'cTrader server configuration is incomplete.',
    }.get(provider_status, 'cTrader connection has not been established.')

"""Safe approval observations; a successful manual OAuth/account flow clears a block."""
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone

KEY = 'ctrader.application_state'
APP_INACTIVE = 'CTRADER_APP_INACTIVE'
INACTIVE_MESSAGE = (
    'Cacsms Traders is registered with cTrader Open API, but the application '
    'is not yet active. OAuth authorization will become available after '
    'cTrader activates the application.'
)


def provider_error_code(code, description=''):
    text = f'{code} {description}'.lower()
    if 'oa client is not in active state' in text or str(code).upper() == APP_INACTIVE:
        return APP_INACTIVE
    return str(code or 'provider_unavailable')[:80]


def _client_key():
    return hashlib.sha256(os.getenv('CTRADER_CLIENT_ID', '').strip().encode()).hexdigest()


def application_state(conn):
    row = conn.execute('SELECT value_json FROM system_settings WHERE key=?', (KEY,)).fetchone()
    observation = json.loads(row['value_json']) if row else None
    if observation and observation.get('client_key') != _client_key():
        observation = None
    if observation:
        state = observation.get('state', 'UNKNOWN')
        if state == 'AUTHORIZING':
            expires = datetime.fromisoformat(observation['expires_at'])
            if expires <= datetime.now(timezone.utc):
                return 'AUTHORIZATION_REQUIRED'
        return state
    # A reported provider rejection can be provisioned once without credentials.
    # Persisted manual attempts supersede this observation; it is not an approval bypass.
    return 'APP_INACTIVE' if os.getenv('CTRADER_APPLICATION_OBSERVATION') == APP_INACTIVE else 'UNKNOWN'


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
    if not configured:
        return 'NOT_CONFIGURED'
    if app_state == 'APP_INACTIVE':
        return 'APP_INACTIVE'
    if app_state == 'AUTHORIZING':
        return 'AUTHORIZING'
    if connected:
        return 'CONNECTED'
    if not row:
        return 'AUTHORIZATION_REQUIRED'
    if row.get('authorization_status') == 'AUTHORIZED':
        return 'AUTHORIZED' if row.get('connection_status') == 'DISCOVERING' else 'DEGRADED'
    if row.get('connection_status') == 'DISCONNECTED':
        return 'DISCONNECTED'
    if row.get('authorization_status') in ('REAUTH_REQUIRED', 'NOT_AUTHORIZED', 'NEEDS_REAUTH', 'PENDING_PROVIDER_ACTIVATION'):
        return 'AUTHORIZATION_REQUIRED'
    return 'ERROR'

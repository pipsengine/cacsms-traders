"""Central, read-only market-data selection and safe connectivity diagnostics."""
import json
import os
from .constants import FX_PAIRS_28


def configuration(conn):
    row = conn.execute("SELECT value_json FROM system_settings WHERE key='market_data.provider'").fetchone()
    cfg = json.loads(row['value_json']) if row else {}
    if isinstance(cfg, str):
        cfg = {'provider': cfg}
    if not isinstance(cfg, dict):
        cfg = {}
    return {'provider': cfg.get('provider', os.getenv('MARKET_DATA_PROVIDER', 'ctrader' if os.getenv('APP_ENV') == 'production' else 'none')).lower(),
            'tenant_id': cfg.get('tenant_id', os.getenv('MARKET_DATA_TENANT_ID', '')),
            'account_id': str(cfg.get('account_id', os.getenv('MARKET_DATA_ACCOUNT_ID', '')))}


def market_context(conn):
    cfg = configuration(conn)
    provider = cfg['provider']
    out = dict(active_provider=provider, provider_status='NOT CONFIGURED', authorization_status='NOT_AUTHORIZED',
               account_status='NOT_SELECTED', symbols_resolved=0, required_symbols=28,
               missing_pairs=list(FX_PAIRS_28), failed_symbol_mappings=[], failed_candle_requests=[],
               closed_bar_status='NOT_STARTED', strength_engine_status='UNAVAILABLE',
               last_successful_sync=None, last_calculation=None, error_code=None,
               market_data_ready=False, analysis_only=True)
    if provider == 'mt5':
        from .mt5_platform_status import get_mt5_market_context
        legacy = get_mt5_market_context(conn)
        out.update(provider_status='CONNECTED' if legacy['market_data_ready'] and legacy['mt5_connected'] else 'DISCONNECTED',
                   authorization_status='AUTHORIZED', account_status='SELECTED', market_data_ready=bool(legacy['market_data_ready'] and legacy['mt5_connected']))
    elif provider == 'ctrader':
        from ..routers.ctrader import ctrader_config
        if ctrader_config() is None:
            out['error_code'] = 'ctrader_not_configured'
            return out
        out['provider_status'] = 'AUTHORIZATION REQUIRED'
        out['error_code'] = 'ctrader_authorization_required'
        if not cfg['tenant_id']:
            rows = conn.execute("SELECT authorization_status,connection_status FROM ctrader_connections WHERE environment='demo'").fetchall()
            authorized = [r for r in rows if r['authorization_status'] == 'AUTHORIZED']
            accounts = conn.execute("SELECT COUNT(*) AS account_count FROM ctrader_accounts WHERE environment='demo' AND authorization_status='AUTHORIZED'").fetchone()['account_count']
            out['accounts_discovered'] = accounts
            if authorized:
                out.update(authorization_status='AUTHORIZED', provider_status='DEGRADED', error_code='market_data_scope_selection_required', account_status='DISCOVERED' if accounts else 'NOT_DISCOVERED')
            return out
        row = conn.execute("SELECT authorization_status,connection_status,last_error_code FROM ctrader_connections WHERE tenant_id=? AND environment='demo'", (cfg['tenant_id'],)).fetchone()
        if not row:
            return out
        out['authorization_status'] = row['authorization_status']
        if row['authorization_status'] != 'AUTHORIZED':
            return out
        account = conn.execute("SELECT authorization_status FROM ctrader_accounts WHERE tenant_id=? AND ctid_trader_account_id=? AND environment='demo'", (cfg['tenant_id'], cfg['account_id'])).fetchone()
        out['account_status'] = 'SELECTED' if account and account['authorization_status'] == 'AUTHORIZED' else 'NOT_SELECTED'
        out['provider_status'] = 'DEGRADED'
        out['error_code'] = row['last_error_code'] or 'ctrader_account_selection_required'
        if out['account_status'] == 'SELECTED' and row['connection_status'] == 'CONNECTED':
            out.update(provider_status='CONNECTING', market_data_ready=True, error_code=None)
    return out


def create_market_data_gateway(conn=None):
    from ..core.database import db
    if conn is None:
        with db() as connection:
            return create_market_data_gateway(connection)
    cfg = configuration(conn)
    if cfg['provider'] == 'mt5':
        from .mt5_gateway import create_market_data_gateway as mt5_adapter
        return mt5_adapter()
    if cfg['provider'] == 'ctrader' and market_context(conn)['market_data_ready']:
        from .ctrader_gateway import CTraderGateway
        return CTraderGateway(conn, cfg)
    from .provider_contract import MarketDataUnavailable
    raise MarketDataUnavailable('market_data_unavailable')

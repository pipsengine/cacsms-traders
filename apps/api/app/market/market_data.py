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
    return {'selection_mode': cfg.get('selection_mode', os.getenv('MARKET_DATA_SELECTION_MODE', 'AUTO')).upper(),
            'mt5_tenant_id': cfg.get('mt5_tenant_id', ''),
            'provider': cfg.get('provider', os.getenv('MARKET_DATA_PROVIDER', 'auto')).lower(),
            'tenant_id': cfg.get('tenant_id', os.getenv('MARKET_DATA_TENANT_ID', '')),
            'account_id': str(cfg.get('account_id', os.getenv('MARKET_DATA_ACCOUNT_ID', '')))}


def provider_context(conn, cfg):
    provider = cfg['provider']
    out = dict(active_provider=provider, provider_status='NOT CONFIGURED', authorization_status='NOT_AUTHORIZED',
               account_status='NOT_SELECTED', symbols_resolved=0, required_symbols=28,
               missing_pairs=list(FX_PAIRS_28), failed_symbol_mappings=[], failed_candle_requests=[],
               closed_bar_status='NOT_STARTED', strength_engine_status='UNAVAILABLE',
               last_successful_sync=None, last_calculation=None, error_code=None,
               market_data_ready=False, analysis_only=True)
    if provider == 'mt5':
        from ..domain.mt5_bridge import status
        bridge = status(conn,cfg.get('mt5_tenant_id','')) if cfg.get('mt5_tenant_id') else None
        if bridge:
            from datetime import datetime, timezone
            fresh_quotes = any(0 <= datetime.now(timezone.utc).timestamp()-q['time'] <= 120 for q in bridge['quotes'])
            ready = bridge['connected'] and fresh_quotes
            out.update(provider_status='CONNECTED' if bridge['connected'] else 'DISCONNECTED',authorization_status='AUTHORIZED',account_status='SELECTED',configured=True,connected=bridge['connected'],account_id=bridge['account_id'],environment=bridge['account']['trade_mode'].lower(),market_data_ready=ready,last_heartbeat=bridge['received_at'],error_code=None if ready else 'mt5_bridge_stale',bridge_tenant_id=cfg['mt5_tenant_id'])
            return out
        from .mt5_platform_status import get_mt5_market_context
        legacy = get_mt5_market_context(conn)
        out.update(provider_status='CONNECTED' if legacy['market_data_ready'] and legacy['mt5_connected'] else 'DISCONNECTED',
                   authorization_status='AUTHORIZED' if legacy.get('authorized', legacy['market_data_ready']) else 'NOT_AUTHORIZED', account_status='SELECTED' if legacy.get('account_id') else 'NOT_SELECTED', configured=legacy.get('configured', True), connected=legacy.get('mt5_connected', False), account_id=legacy.get('account_id'), environment=legacy.get('environment', 'UNKNOWN'), error_code=None if legacy['market_data_ready'] else 'MT5_CONNECTION_FAILED', market_data_ready=bool(legacy['market_data_ready'] and legacy['mt5_connected']))
    elif provider == 'ctrader':
        from ..routers.ctrader import ctrader_config
        if ctrader_config() is None:
            out['error_code'] = 'ctrader_not_configured'
            return out
        from ..services.ctrader_application_state import APP_INACTIVE, application_state
        app_state = application_state(conn)
        out['application_status'] = app_state
        if app_state == 'APP_INACTIVE':
            out.update(provider_status='APP_INACTIVE', authorization_status='PENDING_PROVIDER_ACTIVATION',
                       error_code=APP_INACTIVE, reason='cTrader provider authorization unavailable')
            return out
        if app_state == 'AUTHORIZING':
            out.update(provider_status='AUTHORIZING', authorization_status='AUTHORIZING')
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
        out['connected'] = row['connection_status'] == 'CONNECTED'
        if out['account_status'] == 'SELECTED' and row['connection_status'] == 'CONNECTED':
            out.update(provider_status='CONNECTING', market_data_ready=True, error_code=None)
    return out


def create_market_data_gateway(conn=None, context=None):
    from ..core.database import db
    if conn is None:
        with db() as connection:
            gateway = create_market_data_gateway(connection)
            gateway.observer = None
            return gateway
    context = context or market_context(conn)
    cfg = {**configuration(conn), **context.get('market_data_scope', {}), 'provider': context['active_provider']}
    from .provider_contract import MarketDataUnavailable
    if context.get('selection_mode'):
        current = market_context(conn)
        if current.get('active_provider') != context.get('active_provider') or current.get('market_data_scope') != context.get('market_data_scope'):
            raise MarketDataUnavailable('analytical_scope_changed')
    if not context['market_data_ready']:
        from .provider_contract import MarketDataUnavailable
        raise MarketDataUnavailable('market_data_unavailable')
    from .normalized_provider import NormalizedProvider
    from .provider_manager import ProviderManager
    manager = ProviderManager(conn)
    try:
        if cfg['provider'] == 'mt5':
            if context.get('bridge_tenant_id'):
                from .mt5_bridge_gateway import MT5BridgeGateway
                adapter = MT5BridgeGateway(conn,context['bridge_tenant_id'])
            else:
                from .mt5_gateway import create_market_data_gateway as mt5_adapter
                adapter = mt5_adapter()
            if not hasattr(adapter, 'get_account_context'):
                raise MarketDataUnavailable('MT5_CONNECTION_FAILED')
        elif cfg['provider'] == 'ctrader':
            from .ctrader_gateway import CTraderGateway
            adapter = CTraderGateway(conn, cfg)
        else:
            raise MarketDataUnavailable('market_data_unavailable')
    except (RuntimeError, OSError, ValueError):
        manager.observe(cfg['provider'],success=False,error='MT5_CONNECTION_FAILED' if cfg['provider']=='mt5' else 'provider_connection_failed')
        conn.commit()
        raise MarketDataUnavailable('provider_connection_failed') from None
    gateway = NormalizedProvider(adapter, cfg['provider'], adapter.get_account_context(), observer=lambda **status: _observe_request(manager, cfg['provider'], status))
    gateway.snapshot_id = manager.bind_snapshot(cfg['provider'], (gateway.get_account_context() or {}).get('account_id', ''))
    return gateway


def market_context(conn):
    from .provider_manager import ProviderManager
    return ProviderManager(conn).context()


def _observe_request(manager, provider, status):
    manager.observe(provider, **status)
    if not status.get('success', True):
        # Keep failure telemetry even when the caller rolls back a failed analytical cycle.
        manager.conn.commit()

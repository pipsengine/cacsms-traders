"""Platform-wide provider policy; trading authorization remains a separate boundary."""
import json
from datetime import datetime
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from ..deps import current_user
from ..core.database import db
from ..core.audit import write_audit
from ..core.security import iso
from ..market.market_data import configuration, market_context

router = APIRouter(prefix='/api/providers', tags=['Providers'])


def admin(user=Depends(current_user)):
    if not user.get('is_platform_admin'):
        raise HTTPException(403, 'Platform administrator access required for global provider policy')
    return user


class Selection(BaseModel):
    selection_mode: Literal['AUTO', 'MT5_PREFERRED', 'CTRADER_PREFERRED']
    tenant_id: str | None = None
    account_id: str | None = None


class Backfill(BaseModel):
    symbol: str
    timeframe: Literal['M1','M5','M15','M30','H1','H4','H8','D1','W1','MN']
    start: datetime
    end: datetime
    count: int = 2000


@router.get('')
def overview(user=Depends(admin)):
    with db() as conn:
        return market_context(conn)


@router.get('/accounts')
def market_accounts(tenant_id: str, user=Depends(admin)):
    with db() as conn:
        rows = conn.execute("SELECT ctid_trader_account_id AS account_id,broker_name AS broker,environment FROM ctrader_accounts WHERE tenant_id=? AND environment='demo' AND authorization_status='AUTHORIZED' ORDER BY ctid_trader_account_id", (tenant_id,)).fetchall()
        return [dict(row) for row in rows]


@router.post('/backfill')
def backfill(body: Backfill, user=Depends(admin)):
    from ..market.constants import FX_PAIRS_28
    from ..market.market_data import create_market_data_gateway
    from ..market.repository import MarketRepository
    from ..market.ingestion import CandleIngestionService
    from ..market.provider_contract import MarketDataUnavailable
    symbol = body.symbol.upper().replace('/', '')
    if symbol not in (*FX_PAIRS_28, 'XAUUSD') or not 1 <= body.count <= 2000:
        raise HTTPException(400, 'Select a supported symbol and a count between 1 and 2000')
    if body.start.tzinfo is None or body.end.tzinfo is None or body.start >= body.end:
        raise HTTPException(400, 'Provide an increasing date range with explicit timezones')
    with db() as conn:
        try:
            from ..market.provider_manager import ProviderManager
            ProviderManager(conn).refresh_health()
            gateway = create_market_data_gateway(conn)
            repo = MarketRepository(conn, provider=gateway.provider_id, snapshot_id=gateway.snapshot_id)
            result = CandleIngestionService(gateway, repo).sync(symbol,body.timeframe,body.count,start=body.start,end=body.end)
        except MarketDataUnavailable:
            raise HTTPException(503, 'Market data unavailable for the selected provider') from None
        return {**result, 'source_provider': gateway.provider_id, 'snapshot_id': gateway.snapshot_id, 'analysis_only': True}


@router.put('/selection')
def selection(body: Selection, user=Depends(admin)):
    with db() as conn:
        previous = configuration(conn)
        cfg = {**previous, 'provider': 'auto', 'selection_mode': body.selection_mode}
        if body.tenant_id is not None:
            cfg['tenant_id'] = body.tenant_id
        if body.account_id is not None:
            cfg['account_id'] = body.account_id
        if cfg['account_id'] and (body.tenant_id is not None or body.account_id is not None):
            account = conn.execute("SELECT 1 FROM ctrader_accounts WHERE tenant_id=? AND ctid_trader_account_id=? AND environment='demo' AND authorization_status='AUTHORIZED'", (cfg['tenant_id'], cfg['account_id'])).fetchone()
            if not account:
                raise HTTPException(400, 'Select an OAuth-authorized cTrader demo account within the selected tenant')
        conn.execute('INSERT INTO system_settings(key,value_json,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at', ('market_data.provider', json.dumps(cfg), iso()))
        write_audit(conn, None, user['id'], 'PROVIDER_SELECTED', 'market_data_policy', before=previous, after=cfg)
        context = market_context(conn)
        scope = conn.execute('SELECT provider,account_id FROM mi_provider_snapshot WHERE finalized_at IS NULL LIMIT 1').fetchone()
        selected_account = context.get('providers', {}).get(context.get('active_provider'), {}).get('account_id') or ''
        if scope and (scope['provider'] != context.get('active_provider') or scope['account_id'] != selected_account):
            from ..market.provider_manager import ProviderManager
            ProviderManager(conn).finalize_snapshot()
        return context

"""Read-only bridge credentials and bounded authenticated ingestion."""
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from ..core.database import db
from ..core.security import iso, new_token, token_hash
from ..core.audit import write_audit
from ..deps import current_user
from ..services.access import require_permission
from ..domain import mt5_bridge as bridge
from ..market.constants import FX_PAIRS_28
from ..market.h8_aggregate import aggregate_h8_from_h1
from ..market.models import Candle
from ..market.normalized_provider import candle_close

router = APIRouter(prefix='/api/tenants/{tenant_id}/mt5-bridge', tags=['MT5 Windows Bridge'])


class Account(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    login: str = Field(min_length=1,max_length=32,pattern=r'^\d+$')
    server: str = Field(min_length=1,max_length=128)
    company: str = Field(default='MT5',max_length=128)
    currency: str = Field(min_length=3,max_length=8)
    trade_mode: Literal['DEMO','LIVE','PROP_FIRM']
    balance: float
    equity: float
    margin: float
    free_margin: float
    leverage: int = Field(ge=0,le=100000)


class Quote(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    symbol: str
    provider_symbol: str = Field(max_length=64)
    bid: float = Field(gt=0)
    ask: float = Field(gt=0)
    time: int = Field(gt=0)
    broker_time: int | None = Field(default=None,gt=0)
    digits: int = Field(ge=0,le=12)
    tick_size: float = Field(gt=0)
    pip_size: float = Field(gt=0)
    @model_validator(mode='after')
    def valid(self):
        if self.symbol not in (*FX_PAIRS_28, 'XAUUSD') or self.ask < self.bid or self.time > datetime.now(timezone.utc).timestamp()+5:
            raise ValueError('Invalid bridge quote')
        return self


class Bar(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    symbol: str
    timeframe: Literal['M1','M5','M15','M30','H1','H4','D1','W1','MN']
    time: int = Field(gt=0)
    broker_time: int | None = Field(default=None,gt=0)
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    tick_volume: int = Field(ge=0)
    spread: float = Field(ge=0)
    @model_validator(mode='after')
    def valid(self):
        opened = datetime.fromtimestamp(self.time,timezone.utc)
        if self.symbol not in (*FX_PAIRS_28,'XAUUSD') or self.high < max(self.open,self.close,self.low) or self.low > min(self.open,self.close,self.high):
            raise ValueError('Only valid closed candles are accepted')
        return self


class Heartbeat(BaseModel):
    model_config = ConfigDict(extra='forbid')
    account: Account
    terminal_path: str = Field(min_length=1,max_length=512)
    quotes: list[Quote] = Field(max_length=29)
    candles: list[Bar] = Field(default_factory=list,max_length=12000)
    broker_utc_offset_seconds: int = Field(default=0,ge=-50400,le=50400)
    @model_validator(mode='after')
    def valid_times(self):
        offset = self.broker_utc_offset_seconds
        if offset % 900:
            raise ValueError('Broker clock offset must use quarter-hour increments')
        for item in [*self.quotes,*self.candles]:
            if (offset and item.broker_time is None) or (item.broker_time is not None and item.broker_time-item.time != offset):
                raise ValueError('Broker timestamp does not match its UTC offset')
        now = datetime.now(timezone.utc)
        for bar in self.candles:
            if candle_close(datetime.fromtimestamp(bar.time,timezone.utc),bar.timeframe,offset)>now:
                raise ValueError('Only closed candles are accepted')
        return self


@router.post('/credential')
def credential(tenant_id: str, user=Depends(current_user)):
    with db() as conn:
        require_permission(conn,user,tenant_id,'connections.manage')
        token = new_token()
        expiry = iso(datetime.now(timezone.utc)+timedelta(hours=8))
        bridge.save(conn,tenant_id,'credential',dict(hash=token_hash(token),generation=secrets.token_hex(16),expires_at=expiry,user_id=user['id']))
        if user.get('is_platform_admin'):
            from ..market.market_data import configuration
            import json
            cfg = {**configuration(conn),'mt5_tenant_id':tenant_id}
            conn.execute('INSERT INTO system_settings(key,value_json,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at', ('market_data.provider',json.dumps(cfg),iso()))
        write_audit(conn,tenant_id,user['id'],'MT5_BRIDGE_PAIRED','WindowsGateway',tenant_id)
        return dict(token=token,expires_at=expiry)


@router.post('/heartbeat')
def heartbeat(tenant_id: str, body: Heartbeat, x_mt5_bridge_token: str = Header(default='')):
    with db() as conn:
        # Serialize rotation/revocation and uploads for this tenant.
        conn.execute('UPDATE system_settings SET value_json=value_json WHERE key=?', (bridge.key(tenant_id,'credential'),))
        cred = bridge.read(conn,tenant_id,'credential')
        if not cred.get('hash') or not secrets.compare_digest(cred['hash'],token_hash(x_mt5_bridge_token)) or datetime.fromisoformat(cred['expires_at']) <= datetime.now(timezone.utc):
            raise HTTPException(401,'MT5 bridge credential expired or revoked; reconnect from the platform.')
        owner = conn.execute('SELECT * FROM users WHERE id=?', (cred['user_id'],)).fetchone()
        if not owner or owner['status'] != 'ACTIVE':
            raise HTTPException(403,'MT5 bridge owner is inactive.')
        require_permission(conn,dict(owner),tenant_id,'connections.manage')
        account_id = f'{tenant_id}/{body.account.server}/{body.account.login}'
        if cred.get('account_id') and (cred['account_id'] != account_id or cred.get('environment') != body.account.trade_mode):
            raise HTTPException(409,'MT5 account changed; reconnect to authorize the new account.')
        cred['account_id'] = account_id
        cred['environment'] = body.account.trade_mode
        bridge.save(conn,tenant_id,'credential',cred)
        stamp = iso()
        old = bridge.read(conn,tenant_id,'state')
        state = dict(account=body.account.model_dump(),account_id=account_id,terminal_path=body.terminal_path,
                     received_at=stamp,connected=True,generation=cred['generation'],quotes=[q.model_dump() for q in body.quotes],broker_utc_offset_seconds=body.broker_utc_offset_seconds)
        bridge.save(conn,tenant_id,'state',state)
        bridge.sync_registry(conn,tenant_id,state)
        # Bounded batches avoid one Neon round-trip per bar.
        bars = {}
        h1 = {}
        for bar in body.candles:
            opened = datetime.fromtimestamp(bar.time,timezone.utc)
            closed = candle_close(opened,bar.timeframe,body.broker_utc_offset_seconds)
            bars[(bar.symbol,bar.timeframe,bar.time)] = (bar.symbol,bar.timeframe,opened.isoformat(),closed.isoformat(),bar.open,bar.high,bar.low,bar.close,bar.tick_volume,bar.spread,'mt5',account_id,1)
            if bar.timeframe == 'H1':
                h1.setdefault(bar.symbol,[]).append(Candle(bar.symbol,'H1',opened,closed,bar.open,bar.high,bar.low,bar.close,bar.tick_volume,bar.spread,'mt5',True,account_id))
        # MT5 has no native H8; derive it here so analytical readers never have to write candles.
        for symbol,rows in h1.items():
            for c in aggregate_h8_from_h1(rows):
                bars[(symbol,'H8',int(c.open_time.timestamp()))] = (symbol,'H8',c.open_time.isoformat(),c.close_time.isoformat(),c.open,c.high,c.low,c.close,c.tick_volume,c.spread,'mt5',account_id,1)
        values = list(bars.values())
        # Each uploaded series is a contiguous broker window: drop stored rows inside it that the broker no longer has
        # (e.g. bars recorded on broker time before UTC normalization) so gaps and duplicates cannot persist.
        windows = {}
        for symbol,timeframe,opened,*_ in values:
            low,high = windows.get((symbol,timeframe),(opened,opened))
            windows[(symbol,timeframe)] = (min(low,opened),max(high,opened))
        for (symbol,timeframe),(low,high) in windows.items():
            conn.execute("DELETE FROM mi_provider_candle WHERE source='mt5' AND account_id=? AND symbol=? AND timeframe=? AND open_time>=? AND open_time<=?", (account_id,symbol,timeframe,low,high))
        for offset in range(0,len(values),200):
            batch = values[offset:offset+200]
            placeholders = ','.join(['('+','.join(['?']*13)+')']*len(batch))
            conn.execute('INSERT INTO mi_provider_candle(symbol,timeframe,open_time,close_time,open,high,low,close,tick_volume,spread,source,account_id,is_closed) VALUES '+placeholders+' ON CONFLICT(source,account_id,symbol,timeframe,open_time) DO UPDATE SET close_time=excluded.close_time,open=excluded.open,high=excluded.high,low=excluded.low,close=excluded.close,tick_volume=excluded.tick_volume,spread=excluded.spread', tuple(v for row in batch for v in row))
        if old.get('generation') != state['generation'] or not old.get('connected'):
            write_audit(conn,tenant_id,None,'MT5_BRIDGE_CONNECTED','WindowsGateway',tenant_id,after={'account_id':account_id,'execution_available':False})
        return dict(ok=True,received_at=stamp,account_id=account_id,execution_available=False)


@router.post('/disconnect')
def disconnect(tenant_id: str, user=Depends(current_user)):
    with db() as conn:
        require_permission(conn,user,tenant_id,'connections.manage')
        bridge.save(conn,tenant_id,'credential',{})
        conn.execute("UPDATE trading_connections SET status='DISCONNECTED',updated_at=? WHERE tenant_id=? AND adapter_type='LOCAL_MT5'", (iso(),tenant_id))
        conn.execute("UPDATE trading_accounts SET connection_status='DISCONNECTED',updated_at=? WHERE tenant_id=? AND connection_type='LOCAL_MT5'", (iso(),tenant_id))
        write_audit(conn,tenant_id,user['id'],'MT5_BRIDGE_DISCONNECTED','WindowsGateway',tenant_id)
    return {'ok':True}

"""Deterministic market-data policy. Execution is never selected by this policy."""
from datetime import datetime, timezone
import json

from .market_data import configuration, provider_context

MODES = ('AUTO', 'MT5_PREFERRED', 'CTRADER_PREFERRED')


def select_provider(states, mode='AUTO'):
    if mode not in MODES:
        raise ValueError('Unknown provider selection mode')
    priority = ('ctrader', 'mt5') if mode == 'CTRADER_PREFERRED' else ('mt5', 'ctrader')
    return next((p for p in priority if states[p]['healthy'] and states[p]['market_data_available']), None)


class ProviderManager:
    def __init__(self, conn):
        self.conn = conn
        self.cfg = configuration(conn)

    def states(self):
        states = {}
        storage = getattr(self.conn, 'provider', None) == 'postgresql' or bool(self.conn.execute("SELECT 1 FROM sqlite_master WHERE name='mi_provider_health'").fetchone())
        for provider in ('mt5', 'ctrader'):
            ctx = provider_context(self.conn, {**self.cfg, 'provider': provider})
            ready = bool(ctx['market_data_ready'])
            states[provider] = dict(
                provider=provider, configured=ctx.get('configured', ctx['provider_status'] != 'NOT CONFIGURED' and ctx.get('error_code') != 'ctrader_not_configured'),
                authorized=ctx['authorization_status'] == 'AUTHORIZED', connected=ctx.get('connected', ready),
                healthy=ready, market_data_available=ready, execution_available=False,
                last_heartbeat=ctx.get('last_heartbeat'), last_market_data=None, last_error=ctx.get('error_code'),
                environment='demo' if provider == 'ctrader' else 'terminal',
                account_id=self.cfg['account_id'] if provider == 'ctrader' else ctx.get('account_id'),
                context=ctx,
            )
            state = states[provider]
            state['environment'] = ctx.get('environment', state['environment'])
            if storage:
                row = self.conn.execute('SELECT state_json FROM mi_provider_health WHERE provider=?', (provider,)).fetchone()
                observed = json.loads(row['state_json']) if row else {}
                if observed.get('account_id') != state.get('account_id'):
                    observed = {}
                state.update(last_heartbeat=ctx.get('last_heartbeat') or observed.get('last_heartbeat'), last_market_data=observed.get('last_market_data'))
                if provider == 'ctrader':
                    heartbeat = observed.get('last_heartbeat')
                    fresh_heartbeat = heartbeat and (datetime.now(timezone.utc)-datetime.fromisoformat(heartbeat)).total_seconds() <= 120
                    state.update(healthy=bool(ready and observed.get('healthy') and fresh_heartbeat), market_data_available=bool(ready and observed.get('market_data_available') and fresh_heartbeat))
                last = observed.get('observed_at')
                recent_failure = last and (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds() < 60 and not observed.get('healthy', True)
                if recent_failure:
                    state.update(healthy=False, market_data_available=False, last_error=observed.get('last_error'))
                    ctx.update(market_data_ready=False, provider_status='DEGRADED', error_code=state['last_error'])
                if ctx['provider_status'] == 'APP_INACTIVE':
                    state.update(healthy=False, connected=False, market_data_available=False, last_error='CTRADER_APP_INACTIVE')
        return states

    def refresh_health(self):
        """Bounded read-only cTrader probe in workers, never in status requests or inactive apps."""
        ctx = provider_context(self.conn, {**self.cfg, 'provider': 'ctrader'})
        if not ctx.get('market_data_ready') or ctx.get('provider_status') == 'APP_INACTIVE':
            return
        old = self.conn.execute("SELECT state_json FROM mi_provider_health WHERE provider='ctrader'").fetchone()
        observed = json.loads(old['state_json']) if old else {}
        last = observed.get('observed_at') if observed.get('account_id') == self.cfg['account_id'] else None
        if last and (datetime.now(timezone.utc)-datetime.fromisoformat(last)).total_seconds() < 60:
            return
        try:
            from .ctrader_gateway import CTraderGateway
            from .quality import assess
            adapter = CTraderGateway(self.conn, self.cfg)
            bars = sorted(adapter.get_closed_candles('EURUSD', 'H1', count=2), key=lambda c:c.open_time)
            available = bool(bars and assess('EURUSD', 'H1', bars[-1].close_time).state != 'STALE')
            self.observe('ctrader', success=True, data_available=available, error=None if available else 'stale_or_missing_candles')
        except Exception:
            self.observe('ctrader', success=False, error='provider_probe_failed')

    def observe(self, provider, *, success, data_available=None, error=None):
        now = datetime.now(timezone.utc).isoformat()
        old = self.conn.execute('SELECT state_json FROM mi_provider_health WHERE provider=?', (provider,)).fetchone()
        state = json.loads(old['state_json']) if old else {k: v for k, v in self.states()[provider].items() if k != 'context'}
        state.update(observed_at=now, connected=success)
        state['account_id'] = self.cfg['account_id'] if provider == 'ctrader' else provider_context(self.conn, {**self.cfg, 'provider': 'mt5'}).get('account_id')
        if success:
            state['last_heartbeat'] = now
        if data_available is not None:
            state['market_data_available'] = data_available
            if data_available:
                state['last_market_data'] = now
        if not success:
            state['market_data_available'] = False
        state['healthy'] = success and state.get('market_data_available', False)
        state['last_error'] = error
        self.record_health(provider, state)

    def context(self):
        # Legacy explicit 'none' remains a deliberate disable switch.
        if self.cfg['provider'] == 'none':
            return provider_context(self.conn, self.cfg)
        states = self.states()
        mode = self.cfg['selection_mode']
        if self.cfg['provider'] in ('mt5', 'ctrader') and mode == 'AUTO':
            mode = 'MT5_PREFERRED' if self.cfg['provider'] == 'mt5' else 'CTRADER_PREFERRED'
        selected = select_provider(states, mode)
        diagnostic = selected or ('ctrader' if mode == 'CTRADER_PREFERRED' else 'mt5')
        ctx = dict(states[diagnostic]['context'])
        if selected is None and self.cfg['provider'] == 'auto':
            ctx.update(provider_status='MARKET DATA UNAVAILABLE', market_data_ready=False)
        binding = self.conn.execute("SELECT value_json FROM system_settings WHERE key='execution.provider'").fetchone()
        execution = json.loads(binding['value_json']) if binding else {}
        ctx.update(active_provider=selected, market_data_ready=bool(selected), selection_mode=mode, market_data_scope={'tenant_id': self.cfg['tenant_id'], 'account_id': states[selected]['account_id'] if selected else ''}, providers={p: {k: v for k, v in s.items() if k != 'context'} for p, s in states.items()},
                   execution_provider=execution.get('provider'), execution_account=execution.get('account_id'), execution_available=False, operating_mode='ANALYSIS_ONLY')
        return ctx

    def bind_snapshot(self, provider, account_id=''):
        """Persist a new immutable scope; finalize old scope before a provider/account change."""
        import uuid
        now = datetime.now(timezone.utc).isoformat()
        # Lock the policy row on PostgreSQL; SQLite serializes writes.
        self.conn.execute("INSERT INTO system_settings(key,value_json,updated_at) VALUES('market_data.provider',?,?) ON CONFLICT DO NOTHING", (json.dumps(self.cfg),now))
        self.conn.execute("UPDATE system_settings SET value_json=value_json WHERE key='market_data.provider'")
        row = self.conn.execute("SELECT * FROM mi_provider_snapshot WHERE finalized_at IS NULL ORDER BY started_at DESC LIMIT 1").fetchone()
        if row and row['provider'] == provider and row['account_id'] == account_id:
            return row['id']
        self.conn.execute('UPDATE mi_provider_snapshot SET finalized_at=? WHERE finalized_at IS NULL', (now,))
        snapshot_id = str(uuid.uuid4())
        self.conn.execute('INSERT INTO mi_provider_snapshot(id,provider,account_id,started_at) VALUES(?,?,?,?)', (snapshot_id, provider, account_id, now))
        from ..core.audit import write_audit
        write_audit(self.conn, None, None, 'MARKET_DATA_PROVIDER_CHANGED', 'market_data', snapshot_id,
                    before=dict(row) if row else None, after=dict(provider=provider, account_id=account_id))
        write_audit(self.conn, None, None, 'PROVIDER_SELECTED', 'market_data', provider)
        return snapshot_id

    def finalize_snapshot(self):
        row = self.conn.execute('SELECT * FROM mi_provider_snapshot WHERE finalized_at IS NULL LIMIT 1').fetchone()
        if row:
            self.conn.execute('UPDATE mi_provider_snapshot SET finalized_at=? WHERE finalized_at IS NULL', (datetime.now(timezone.utc).isoformat(),))
            from ..core.audit import write_audit
            write_audit(self.conn, None, None, 'MARKET_DATA_PROVIDER_CHANGED', 'market_data', row['id'], before=dict(row), after={'provider':None})

    def record_health(self, provider, state):
        """Audit transitions once, without connecting or retrying inactive OAuth apps."""
        from ..core.audit import write_audit
        old = self.conn.execute('SELECT state_json FROM mi_provider_health WHERE provider=?', (provider,)).fetchone()
        previous = json.loads(old['state_json']) if old else {}
        events = []
        for field, on, off in (('connected', 'PROVIDER_CONNECTED', 'PROVIDER_DISCONNECTED'), ('healthy', 'PROVIDER_RECOVERED', 'PROVIDER_DEGRADED')):
            if previous.get(field) != state.get(field):
                events.append(on if state.get(field) else off)
        if state.get('last_error') != previous.get('last_error'):
            if state.get('last_error') == 'CTRADER_APP_INACTIVE':
                events.append('CTRADER_APP_INACTIVE')
            elif provider == 'mt5' and state.get('last_error'):
                events.append('MT5_CONNECTION_FAILED')
        state = {**previous, **state}
        for event in events:
            write_audit(self.conn, None, None, event, 'provider', provider, before=previous, after=state)
        self.conn.execute('INSERT INTO mi_provider_health(provider,state_json) VALUES(?,?) ON CONFLICT(provider) DO UPDATE SET state_json=excluded.state_json', (provider, json.dumps(state)))

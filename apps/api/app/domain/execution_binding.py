"""Immutable campaign ownership. Market-data policy cannot change this binding."""
from datetime import datetime, timezone


def bind_campaign(conn, campaign_id, provider, account_id):
    if provider not in ('mt5', 'ctrader') or not account_id:
        raise ValueError('An explicit execution provider and account are required')
    conn.execute('INSERT INTO execution_provider_binding(campaign_id,provider,account_id,created_at) VALUES(?,?,?,?) ON CONFLICT DO NOTHING',
                 (campaign_id, provider, account_id, datetime.now(timezone.utc).isoformat()))
    row = conn.execute('SELECT provider,account_id FROM execution_provider_binding WHERE campaign_id=?', (campaign_id,)).fetchone()
    if row['provider'] != provider or row['account_id'] != account_id:
        raise ValueError('Execution ownership is immutable; provider/account failover refused')
    return dict(row)

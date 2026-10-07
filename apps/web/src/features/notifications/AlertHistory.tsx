import React from 'react';
import { RefreshCcw } from 'lucide-react';
import { Card, Empty, Notice } from '../../components/Ui';
import { get } from '../../lib/api';
import { fmtPrice, fmtTime, providerLabel, statusTone } from './format';
import type { AlertEvent, AlertType } from './types';

export function AlertHistory({ tenantId, types, statuses }: {
  tenantId: string;
  types: { key: AlertType; label: string }[];
  statuses: string[];
}) {
  const [rows, setRows] = React.useState<AlertEvent[]>([]);
  const [status, setStatus] = React.useState('');
  const [type, setType] = React.useState('');
  const [open, setOpen] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState('');

  const load = React.useCallback(async () => {
    if (!tenantId) return;
    setLoading(true);
    try {
      const q = new URLSearchParams({ tenant_id: tenantId, limit: '200' });
      if (status) q.set('status', status);
      if (type) q.set('event_type', type);
      setRows((await get<{ events: AlertEvent[] }>(`/notifications/email/events?${q}`)).events);
      setError('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load alert history.');
    } finally {
      setLoading(false);
    }
  }, [tenantId, status, type]);

  React.useEffect(() => { void load(); }, [load]);

  const label = (k: string) => types.find((t) => t.key === k)?.label ?? k;

  return (
    <Card className="nt-card">
      <div className="card-title">
        <div>
          <h2>Alert history</h2>
          <p>Every detected market intelligence event with its validation and delivery outcome. Duplicates are never stored twice.</p>
        </div>
        <div className="nt-filters">
          <select value={type} onChange={(e) => setType(e.target.value)} aria-label="Alert type">
            <option value="">All types</option>
            {types.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
          </select>
          <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
            <option value="">All statuses</option>
            {statuses.map((s) => <option key={s} value={s}>{s.replaceAll('_', ' ')}</option>)}
          </select>
          <button type="button" className="sc-btnSecondary sc-btnSmall" disabled={loading} onClick={() => void load()}><RefreshCcw /> Refresh</button>
        </div>
      </div>
      {error && <Notice title="Alert history" text={error} tone="warning" />}
      {rows.length === 0 ? (
        <Empty title={loading ? 'Loading…' : 'No alerts yet'} text="Alerts appear here when the engines confirm a channel break, touch, break & retest continuation or TiT setup on closed candles." />
      ) : (
        <div className="table-wrap">
          <table className="nt-table">
            <thead>
              <tr>
                <th>Event time</th><th>Alert</th><th>Symbol</th><th>TF</th><th>Direction</th><th>Price / Level</th><th>Provider</th><th>Status</th><th>Delivery</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((e) => (
                <React.Fragment key={e.id}>
                  <tr className="nt-row" onClick={() => setOpen(open === e.id ? null : e.id)}>
                    <td>{fmtTime(e.event_time)}</td>
                    <td>{label(e.event_type)}{e.tit_level ? ` · ${e.tit_level}` : ''}</td>
                    <td><b>{e.symbol}</b></td>
                    <td>{e.timeframe}</td>
                    <td>{e.direction ?? '—'}</td>
                    <td>{fmtPrice(e.price, e.symbol)} / {fmtPrice(e.level, e.symbol)}</td>
                    <td>{providerLabel(e.provider)}</td>
                    <td><span className={`nt-badge ${statusTone(e.status)}`}>{e.status.replaceAll('_', ' ')}</span></td>
                    <td>{e.deliveries.length ? `${e.deliveries.filter((d) => d.status === 'SENT').length}/${e.deliveries.length} sent` : '—'}</td>
                  </tr>
                  {open === e.id && (
                    <tr className="nt-rowDetail">
                      <td colSpan={9}>
                        <div className="detail-list">
                          <div><span>Detected</span><b>{fmtTime(e.detected_at)}</b></div>
                          <div><span>Sent</span><b>{fmtTime(e.sent_at)}</b></div>
                          {e.status_reason && <div><span>Reason</span><b>{e.status_reason}</b></div>}
                          {e.failure_reason && <div><span>Last failure</span><b>{e.failure_reason}</b></div>}
                        </div>
                        {e.deliveries.map((d) => (
                          <p className="muted" key={d.recipient_email}>
                            {d.recipient_email} — {d.status.replaceAll('_', ' ')} · attempts {d.attempt_count}
                            {d.sent_at ? ` · sent ${fmtTime(d.sent_at)}` : ''}
                            {d.next_attempt_at && d.status === 'RETRY_PENDING' ? ` · next attempt ${fmtTime(d.next_attempt_at)}` : ''}
                            {d.failure_reason ? ` · ${d.failure_reason}` : ''}
                          </p>
                        ))}
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

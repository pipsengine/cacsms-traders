import React from 'react';
import { Filter, Search } from 'lucide-react';
import { Card, Empty, PageHeader } from '../components/Ui';
import { get } from '../lib/api';
import type { AuditEvent } from '../types';

export function Audit({ tenantId }: { tenantId: string }) {
  const [rows, setRows] = React.useState<AuditEvent[]>([]);
  const [q, setQ] = React.useState('');

  React.useEffect(() => {
    if (!tenantId) return;
    get<AuditEvent[]>(`/tenants/${tenantId}/audit?limit=200`).then(setRows).catch(() => setRows([]));
  }, [tenantId]);

  const filtered = rows.filter(
    (e) =>
      !q ||
      e.action.toLowerCase().includes(q.toLowerCase()) ||
      (e.entity_type ?? '').toLowerCase().includes(q.toLowerCase()) ||
      (e.entity_id ?? '').toLowerCase().includes(q.toLowerCase()),
  );

  return (
    <>
      <PageHeader title="Audit Trail" subtitle="Reconstruct administrative and future autonomous decisions with correlation IDs." />
      <Card>
        <div className="toolbar">
          <div className="search">
            <Search />
            <input placeholder="Search action, user, entity or correlation ID…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <button type="button" className="secondary">
            <Filter />
            Filters
          </button>
        </div>
        {filtered.length === 0 ? (
          <Empty title="No audit events to display" text="Administrative actions on users, tenants, accounts and system mode appear here." />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>When</th>
                  <th>Action</th>
                  <th>Entity</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((e) => (
                  <tr key={e.id}>
                    <td>{e.created_at}</td>
                    <td>{e.action}</td>
                    <td>
                      {e.entity_type ?? '—'} {e.entity_id ?? ''}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}

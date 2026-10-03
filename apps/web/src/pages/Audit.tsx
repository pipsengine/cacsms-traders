import React from 'react';
import { Filter, Search } from 'lucide-react';
import { Card, Empty, PageHeader } from '../components/Ui';
import { get } from '../lib/api';
import type { AuditEvent } from '../types';

export function Audit({
  tenantId,
  embedded,
  category = 'all',
}: {
  tenantId: string;
  embedded?: boolean;
  category?: string;
}) {
  const [rows, setRows] = React.useState<AuditEvent[]>([]);
  const [q, setQ] = React.useState('');

  React.useEffect(() => {
    if (!tenantId) return;
    get<AuditEvent[]>(`/tenants/${tenantId}/audit?limit=200`).then(setRows).catch(() => setRows([]));
  }, [tenantId]);

  const categoryFiltered = rows.filter((e) => {
    if (category === 'all') return true;
    if (category === 'user') return e.action.includes('USER') || e.action.includes('TENANT');
    if (category === 'system') return e.action.includes('SYSTEM');
    if (category === 'security') return e.action.includes('AUTH') || e.action.includes('SECURITY');
    if (category === 'config') return e.action.includes('SETTINGS') || e.action.includes('MODE');
    return false;
  });

  const filtered = categoryFiltered.filter(
    (e) =>
      !q ||
      e.action.toLowerCase().includes(q.toLowerCase()) ||
      (e.entity_type ?? '').toLowerCase().includes(q.toLowerCase()) ||
      (e.entity_id ?? '').toLowerCase().includes(q.toLowerCase()),
  );

  return (
    <>
      {!embedded && <PageHeader title="Audit Trail" subtitle="Reconstruct administrative and future autonomous decisions with correlation IDs." />}
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

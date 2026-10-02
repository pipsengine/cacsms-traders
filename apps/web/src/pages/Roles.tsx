import React from 'react';
import { Shield } from 'lucide-react';
import { Card, Empty } from '../components/Ui';
import { get } from '../lib/api';

type Role = { id: string; name: string; description?: string; tenant_id: string };

export function Roles({ tenantId }: { tenantId: string }) {
  const [rows, setRows] = React.useState<Role[]>([]);

  React.useEffect(() => {
    if (!tenantId) return;
    get<Role[]>(`/tenants/${tenantId}/roles`).then(setRows).catch(() => setRows([]));
  }, [tenantId]);

  return (
    <>
      <Card>
        <div className="table-head">
          <div>
            <h2>Roles & permissions</h2>
            <p>Tenant-scoped RBAC roles enforced on the server for every API call.</p>
          </div>
        </div>
        {rows.length === 0 ? (
          <Empty
            title="No roles in this tenant"
            text="Create roles via the API or assign the platform administrator role during tenant bootstrap."
          />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Role</th>
                  <th>Description</th>
                  <th>ID</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <div className="entity">
                        <span className="entity-icon">
                          <Shield />
                        </span>
                        <b>{r.name}</b>
                      </div>
                    </td>
                    <td>{r.description ?? '—'}</td>
                    <td>{r.id}</td>
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

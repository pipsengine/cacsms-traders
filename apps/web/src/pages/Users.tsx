import React from 'react';
import { Plus, Search, UserRound } from 'lucide-react';
import { Card, PageHeader, Status } from '../components/Ui';
import { get, post } from '../lib/api';
import type { TenantUser } from '../types';

export function Users({ tenantId, onChanged }: { tenantId: string; onChanged: () => void }) {
  const [rows, setRows] = React.useState<TenantUser[]>([]);
  const [q, setQ] = React.useState('');

  React.useEffect(() => {
    if (!tenantId) return;
    get<TenantUser[]>(`/tenants/${tenantId}/users`).then(setRows).catch(() => setRows([]));
  }, [tenantId]);

  async function addUser() {
    const username = window.prompt('Username');
    if (!username) return;
    const first_name = window.prompt('First name') ?? 'New';
    const last_name = window.prompt('Last name') ?? 'User';
    const password = window.prompt('Temporary password (min 8 chars)');
    if (!password || password.length < 8) return;
    await post(`/tenants/${tenantId}/users`, { username, first_name, last_name, password });
    onChanged();
    setRows(await get<TenantUser[]>(`/tenants/${tenantId}/users`));
  }

  const filtered = rows.filter(
    (u) =>
      !q ||
      u.display_name.toLowerCase().includes(q.toLowerCase()) ||
      u.username.toLowerCase().includes(q.toLowerCase()) ||
      (u.email ?? '').toLowerCase().includes(q.toLowerCase()),
  );

  return (
    <>
      <PageHeader
        title="Users & Access"
        subtitle="Tenant memberships, profiles, roles and server-enforced permissions."
        action={
          <button type="button" className="primary" onClick={addUser}>
            <Plus />
            Add User
          </button>
        }
      />
      <Card>
        <div className="toolbar">
          <div className="search">
            <Search />
            <input placeholder="Search users, email or role…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>User</th>
                <th>Username</th>
                <th>Role</th>
                <th>Timezone</th>
                <th>Status</th>
                <th>Last Login</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((u) => (
                <tr key={u.id}>
                  <td>
                    <div className="entity">
                      <span className="avatar-sm">
                        <UserRound />
                      </span>
                      <div>
                        <b>{u.display_name}</b>
                        <small>{u.email ?? '—'}</small>
                      </div>
                    </div>
                  </td>
                  <td>{u.username}</td>
                  <td>{u.role_name ?? '—'}</td>
                  <td>{u.timezone ?? '—'}</td>
                  <td>
                    <Status value={u.status} />
                  </td>
                  <td>{u.last_login_at ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}

import { Building2, Plus } from 'lucide-react';
import { Card, PageHeader, Status } from '../components/Ui';
import { post } from '../lib/api';
import type { Tenant } from '../types';

export function Tenants({
  tenants,
  onCreated,
  isPlatformAdmin,
}: {
  tenants: Tenant[];
  onCreated: () => void;
  isPlatformAdmin: boolean;
}) {
  async function createTenant() {
    if (!isPlatformAdmin) return;
    const name = window.prompt('Tenant name');
    if (!name) return;
    const slug = (window.prompt('Slug (unique)', name.toLowerCase().replace(/\s+/g, '-')) ?? '').trim();
    const reporting_currency = (window.prompt('Reporting currency: USD or NGN', 'USD') ?? 'USD').toUpperCase();
    await post('/tenants', { name, slug, reporting_currency });
    onCreated();
  }

  return (
    <>
      <PageHeader
        title="Tenants"
        subtitle="Manage isolated organizations and their platform context."
        action={
          isPlatformAdmin ? (
            <button type="button" className="primary" onClick={createTenant}>
              <Plus />
              New Tenant
            </button>
          ) : undefined
        }
      />
      <Card>
        <div className="table-head">
          <div>
            <h2>Tenant directory</h2>
            <p>{tenants.length} tenant workspace(s)</p>
          </div>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Tenant</th>
                <th>Slug</th>
                <th>Reporting Currency</th>
                <th>Timezone</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {tenants.map((t) => (
                <tr key={t.id}>
                  <td>
                    <div className="entity">
                      <span className="entity-icon">
                        <Building2 />
                      </span>
                      <div>
                        <b>{t.name}</b>
                        <small>{t.id}</small>
                      </div>
                    </div>
                  </td>
                  <td>{t.slug}</td>
                  <td>{t.reporting_currency}</td>
                  <td>{t.timezone}</td>
                  <td>
                    <Status value={t.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}

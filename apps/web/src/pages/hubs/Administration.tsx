import { useState } from 'react';
import { PageHeader } from '../../components/Ui';
import { PageTabs, TabPanel } from '../../components/PageTabs';
import { Tenants } from '../Tenants';
import { Users } from '../Users';
import { Roles } from '../Roles';
import { AccountsPanel } from '../hub-panels/AccountsPanel';
import { Profile } from '../Profile';
import type { AuthUser, Tenant } from '../../types';
import { writeHashRoute } from '../../lib/routes';

const TABS = [
  { id: 'tenants', label: 'Tenants' },
  { id: 'users', label: 'Users' },
  { id: 'roles', label: 'Roles & Permissions' },
  { id: 'accounts', label: 'Trading Accounts' },
  { id: 'profile', label: 'User Profile' },
];

export function Administration({
  initialTab = 'tenants',
  tenants,
  tenantId,
  user,
  onRefresh,
  onLogout,
  isPlatformAdmin,
}: {
  initialTab?: string;
  tenants: Tenant[];
  tenantId: string;
  user: AuthUser;
  onRefresh: () => void;
  onLogout: () => void;
  isPlatformAdmin: boolean;
}) {
  const [tab, setTab] = useState(TABS.some((t) => t.id === initialTab) ? initialTab : 'tenants');
  const pickTab = (id: string) => {
    setTab(id);
    writeHashRoute('administration', id);
  };

  return (
    <>
      <PageHeader title="Administration" subtitle="Tenants, identity, access control, trading accounts and your profile." />
      <PageTabs tabs={TABS} active={tab} onChange={pickTab} />
      <TabPanel active={tab} id="tenants">
        <Tenants tenants={tenants} onCreated={onRefresh} isPlatformAdmin={isPlatformAdmin} />
      </TabPanel>
      <TabPanel active={tab} id="users">
        <Users tenantId={tenantId} onChanged={onRefresh} />
      </TabPanel>
      <TabPanel active={tab} id="roles">
        <Roles tenantId={tenantId} />
      </TabPanel>
      <TabPanel active={tab} id="accounts">
        <AccountsPanel tenantId={tenantId} tenant={tenants.find((t) => t.id === tenantId)} onChanged={onRefresh} />
      </TabPanel>
      <TabPanel active={tab} id="profile">
        <Profile user={user} onChanged={onRefresh} onLogout={onLogout} />
      </TabPanel>
    </>
  );
}

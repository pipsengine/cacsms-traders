import React from 'react';
import { AppShell } from './components/AppShell';
import { Overview } from './pages/Overview';
import { Tenants } from './pages/Tenants';
import { Users } from './pages/Users';
import { Accounts } from './pages/Accounts';
import { Connections } from './pages/Connections';
import { System } from './pages/System';
import { Audit } from './pages/Audit';
import { Profile } from './pages/Profile';
import { Login } from './pages/Login';
import { get, post } from './lib/api';
import type { AuthUser, Health, Page, Summary, Tenant } from './types';

export function App() {
  const [authed, setAuthed] = React.useState(!!localStorage.getItem('ct_token'));
  const [page, setPage] = React.useState<Page>('overview');
  const [user, setUser] = React.useState<AuthUser | null>(null);
  const [health, setHealth] = React.useState<Health | null>(null);
  const [summary, setSummary] = React.useState<Summary | null>(null);
  const [tenants, setTenants] = React.useState<Tenant[]>([]);
  const [tenantId, setTenantId] = React.useState<string>('');

  const refresh = React.useCallback(async () => {
    const [h, s, t, me] = await Promise.all([
      get<Health>('/health'),
      get<Summary>('/dashboard/summary'),
      get<Tenant[]>('/tenants'),
      get<AuthUser>('/auth/me'),
    ]);
    setHealth(h);
    setSummary(s);
    setTenants(t);
    setUser(me);
    setTenantId((prev) => prev || me.memberships?.[0]?.tenant_id || t[0]?.id || '');
  }, []);

  React.useEffect(() => {
    if (!authed) return;
    refresh().catch(() => {
      localStorage.removeItem('ct_token');
      setAuthed(false);
    });
  }, [authed, refresh]);

  async function logout() {
    try {
      await post('/auth/logout', {});
    } catch {
      /* ignore */
    }
    localStorage.removeItem('ct_token');
    setAuthed(false);
    setUser(null);
  }

  if (!authed) {
    return <Login onSuccess={() => setAuthed(true)} />;
  }

  if (!user) {
    return (
      <div className="login-screen">
        <div className="login-card">
          <p className="login-lead">Loading platform session…</p>
        </div>
      </div>
    );
  }

  const activeTenant = tenants.find((t) => t.id === tenantId) ?? tenants[0];

  let body: React.ReactNode;
  switch (page) {
    case 'tenants':
      body = <Tenants tenants={tenants} onCreated={refresh} isPlatformAdmin={!!user?.is_platform_admin} />;
      break;
    case 'users':
      body = <Users tenantId={activeTenant?.id ?? ''} onChanged={refresh} />;
      break;
    case 'accounts':
      body = <Accounts tenantId={activeTenant?.id ?? ''} onChanged={refresh} />;
      break;
    case 'connections':
      body = <Connections tenantId={activeTenant?.id ?? ''} />;
      break;
    case 'system':
      body = <System mode={summary?.mode ?? 'ANALYSIS_ONLY'} onChanged={refresh} isPlatformAdmin={!!user?.is_platform_admin} />;
      break;
    case 'audit':
      body = <Audit tenantId={activeTenant?.id ?? ''} />;
      break;
    case 'profile':
      body = <Profile user={user} onChanged={refresh} onLogout={logout} />;
      break;
    default:
      body = <Overview health={health} summary={summary} instrumentCount={29} />;
  }

  return (
    <AppShell
      page={page}
      setPage={setPage}
      user={user}
      tenants={tenants}
      tenantId={activeTenant?.id ?? ''}
      onTenantChange={setTenantId}
      mode={summary?.mode ?? 'ANALYSIS_ONLY'}
      onLogout={logout}
    >
      {body}
    </AppShell>
  );
}

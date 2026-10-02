import React from 'react';
import {
  Activity,
  Building2,
  ChevronDown,
  CircleUserRound,
  LayoutDashboard,
  Menu,
  MonitorCog,
  PlugZap,
  ShieldCheck,
  Users,
  WalletCards,
} from 'lucide-react';
import type { AuthUser, Page, Tenant } from '../types';

const nav: [string, { page: Page; label: string; icon: React.ReactNode }[]][] = [
  [
    'PLATFORM',
    [
      { page: 'overview', label: 'Overview', icon: <LayoutDashboard /> },
      { page: 'tenants', label: 'Tenants', icon: <Building2 /> },
      { page: 'users', label: 'Users & Access', icon: <Users /> },
    ],
  ],
  [
    'TRADING FOUNDATION',
    [
      { page: 'accounts', label: 'Trading Accounts', icon: <WalletCards /> },
      { page: 'connections', label: 'MT5 Connections', icon: <PlugZap /> },
    ],
  ],
  [
    'SYSTEM',
    [
      { page: 'system', label: 'System Control', icon: <MonitorCog /> },
      { page: 'audit', label: 'Audit Trail', icon: <ShieldCheck /> },
    ],
  ],
];

export function AppShell({
  page,
  setPage,
  children,
  user,
  tenants,
  tenantId,
  onTenantChange,
  mode,
  onLogout,
}: {
  page: Page;
  setPage: (p: Page) => void;
  children: React.ReactNode;
  user: AuthUser | null;
  tenants: Tenant[];
  tenantId: string;
  onTenantChange: (id: string) => void;
  mode: string;
  onLogout: () => void;
}) {
  const [collapsed, setCollapsed] = React.useState(false);
  const active = tenants.find((t) => t.id === tenantId);

  return (
    <div className="shell">
      <aside className={collapsed ? 'side collapsed' : 'side'}>
        <div className="brand">
          <div className="mark">C</div>
          {!collapsed && (
            <div>
              <b>Cacsms-Traders</b>
              <span>Autonomous Trading Platform</span>
            </div>
          )}
          <button type="button" onClick={() => setCollapsed(!collapsed)}>
            <Menu />
          </button>
        </div>
        <nav>
          {nav.map(([section, items]) => (
            <div key={section}>
              {!collapsed && <div className="nav-section">{section}</div>}
              {items.map((n) => (
                <button
                  type="button"
                  key={n.page}
                  className={page === n.page ? 'nav active' : 'nav'}
                  onClick={() => setPage(n.page)}
                >
                  {n.icon}
                  {!collapsed && <span>{n.label}</span>}
                </button>
              ))}
            </div>
          ))}
        </nav>
        <div className="side-foot">
          <div className="live-dot" />
          {!collapsed && (
            <div>
              <b>Foundation Mode</b>
              <span>{mode.replaceAll('_', ' ')}</span>
            </div>
          )}
        </div>
      </aside>
      <main className="workspace">
        <header className="top">
          <div className="crumb">
            <Activity size={17} />
            <span>Platform Foundation</span>
          </div>
          <div className="top-right">
            <div className="tenant-switch">
              <Building2 />
              <select value={tenantId} onChange={(e) => onTenantChange(e.target.value)} aria-label="Active tenant">
                {tenants.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
              <ChevronDown />
            </div>
            <button type="button" className="profile" onClick={() => setPage('profile')}>
              <CircleUserRound />
              <span>{user?.display_name ?? active?.name ?? 'User'}</span>
            </button>
            <button type="button" className="secondary" onClick={onLogout}>
              Sign out
            </button>
          </div>
        </header>
        <div className="page">{children}</div>
      </main>
    </div>
  );
}

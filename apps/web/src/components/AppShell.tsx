import React from 'react';
import {
  Activity,
  BarChart3,
  Building2,
  ChevronDown,
  CircleUserRound,
  GitBranch,
  LayoutDashboard,
  LineChart,
  Menu,
  MonitorCog,
  ScanSearch,
  Settings2,
  Shield,
  Target,
  TrendingUp,
  Workflow,
  Zap,
} from 'lucide-react';
import type { AuthUser, Tenant } from '../types';
import type { Page } from '../lib/routes';
import { PAGE_CRUMB } from '../lib/routes';

const nav: [string, { page: Page; label: string; icon: React.ReactNode }[]][] = [
  [
    'AUTONOMOUS TRADER',
    [
      { page: 'overview', label: 'Overview', icon: <LayoutDashboard /> },
      { page: 'workflow-engine', label: 'Workflow Engine', icon: <Workflow /> },
    ],
  ],
  [
    'MARKET INTELLIGENCE',
    [
      { page: 'strength-intelligence', label: 'Strength Intelligence', icon: <TrendingUp /> },
      { page: 'market-scanner', label: 'Market Scanner', icon: <ScanSearch /> },
    ],
  ],
  [
    'MARKET VISION',
    [
      { page: 'market-structure', label: 'Market Structure', icon: <LineChart /> },
      { page: 'channel-intelligence', label: 'Channel Intelligence', icon: <GitBranch /> },
    ],
  ],
  [
    'TRADING',
    [
      { page: 'trading-opportunities', label: 'Trading Opportunities', icon: <Target /> },
      { page: 'risk-portfolio', label: 'Risk & Portfolio', icon: <Shield /> },
      { page: 'execution-positions', label: 'Execution & Positions', icon: <Zap /> },
    ],
  ],
  [
    'ANALYTICS',
    [{ page: 'performance-learning', label: 'Performance & Learning', icon: <BarChart3 /> }],
  ],
  [
    'ADMINISTRATION',
    [{ page: 'administration', label: 'Administration', icon: <Settings2 /> }],
  ],
  [
    'SYSTEM',
    [{ page: 'system-control', label: 'System Control', icon: <MonitorCog /> }],
  ],
];

export function AppShell({
  page,
  navigate,
  children,
  user,
  tenants,
  tenantId,
  onTenantChange,
  mode,
  onLogout,
  onOpenProfile,
}: {
  page: Page;
  navigate: (page: Page, tab?: string) => void;
  children: React.ReactNode;
  user: AuthUser | null;
  tenants: Tenant[];
  tenantId: string;
  onTenantChange: (id: string) => void;
  mode: string;
  onLogout: () => void;
  onOpenProfile: () => void;
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
              <span>Autonomous Trader</span>
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
                  onClick={() => navigate(n.page)}
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
              <b>{mode.replaceAll('_', ' ')}</b>
              <span>Operations interface</span>
            </div>
          )}
        </div>
      </aside>
      <main className="workspace">
        <header className="top">
          <div className="crumb">
            <Activity size={17} />
            <span>{PAGE_CRUMB[page] ?? 'Overview'}</span>
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
            <button type="button" className="profile" onClick={onOpenProfile}>
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

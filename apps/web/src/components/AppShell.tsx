import React from 'react';
import {
  Activity,
  BarChart3,
  BrainCircuit,
  Building2,
  ChevronDown,
  Search,
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
import type { AuthUser, Health, Tenant } from '../types';
import type { Page } from '../lib/routes';
import { PAGE_CRUMB } from '../lib/routes';
import { TopBarStatus } from './TopBarStatus';
import { NotificationBell } from './NotificationBell';

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
      { page: 'h8-bos-btl', label: 'H8 BOS & BTL Intelligence', icon: <BarChart3 /> },
      { page: 'channel-intelligence', label: 'Channel Intelligence', icon: <GitBranch /> },
      { page: 'ai-market-outlook', label: 'AI Market Outlook', icon: <BrainCircuit /> },
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
  health,
  autonomousStatus,
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
  health: Health | null;
  autonomousStatus: string;
  onLogout: () => void;
  onOpenProfile: () => void;
}) {
  const narrowQuery = '(max-width: 1600px), (max-height: 920px)';
  const [collapsed, setCollapsed] = React.useState(
    () => typeof window !== 'undefined' && window.matchMedia(narrowQuery).matches,
  );
  const active = tenants.find((t) => t.id === tenantId);
  const initials = React.useMemo(() => {
    const name = user?.display_name ?? user?.username ?? 'U';
    const parts = name.trim().split(/\s+/).filter(Boolean);
    if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
    return name.slice(0, 2).toUpperCase();
  }, [user?.display_name, user?.username]);
  const roleLabel = user?.is_platform_admin ? 'Administrator' : user?.memberships?.[0]?.role_name ?? 'Operator';

  React.useEffect(() => {
    const mq = window.matchMedia(narrowQuery);
    const onChange = () => {
      if (mq.matches) setCollapsed(true);
    };
    onChange();
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);

  return (
    <div
      className={[
        collapsed ? 'shell shell--collapsed' : 'shell',
        page === 'overview' ? 'shell--overview' : '',
      ]
        .filter(Boolean)
        .join(' ')}
    >
      <aside className={collapsed ? 'side collapsed' : 'side'} aria-label="Main navigation">
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
                  onClick={() => navigate(n.page)}
                >
                  {n.icon}
                  {!collapsed && <span>{n.label}</span>}
                </button>
              ))}
            </div>
          ))}
        </nav>
        <div className={`side-foot side-foot-status ${collapsed ? '' : 'side-foot-figma'}`}>
          {!collapsed ? (
            <div className="side-foot-lines">
              <div className="side-status-row">
                <i className="side-dot green" aria-hidden />
                <div>
                  <span>Operating mode</span>
                  <b>{mode.replaceAll('_', ' ')}</b>
                </div>
              </div>
              <div className="side-status-row">
                <i
                  className={`side-dot ${
                    health?.market_data?.provider_status === 'CONNECTED'
                      ? 'green'
                      : 'red'
                  }`}
                  aria-hidden
                />
                <div>
                  <span>Market data</span>
                  <b>
                    {health?.market_data?.provider_status === 'CONNECTED'
                      ? `${health?.market_data?.active_provider === 'ctrader' ? 'cTrader' : health?.market_data?.active_provider} · CONNECTED`
                      : `${health?.market_data?.active_provider === 'ctrader' ? 'cTrader' : health?.market_data?.active_provider || 'NO PROVIDER'} · ${health?.market_data?.provider_status || 'UNAVAILABLE'}`}
                  </b>
                </div>
              </div>
            </div>
          ) : (
            <div className="live-dot" />
          )}
        </div>
      </aside>
      <main className="workspace">
        <header className={page === 'overview' ? 'top top--overview' : 'top'}>
          <div className="top-left-cluster">
            {page !== 'overview' && (
              <div className="crumb">
                <Activity size={17} />
                <span>{PAGE_CRUMB[page] ?? 'Overview'}</span>
              </div>
            )}
            <label className="top-search" aria-label="Search">
              <Search size={16} />
              <input type="search" placeholder="Search anything…" disabled title="Global search (coming soon)" />
              <kbd>Ctrl + K</kbd>
            </label>
          </div>
          <div className="top-right">
            <TopBarStatus />
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
            <NotificationBell tenantId={tenantId} navigate={navigate} />
            <button type="button" className="profile-figma" onClick={onOpenProfile}>
              <span className="profile-avatar" aria-hidden>
                {initials}
              </span>
              <span className="profile-figma-text">
                <b>{user?.display_name ?? active?.name ?? 'User'}</b>
                <span>{roleLabel}</span>
              </span>
            </button>
            <button type="button" className="secondary" onClick={onLogout} title="Sign out">
              Sign out
            </button>
          </div>
        </header>
        <div
          className={
            page === 'overview' ? 'page overview-page' : page === 'system-control' ? 'page sc-hub-page' : 'page'
          }
        >
          <div className="page-inner">{children}</div>
        </div>
      </main>
    </div>
  );
}

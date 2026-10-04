import React from 'react';
import { AppShell } from './components/AppShell';
import { Overview } from './pages/Overview';
import { Login } from './pages/Login';
import { WorkflowEngine } from './pages/WorkflowEngine';
import { MarketScanner } from './pages/MarketScanner';
import { MarketStructure } from './pages/MarketStructure';
import { ChannelIntelligence } from './pages/ChannelIntelligence';
import { H8BosBtl } from './pages/H8BosBtl';
import { TradingOpportunities } from './pages/TradingOpportunities';
import { RiskPortfolio } from './pages/RiskPortfolio';
import { ExecutionPositions } from './pages/ExecutionPositions';
import { PerformanceLearning } from './pages/PerformanceLearning';
import { Administration } from './pages/hubs/Administration';
import { SystemControl } from './pages/hubs/SystemControl';
import { StrengthIntelligence } from './pages/hubs/StrengthIntelligence';
import { get, post } from './lib/api';
import type { AuthUser, Health, Summary, Tenant, AppRouteState } from './types';
import type { Page } from './lib/routes';
import { LEGACY_ROUTE, parseHashRoute, writeHashRoute } from './lib/routes';
import { marketIntelligenceApi } from './features/market-intelligence/api';

export function App() {
  // null = session not yet checked; the session itself lives in an HttpOnly cookie.
  const [authed, setAuthed] = React.useState<boolean | null>(null);
  const [route, setRoute] = React.useState<AppRouteState>(() => parseHashRoute());
  const [user, setUser] = React.useState<AuthUser | null>(null);
  const [health, setHealth] = React.useState<Health | null>(null);
  const [summary, setSummary] = React.useState<Summary | null>(null);
  const [tenants, setTenants] = React.useState<Tenant[]>([]);
  const [tenantId, setTenantId] = React.useState<string>(() => localStorage.getItem('ct_tenant_id') || '');

  const selectTenant = React.useCallback((id: string) => {
    setTenantId(id);
    if (id) localStorage.setItem('ct_tenant_id', id);
  }, []);
  const [autonomousStatus, setAutonomousStatus] = React.useState('Checking…');

  const navigate = React.useCallback((page: Page, tab?: string) => {
    setRoute({ page, tab });
    writeHashRoute(page, tab);
  }, []);

  React.useEffect(() => {
    const onHash = () => setRoute(parseHashRoute());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  const refresh = React.useCallback(async () => {
    const [h, s, t, me] = await Promise.all([
      get<Health>('/system/health'),
      get<Summary>('/dashboard/summary'),
      get<Tenant[]>('/tenants'),
      get<AuthUser>('/auth/me'),
    ]);
    setHealth(h);
    setSummary(s);
    setTenants(t);
    setUser(me);
    setTenantId((prev) => {
      const next = prev || me.memberships?.[0]?.tenant_id || t[0]?.id || '';
      if (next) localStorage.setItem('ct_tenant_id', next);
      return next;
    });
    marketIntelligenceApi
      .health()
      .then((mi) => setAutonomousStatus(mi.status === 'ready' ? 'Intelligence ready' : 'Awaiting worker'))
      .catch(() => setAutonomousStatus(h.api === 'HEALTHY' ? 'Foundation online' : 'Degraded'));
  }, []);

  React.useEffect(() => {
    localStorage.removeItem('ct_token');
    get<AuthUser>('/auth/me')
      .then((me) => {
        setUser(me);
        setAuthed(true);
      })
      .catch(() => setAuthed(false));
  }, []);

  React.useEffect(() => {
    if (!authed) return;
    refresh().catch(() => {
      setUser(null);
      setAuthed(false);
    });
  }, [authed, refresh]);

  async function logout() {
    try {
      await post('/auth/logout', {});
    } catch {
      /* session already invalid */
    }
    setAuthed(false);
    setUser(null);
  }

  if (authed === null) {
    return (
      <div className="login-screen">
        <div className="login-card">
          <p className="login-lead">Checking session…</p>
        </div>
      </div>
    );
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

  const activeTenantId = tenantId || tenants[0]?.id || '';
  const activeTenant = tenants.find((t) => t.id === activeTenantId) ?? tenants[0];
  const tab = route.tab;

  let body: React.ReactNode;
  switch (route.page) {
    case 'workflow-engine':
      body = <WorkflowEngine />;
      break;
    case 'strength-intelligence':
      body = <StrengthIntelligence initialTab={tab} health={health} />;
      break;
    case 'market-scanner':
      body = <MarketScanner />;
      break;
    case 'market-structure':
      body = <MarketStructure />;
      break;
    case 'h8-bos-btl':
      body = <H8BosBtl />;
      break;
    case 'channel-intelligence':
      body = <ChannelIntelligence />;
      break;
    case 'trading-opportunities':
      body = <TradingOpportunities />;
      break;
    case 'risk-portfolio':
      body = <RiskPortfolio />;
      break;
    case 'execution-positions':
      body = <ExecutionPositions />;
      break;
    case 'performance-learning':
      body = <PerformanceLearning />;
      break;
    case 'administration':
      body = (
        <Administration
          initialTab={tab}
          tenants={tenants}
          tenantId={activeTenantId}
          user={user}
          onRefresh={refresh}
          onLogout={logout}
          isPlatformAdmin={!!user.is_platform_admin}
        />
      );
      break;
    case 'system-control':
      body = (
        <SystemControl
          initialTab={tab}
          tenantId={activeTenantId}
          health={health}
          summary={summary}
          onChanged={refresh}
          isPlatformAdmin={!!user.is_platform_admin}
          autonomousStatus={autonomousStatus}
        />
      );
      break;
    default:
      body = (
        <Overview
          health={health}
          summary={summary}
          tenant={activeTenant}
          tenantId={activeTenantId}
          instrumentCount={29}
        />
      );
  }

  return (
    <AppShell
      page={route.page}
      navigate={navigate}
      user={user}
      tenants={tenants}
      tenantId={activeTenantId}
      onTenantChange={selectTenant}
      mode={summary?.mode ?? 'ANALYSIS_ONLY'}
      health={health}
      autonomousStatus={autonomousStatus}
      onLogout={logout}
      onOpenProfile={() => navigate('administration', 'profile')}
    >
      {body}
    </AppShell>
  );
}

export default App;

// Re-export legacy route map for tests/documentation
export { LEGACY_ROUTE };

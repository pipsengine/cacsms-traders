export type Page =
  | 'overview'
  | 'workflow-engine'
  | 'strength-intelligence'
  | 'market-scanner'
  | 'market-structure'
  | 'h8-bos-btl'
  | 'channel-intelligence'
  | 'trading-opportunities'
  | 'risk-portfolio'
  | 'execution-positions'
  | 'performance-learning'
  | 'administration'
  | 'system-control';

/** Legacy sidebar ids → primary page + optional tab */
export const LEGACY_ROUTE: Record<
  string,
  { page: Page; tab?: string }
> = {
  tenants: { page: 'administration', tab: 'tenants' },
  users: { page: 'administration', tab: 'users' },
  accounts: { page: 'administration', tab: 'accounts' },
  profile: { page: 'administration', tab: 'profile' },
  connections: { page: 'system-control', tab: 'mt5' },
  system: { page: 'system-control', tab: 'mode' },
  engines: { page: 'system-control', tab: 'engines' },
  config: { page: 'system-control', tab: 'config' },
  audit: { page: 'system-control', tab: 'audit' },
  'strength-matrix': { page: 'strength-intelligence', tab: 'matrix' },
};

export const PAGE_CRUMB: Record<Page, string> = {
  overview: 'Overview',
  'workflow-engine': 'Workflow Engine',
  'strength-intelligence': 'Strength Intelligence',
  'market-scanner': 'Market Scanner',
  'market-structure': 'Market Structure',
  'h8-bos-btl': 'H8 BOS & BTL Intelligence',
  'channel-intelligence': 'Channel Intelligence',
  'trading-opportunities': 'Trading Opportunities',
  'risk-portfolio': 'Risk & Portfolio',
  'execution-positions': 'Execution & Positions',
  'performance-learning': 'Performance & Learning',
  administration: 'Administration',
  'system-control': 'System Control',
};

export function parseHashRoute(): { page: Page; tab?: string } {
  const raw = window.location.hash.replace(/^#\/?/, '') || 'overview';
  const [segment, tab] = raw.split('/');
  const legacy = LEGACY_ROUTE[segment];
  if (legacy) return { page: legacy.page, tab: tab ?? legacy.tab };
  if (segment in PAGE_CRUMB) return { page: segment as Page, tab };
  return { page: 'overview' };
}

export function writeHashRoute(page: Page, tab?: string) {
  const path = tab ? `${page}/${tab}` : page;
  if (window.location.hash.replace(/^#\/?/, '') !== path) {
    window.location.hash = `#/${path}`;
  }
}

export function resolvePage(id: string): { page: Page; tab?: string } {
  const legacy = LEGACY_ROUTE[id];
  if (legacy) return legacy;
  if (id in PAGE_CRUMB) return { page: id as Page };
  return { page: 'overview' };
}

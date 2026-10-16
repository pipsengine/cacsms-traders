import { useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  ArrowRight,
  BarChart3,
  BrainCircuit,
  ChevronLeft,
  ChevronRight,
  Columns3,
  Download,
  Eye,
  Filter,
  MoreHorizontal,
  Layers3,
  PieChart,
  Play,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  Target,
  TrendingDown,
  TrendingUp,
} from 'lucide-react';
import { InstrumentIcon } from '../features/market-scanner/components/InstrumentIcon';
import { engineApi } from '../features/cacsms-engine/api';
import { CampaignChartModal } from '../features/cacsms-engine/components/CampaignChartModal';
import type { Campaign, CampaignDetail, EngineResponse, Horizon, Stage } from '../features/cacsms-engine/types';

const steps = [
  {
    id: 'QUALIFICATION' as const,
    name: 'Opportunity Qualification',
    sub: 'Strategy and outlook',
    desc: 'Strategy setups keep their own rules. AI outlooks qualify at Evidence Score 70 or above.',
    icon: BrainCircuit,
    foot: 'Qualified Opportunities',
  },
  {
    id: 'CONFIRMATION' as const,
    name: 'Entry Confirmation',
    sub: 'Market Validation',
    desc: 'Wait for ERZ, reaction, BOS/CHoCH, breakout or retest on execution timeframes.',
    icon: Target,
    foot: 'Awaiting Confirmation',
  },
  {
    id: 'RISK' as const,
    name: 'Risk Authorization',
    sub: 'Risk Control',
    desc: 'Calculate position size, SL/TP, check exposure, margin and account limits.',
    icon: ShieldCheck,
    foot: 'Pending Authorization',
  },
  {
    id: 'EXECUTION' as const,
    name: 'Trade Execution',
    sub: 'Broker Orders',
    desc: 'Submit approved orders to MT5/cTrader and verify fills.',
    icon: Play,
    foot: 'Executing / Pending',
  },
  {
    id: 'MANAGEMENT' as const,
    name: 'Trade Management',
    sub: 'Lifecycle & Exit',
    desc: 'Manage open positions, trailing stops, targets, exits and campaign limits.',
    icon: BarChart3,
    foot: 'Open Positions',
  },
];

const sources: { key: string; label: string }[] = [
  { key: 'ALL', label: 'All horizons' },
  { key: 'DAILY', label: 'Daily' },
  { key: 'WEEKLY', label: 'Weekly' },
  { key: 'MONTHLY', label: 'Monthly' },
  { key: 'QUARTERLY', label: 'Quarterly' },
  { key: 'GOLD_H8', label: 'XAUUSD H8' },
];

const horizonMeta: { key: Horizon; label: string; color: string }[] = [
  { key: 'DAILY', label: 'Daily', color: '#3b82f6' },
  { key: 'WEEKLY', label: 'Weekly', color: '#8b5cf6' },
  { key: 'MONTHLY', label: 'Monthly', color: '#14b8a6' },
  { key: 'QUARTERLY', label: 'Quarterly', color: '#22c55e' },
  { key: 'GOLD_H8', label: 'Gold H8', color: '#f59e0b' },
];

const columnDefs = [
  { key: 'symbol', label: 'Symbol' },
  { key: 'source', label: 'Source' },
  { key: 'bias', label: 'AI Bias' },
  { key: 'score', label: 'Score' },
  { key: 'status', label: 'Setup Status' },
  { key: 'stage', label: 'Stage' },
  { key: 'positions', label: 'Positions' },
  { key: 'levels', label: 'Key Levels' },
  { key: 'next', label: 'Next Action' },
  { key: 'updated', label: 'Last Update' },
] as const;

type ColumnKey = (typeof columnDefs)[number]['key'];

const fmt = (value?: number | null) =>
  value == null ? '—' : new Intl.NumberFormat('en-US', { maximumFractionDigits: value >= 100 ? 3 : 5 }).format(value);

const human = (horizon: Horizon) =>
  ({ DAILY: 'Daily', WEEKLY: 'Weekly', MONTHLY: 'Monthly', QUARTERLY: 'Quarterly', GOLD_H8: 'H8' })[horizon];

const stageText = (stage: Stage) =>
  ({
    QUALIFICATION: '1 · Qualified',
    CONFIRMATION: '2 · Confirmation',
    RISK: '3 · Risk',
    EXECUTION: '4 · Execution',
    MANAGEMENT: '5 · Management',
    MONITORING: 'Monitoring',
    BLOCKED: 'Blocked',
    CLOSED: 'Closed',
  })[stage];

function pairOf(symbol: string) {
  if (symbol.startsWith('XAU')) return { base: 'XAU', quote: symbol.slice(3) || 'USD' };
  return { base: symbol.slice(0, 3), quote: symbol.slice(3, 6) };
}

function when(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return { day: '—', time: '' };
  return {
    day: parsed.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }),
    time: parsed.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }),
  };
}

function money(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return '';
  return `${value > 0 ? '+' : ''}${value.toFixed(2)}`;
}

function positionText(campaign: Campaign) {
  const open = campaign.positionsOpen;
  const pending = campaign.positionsPending;
  if (open > 0 && pending > 0) return `${open} open, ${pending} pending`;
  if (open > 0) return open === 1 ? '1 open' : `${open} open`;
  if (pending > 0) return pending === 1 ? '1 pending' : `${pending} pending`;
  return 'None';
}

function positionDetail(campaign: Campaign) {
  const live = campaign.brokerPositions ?? [];
  if (!live.length) return '';
  const first = live[0];
  const extra = live.length > 1 ? ` +${live.length - 1}` : '';
  const profit = money(first.profit);
  return `#${first.ticket}${extra}${profit ? ` · ${profit}` : ''}`;
}

function positionTitle(campaign: Campaign) {
  const live = campaign.brokerPositions ?? [];
  if (live.length) {
    return live.map((item) => {
      const profit = money(item.profit);
      return `MT5 #${item.ticket} ${item.direction} ${item.volume} at ${item.priceOpen}. Stop ${item.stopLoss || '—'}. Target ${item.takeProfit || '—'}. Price ${item.priceCurrent || '—'}${profit ? `. Floating ${profit}` : ''}.`;
    }).join(' ');
  }
  const allowance = campaign.maxPositions == null
    ? 'This horizon has no position-count ceiling.'
    : `The allowance for this symbol on this horizon is ${campaign.maxPositions}.`;
  if (!campaign.positionsOpen && !campaign.positionsPending) return `No broker position is open. ${allowance}`;
  return allowance;
}

const PAGE_SIZE = 8;
const stageRank: Record<Stage, number> = {
  MANAGEMENT: 0,
  EXECUTION: 1,
  RISK: 2,
  CONFIRMATION: 3,
  QUALIFICATION: 4,
  MONITORING: 5,
  BLOCKED: 6,
  CLOSED: 7,
};

function pageList(current: number, total: number): (number | 'gap')[] {
  if (total <= 7) return Array.from({ length: total }, (_, index) => index);
  const keep = [0, total - 1, current - 1, current, current + 1].filter((value, index, all) => value >= 0 && value < total && all.indexOf(value) === index);
  keep.sort((a, b) => a - b);
  const labels: (number | 'gap')[] = [];
  keep.forEach((value, index) => {
    if (index > 0 && value - keep[index - 1] > 1) labels.push('gap');
    labels.push(value);
  });
  return labels;
}

export function CacsmsEngine() {
  const [data, setData] = useState<EngineResponse | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [source, setSource] = useState('ALL');
  const [mode, setMode] = useState<'ALL' | 'STRATEGY' | 'OUTLOOK'>('ALL');
  const [stage, setStage] = useState('ALL');
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<CampaignDetail | null>(null);
  const [showFilters, setShowFilters] = useState(false);
  const [showColumns, setShowColumns] = useState(false);
  const [columns, setColumns] = useState<Record<ColumnKey, boolean>>(() =>
    Object.fromEntries(columnDefs.map((column) => [column.key, true])) as Record<ColumnKey, boolean>,
  );
  const [picked, setPicked] = useState<string[]>([]);
  const [menuId, setMenuId] = useState<string | null>(null);
  const [page, setPage] = useState(0);

  const inflight = useRef(false);
  const reload = async (initial = false, quiet = false) => {
    if (inflight.current) return;
    inflight.current = true;
    if (initial) setLoading(true);
    else if (!quiet) setBusy(true);
    try {
      const result = await engineApi.overview();
      setData(result);
      setError('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load engine');
    } finally {
      inflight.current = false;
      setLoading(false);
      setBusy(false);
    }
  };

  useEffect(() => {
    void reload(true);
    const id = window.setInterval(() => {
      if (document.visibilityState === 'visible') void reload(false, true);
    }, 1000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    if (!selected && !menuId && !showColumns) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      setSelected(null);
      setMenuId(null);
      setShowColumns(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [selected, menuId, showColumns]);

  const campaigns = useMemo(
    () =>
      (data?.campaigns.filter((campaign) => {
        const haystack = `${campaign.symbol} ${campaign.horizon} ${campaign.status} ${campaign.nextAction}`.toLowerCase();
        const modeOk = mode === 'ALL'
          || (mode === 'STRATEGY' && campaign.sourceMode !== 'OUTLOOK')
          || (mode === 'OUTLOOK' && campaign.sourceMode !== 'STRATEGY');
        const horizonOk = mode === 'STRATEGY' || source === 'ALL' || (campaign.sourceMode !== 'STRATEGY' && campaign.horizon === source);
        return modeOk && horizonOk && (stage === 'ALL' || campaign.stage === stage) && haystack.includes(search.toLowerCase());
      }) ?? []).slice().sort((a, b) => stageRank[a.stage] - stageRank[b.stage] || b.evidenceScore - a.evidenceScore),
    [data, source, stage, search, mode],
  );

  useEffect(() => {
    setPage(0);
  }, [source, stage, search, mode]);

  const counts = useMemo(() => {
    const rows = (data?.campaigns ?? []).filter((campaign) => (
      mode === 'ALL'
      || (mode === 'STRATEGY' && campaign.sourceMode !== 'OUTLOOK')
      || (mode === 'OUTLOOK' && campaign.sourceMode !== 'STRATEGY')
    ));
    return Object.fromEntries(
      sources.map((item) => [
        item.key,
        item.key === 'ALL'
          ? rows.length
          : rows.filter((campaign) => campaign.sourceMode !== 'STRATEGY' && campaign.horizon === item.key).length,
      ]),
    );
  }, [data, mode]);

  const view = async (campaign: Campaign) => {
    setMenuId(null);
    setSelected(campaign);
    try {
      setSelected(await engineApi.detail(campaign.id));
    } catch {
      setSelected(campaign);
    }
  };

  const download = () => {
    if (!data) return;
    const rows = picked.length ? campaigns.filter((campaign) => picked.includes(campaign.id)) : campaigns;
    const header = ['Symbol', 'Outlook', 'Direction', 'Evidence score', 'Stage', 'Status', 'Used slots', 'Maximum slots', 'Entry', 'Stop loss', 'Target 1', 'Next action', 'Last update'];
    const csv = [header, ...rows.map((campaign) => [
      campaign.symbol, human(campaign.horizon), campaign.direction, campaign.evidenceScore, stageText(campaign.stage),
      campaign.status, campaign.positionsUsed, campaign.maxPositions ?? '', campaign.entry ?? '', campaign.stopLoss ?? '',
      campaign.targets[0] ?? '', campaign.nextAction, campaign.updatedAt,
    ])].map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(',')).join('\n');
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = 'cacsms-engine-campaigns.csv';
    link.click();
    URL.revokeObjectURL(url);
  };

  const summary = data?.summary;
  const book = data?.campaigns ?? [];
  const watching = book.filter((campaign) => campaign.stage === 'MONITORING' || campaign.stage === 'QUALIFICATION').length;
  const confirmed = book.filter((campaign) => ['CONFIRMATION', 'RISK', 'EXECUTION', 'MANAGEMENT'].includes(campaign.stage)).length;
  const rejected = book.filter((campaign) => campaign.stage === 'BLOCKED').length;
  const closed = book.filter((campaign) => campaign.stage === 'CLOSED').length;
  const totalOpportunities = book.length;
  const strategyActive = book.filter((campaign) => campaign.sourceMode === 'STRATEGY' && campaign.stage !== 'CLOSED').length;
  const fxOpen = summary?.fxPositions ?? book.reduce((sum, campaign) => sum + (campaign.symbol === 'XAUUSD' ? 0 : campaign.positionsOpen), 0);
  const goldOpen = summary?.goldPositions ?? book.reduce((sum, campaign) => sum + (campaign.symbol === 'XAUUSD' ? campaign.positionsOpen : 0), 0);
  const horizonActive = (key: Horizon) => book.filter((campaign) => campaign.stage !== 'CLOSED' && campaign.sourceMode !== 'STRATEGY' && campaign.horizon === key).length;
  const horizonTotal = (horizonMeta.reduce((sum, item) => sum + horizonActive(item.key), 0) + strategyActive) || 1;
  const live = summary?.tradingMode === 'LIVE' || summary?.tradingMode === 'DEMO';
  const visibleColumns = columnDefs.filter((column) => columns[column.key]).length + 2;
  const pageCount = Math.max(1, Math.ceil(campaigns.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const pageStart = safePage * PAGE_SIZE;
  const pageRows = campaigns.slice(pageStart, pageStart + PAGE_SIZE);
  const pagePicked = pageRows.length > 0 && pageRows.every((campaign) => picked.includes(campaign.id));

  const stepCount = (id: (typeof steps)[number]['id']) => {
    if (!data) return null;
    if (id === 'MANAGEMENT') return summary?.openPositions ?? book.reduce((sum, campaign) => sum + campaign.positionsOpen, 0);
    return book.filter((campaign) => campaign.stage === id).length;
  };

  const togglePick = (id: string) => {
    setPicked((current) => (current.includes(id) ? current.filter((item) => item !== id) : [...current, id]));
  };

  return (
    <div className="ce">
      <div className="ce-heading">
        <div>
          <h1>
            Cacsms Engine <span className="ce-tag">Autonomous</span>
          </h1>
          <p>AI Market Outlook driven trading engine — 5-stage autonomous workflow from opportunity to position management.</p>
        </div>
        <div className="ce-actions">
          <button
            type="button"
            className={`ce-switch ${live ? 'is-on' : ''}`}
            aria-pressed={live}
            title={summary ? `Server mode ${summary.tradingMode}. This control does not change it.` : 'Waiting for the server mode'}
            onClick={(event) => event.preventDefault()}
          >
            {summary?.tradingMode === 'DEMO' ? 'Demo Trading' : 'Live Trading'}
            <i />
          </button>
          <button type="button" onClick={() => setShowFilters((open) => !open)}>
            <Settings2 size={15} /> Settings
          </button>
          <button type="button" onClick={() => void reload()} disabled={busy}>
            <RefreshCw size={15} className={busy ? 'ce-spin' : ''} /> Refresh
          </button>
          <button type="button" onClick={download} disabled={!data}>
            <Download size={15} /> Export
          </button>
        </div>
      </div>

      {error && (
        <div className="ce-error" role="alert">
          <AlertTriangle size={18} />
          <div>
            <b>Live engine data unavailable.</b> {error}. This page does not fabricate trading results.
          </div>
          <button type="button" onClick={() => void reload()}>Retry</button>
        </div>
      )}

      <div className="ce-steps">
        {steps.map((item, index) => {
          const Icon = item.icon;
          const count = stepCount(item.id);
          return (
            <div className="ce-step-slot" key={item.id}>
              {index > 0 && (
                <span className="ce-join" aria-hidden>
                  <ChevronRight size={18} />
                </span>
              )}
              <button
                type="button"
                className={`ce-step ce-step-${index}${count === 0 ? ' is-idle' : ' is-live'}${stage === item.id ? ' is-on' : ''}`}
                onClick={() => setStage(stage === item.id ? 'ALL' : item.id)}
                aria-pressed={stage === item.id}
                title={item.desc}
              >
                <div className="ce-step-title">
                  <span className="ce-num">{index + 1}</span>
                  <Icon size={20} />
                  <div>
                    <b>{item.name}</b>
                    <small>{item.sub}</small>
                  </div>
                </div>
                <p>{item.desc}</p>
                <div className="ce-step-foot">
                  <b>{count ?? '—'}</b>
                  <span>{item.foot}</span>
                  <ArrowRight size={15} />
                </div>
              </button>
            </div>
          );
        })}
      </div>

      <div className="ce-kpis">
        <article className="ce-kpi">
          <span className="ce-kpi-icon is-rose"><Target size={18} /></span>
          <div>
            <span>Total Opportunities</span>
            <strong>{data ? totalOpportunities : '—'}</strong>
            <ul className="ce-dots">
              <li className="is-watch">{watching} Watching</li>
              <li className="is-ok">{confirmed} In progress</li>
              <li className="is-wait">{closed} Closed</li>
              {rejected > 0 ? <li className="is-bad">{rejected} Rejected</li> : null}
            </ul>
          </div>
        </article>
        <article className="ce-kpi">
          <span className="ce-kpi-icon is-blue"><Layers3 size={18} /></span>
          <div>
            <span>Active Campaigns</span>
            <strong>{summary?.campaigns ?? '—'}</strong>
            <div className="ce-mix" aria-hidden>
              {horizonMeta.map((item) => (
                <i key={item.key} style={{ width: `${(horizonActive(item.key) / horizonTotal) * 100}%`, background: item.color }} />
              ))}
              <i style={{ width: `${(strategyActive / horizonTotal) * 100}%`, background: '#64748b' }} />
            </div>
            <ul className="ce-legend">
              {horizonMeta.map((item) => (
                <li key={item.key}><i style={{ background: item.color }} />{item.label} {horizonActive(item.key)}</li>
              ))}
              <li><i style={{ background: '#64748b' }} />Strategy {strategyActive}</li>
            </ul>
          </div>
        </article>
        <article className="ce-kpi">
          <span className="ce-kpi-icon is-green"><BarChart3 size={18} /></span>
          <div>
            <span>Open Positions</span>
            <strong>{summary?.openPositions ?? '—'}</strong>
            <ul className="ce-squares">
              <li className="is-fx">{fxOpen} FX Positions</li>
              <li className="is-gold">{goldOpen} XAUUSD Scalps</li>
              <li className="is-wait">{summary?.pendingOrders ?? 0} Pending Orders</li>
            </ul>
          </div>
        </article>
        <article className="ce-kpi">
          <span className="ce-kpi-icon is-violet"><PieChart size={18} /></span>
          <div>
            <span>Account Exposure</span>
            <strong>
              {summary?.exposurePercent == null ? '—' : `${summary.exposurePercent.toFixed(1)}%`}
              {summary?.exposurePercent != null && <small> of equity</small>}
            </strong>
            <div className="ce-meter">
              <span style={{ width: summary?.exposurePercent != null && summary.maxExposurePercent ? `${Math.min(100, (100 * summary.exposurePercent) / summary.maxExposurePercent)}%` : '0%' }} />
            </div>
            <div className="ce-allow">
              <span>Allowed: {summary?.maxExposurePercent == null ? '—' : `${summary.maxExposurePercent.toFixed(1)}%`}</span>
              <span>Remaining: {summary?.exposureRemainingPercent == null ? '—' : `${summary.exposureRemainingPercent.toFixed(1)}%`}</span>
            </div>
          </div>
        </article>
      </div>

      <section className="ce-card">
        <div className="ce-toolbar">
          <div className="ce-tabs" role="tablist" aria-label="Opportunity source">
            {([
              ['ALL', 'All Opportunities'],
              ['STRATEGY', 'Strategy-Based'],
              ['OUTLOOK', 'AI Market Outlook'],
            ] as const).map(([key, label]) => (
              <button key={key} type="button" className={mode === key ? 'is-on' : ''} onClick={() => setMode(key)}>
                {label}
                {key === 'STRATEGY' ? <span>({summary?.sourceCounts?.strategy ?? 0})</span> : null}
                {key === 'OUTLOOK' ? <span>({(summary?.sourceCounts?.outlook ?? 0) + (summary?.sourceCounts?.combined ?? 0)})</span> : null}
                {key === 'ALL' ? <span>({data?.campaigns.length ?? 0})</span> : null}
              </button>
            ))}
          </div>
        </div>
        <div className="ce-toolbar">
          {mode !== 'STRATEGY' && (
          <div className="ce-tabs" role="tablist" aria-label="Outlook horizon">
            {sources.map((item) => (
              <button key={item.key} type="button" className={source === item.key ? 'is-on' : ''} onClick={() => setSource(item.key)}>
                {item.label} <span>({counts[item.key] ?? 0})</span>
              </button>
            ))}
          </div>
          )}
          <div className="ce-tools">
            <label className="ce-search">
              <Search size={15} />
              <input aria-label="Search campaigns" placeholder="Search symbol, timeframe, stage…" value={search} onChange={(event) => setSearch(event.target.value)} />
            </label>
            <button type="button" aria-label="Toggle stage filters" className="ce-icon-btn" onClick={() => setShowFilters((open) => !open)}>
              <Filter size={16} />
            </button>
            <div className="ce-pop">
              <button type="button" className="ce-columns" onClick={() => setShowColumns((open) => !open)}>
                <Columns3 size={15} /> Columns
              </button>
              {showColumns && (
                <div className="ce-menu" role="menu">
                  {columnDefs.map((column) => (
                    <label key={column.key}>
                      <input
                        type="checkbox"
                        checked={columns[column.key]}
                        onChange={() => setColumns((current) => ({ ...current, [column.key]: !current[column.key] }))}
                      />
                      {column.label}
                    </label>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
        {showFilters && (
          <div className="ce-filters">
            <span>Workflow stage</span>
            <select aria-label="Filter by stage" value={stage} onChange={(event) => setStage(event.target.value)}>
              <option value="ALL">All stages</option>
              {['MONITORING', ...steps.map((item) => item.id), 'BLOCKED', 'CLOSED'].map((value) => (
                <option key={value} value={value}>{value}</option>
              ))}
            </select>
            <button type="button" onClick={() => { setStage('ALL'); setSearch(''); setSource('ALL'); setPicked([]); }}>Clear filters</button>
          </div>
        )}
        {loading ? (
          <div className="ce-state"><RefreshCw className="ce-spin" /> Loading engine data…</div>
        ) : (
          <div className="ce-scroll">
            <table>
              <thead>
                <tr>
                  <th className="ce-check">
                    <input
                      type="checkbox"
                      aria-label="Select campaigns on this page"
                      checked={pagePicked}
                      onChange={() => {
                        const ids = pageRows.map((campaign) => campaign.id);
                        setPicked((current) => (pagePicked ? current.filter((id) => !ids.includes(id)) : [...new Set([...current, ...ids])]));
                      }}
                    />
                  </th>
                  {columns.symbol && <th>Symbol</th>}
                  {columns.source && <th>Source</th>}
                  {columns.bias && <th>AI Bias</th>}
                  {columns.score && <th>Score</th>}
                  {columns.status && <th>Setup Status</th>}
                  {columns.stage && <th>Stage</th>}
                  {columns.positions && <th>Positions</th>}
                  {columns.levels && <th>Key Levels</th>}
                  {columns.next && <th>Next Action</th>}
                  {columns.updated && <th>Last Update</th>}
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {pageRows.map((campaign) => {
                  const stamp = when(campaign.updatedAt);
                  const outlookScore = campaign.sourceMode !== 'STRATEGY';
                  const passing = outlookScore && (campaign.outlookQualified || campaign.evidenceScore >= 70);
                  return (
                    <tr key={campaign.id} className={picked.includes(campaign.id) ? 'is-picked' : ''}>
                      <td className="ce-check">
                        <input type="checkbox" aria-label={`Select ${campaign.symbol}`} checked={picked.includes(campaign.id)} onChange={() => togglePick(campaign.id)} />
                      </td>
                      {columns.symbol && (
                        <td>
                          <span className="ce-symbol">
                            <InstrumentIcon {...pairOf(campaign.symbol)} />
                            <b>{campaign.symbol}</b>
                          </span>
                        </td>
                      )}
                      {columns.source && (
                        <td>
                          <span className={`ce-source is-${campaign.sourceMode === 'STRATEGY' ? 'weekly' : campaign.horizon.toLowerCase()}`}>
                            {campaign.sourceMode === 'STRATEGY'
                              ? campaign.strategyType
                              : campaign.sourceMode === 'COMBINED'
                                ? `${human(campaign.horizon)} · ${campaign.strategyType ?? 'Strategy'}`
                                : human(campaign.horizon)}
                          </span>
                        </td>
                      )}
                      {columns.bias && (
                        <td>
                          <span className={`ce-bias ${campaign.direction === 'SELL' ? 'is-bear' : campaign.direction === 'BUY' ? 'is-bull' : 'is-neutral'}`}>
                            {campaign.direction === 'SELL' ? <TrendingDown size={13} /> : <TrendingUp size={13} />}
                            {campaign.direction === 'SELL' ? 'Bearish' : campaign.direction === 'BUY' ? 'Bullish' : 'Neutral'}
                          </span>
                        </td>
                      )}
                      {columns.score && (
                    <td>
                      <span
                        className={`ce-score ${outlookScore ? (passing ? 'is-pass' : 'is-fail') : ''}`}
                        title={outlookScore ? 'AI Market Outlook evidence score for this symbol and horizon.' : 'Strategy qualification uses its own rules. This is not the AI Market Outlook score.'}
                      >
                        {Math.round(campaign.evidenceScore)}{outlookScore ? '%' : ''}
                      </span>
                    </td>
                  )}
                      {columns.status && (
                        <td>
                          <b className="ce-setup">{campaign.status}</b>
                          <small>{campaign.reason || 'Scenario state from outlook'}</small>
                        </td>
                      )}
                      {columns.stage && (
                        <td>
                          <span className={`ce-stage ce-stage-${campaign.stage.toLowerCase()}`} title={campaign.pipelineStage || undefined}>{stageText(campaign.stage)}</span>
                        </td>
                      )}
                      {columns.positions && (
                        <td className={campaign.positionsOpen || campaign.positionsPending ? 'ce-pos' : 'ce-pos-none'} title={positionTitle(campaign)}>
                          <b>{positionText(campaign)}</b>
                          {positionDetail(campaign) ? <small>{positionDetail(campaign)}</small> : null}
                        </td>
                      )}
                      {columns.levels && (
                        <td className="ce-levels">
                          <div>Entry: <b>{fmt(campaign.entry)}</b></div>
                          <div>SL: <b>{fmt(campaign.stopLoss)}</b></div>
                          <div>TP1: <b>{fmt(campaign.targets[0])}</b></div>
                        </td>
                      )}
                      {columns.next && <td className="ce-next">{campaign.nextAction}</td>}
                      {columns.updated && (
                        <td
                          className="ce-when"
                          title={campaign.publishedAt && campaign.publishedAt !== campaign.updatedAt
                            ? `Outlook published ${when(campaign.publishedAt).day} ${when(campaign.publishedAt).time}. Last engine check ${stamp.day} ${stamp.time}.`
                            : undefined}
                        >
                          <b>{stamp.day}</b>
                          <small>{stamp.time}</small>
                        </td>
                      )}
                      <td>
                        <div className="ce-actions-cell">
                        <button type="button" className="ce-view" onClick={() => void view(campaign)}><Eye size={14} /> View</button>
                        <div className="ce-pop">
                          <button type="button" className="ce-more" aria-label={`More actions for ${campaign.symbol}`} onClick={() => setMenuId(menuId === campaign.id ? null : campaign.id)}>
                            <MoreHorizontal size={16} />
                          </button>
                          {menuId === campaign.id && (
                            <div className="ce-menu is-row" role="menu">
                              <button type="button" onClick={() => void view(campaign)}>View campaign</button>
                            </div>
                          )}
                        </div>
                        </div>
                      </td>
                    </tr>
                  );
                })}
                {!campaigns.length && (
                  <tr>
                    <td colSpan={visibleColumns} className="ce-empty">{error ? 'Connect the live API to display campaigns.' : 'No campaigns match these filters.'}</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
        <div className="ce-foot">
          <span>
            Showing {campaigns.length ? pageStart + 1 : 0}–{Math.min(pageStart + PAGE_SIZE, campaigns.length)} of {campaigns.length}
            {picked.length ? ` · ${picked.length} selected` : ''}
          </span>
          <div className="ce-pages" role="navigation" aria-label="Campaign pages">
            <button type="button" aria-label="Previous page" disabled={safePage <= 0} onClick={() => setPage(safePage - 1)}>
              <ChevronLeft size={15} />
            </button>
            {pageList(safePage, pageCount).map((item, index) => (
              item === 'gap' ? <span key={`gap-${index}`}>…</span> : (
                <button key={item} type="button" className={item === safePage ? 'is-on' : ''} aria-current={item === safePage ? 'page' : undefined} onClick={() => setPage(item)}>
                  {item + 1}
                </button>
              )
            ))}
            <button type="button" aria-label="Next page" disabled={safePage >= pageCount - 1} onClick={() => setPage(safePage + 1)}>
              <ChevronRight size={15} />
            </button>
          </div>
          <span>Last sync: {data ? new Date(data.generatedAt).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '—'}</span>
        </div>
      </section>

      {selected ? <CampaignChartModal campaign={selected} onClose={() => setSelected(null)} /> : null}
    </div>
  );
}

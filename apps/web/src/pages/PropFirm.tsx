import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  Activity,
  Box,
  Brain,
  CalendarOff,
  ChartColumn,
  CircleCheck,
  CircleX,
  ClipboardList,
  Ellipsis,
  Gauge,
  Layers,
  LayoutDashboard,
  Monitor,
  Newspaper,
  Plus,
  ScrollText,
  Shield,
  ShieldCheck,
  SlidersHorizontal,
  TrendingDown,
  TrendingUp,
  UserRound,
  X,
} from 'lucide-react';
import { propApi } from '../features/prop-firm/api';
import type { PropAccountRow, PropOverview, PropRules } from '../features/prop-firm/types';

const TABS = [
  ['overview', 'Overview', <LayoutDashboard key="o" />],
  ['accounts', 'Accounts & Challenges', <ClipboardList key="a" />],
  ['risk', 'Risk & Compliance', <Shield key="r" />],
  ['performance', 'Trading Performance', <TrendingUp key="p" />],
  ['audit', 'Violations & Audit', <ScrollText key="v" />],
] as const;

const EMPTY_RULES: PropRules = {
  daily_loss_pct: 5,
  max_loss_pct: 10,
  drawdown_method: 'STATIC',
  daily_reference: 'BALANCE',
  reset_timezone: 'UTC',
  max_positions: 5,
  max_lot: 2,
  floating_loss_pct: 5,
  news_block_minutes: 5,
  weekend_holding: false,
  automation_permitted: false,
  permitted_strategies: ['TIT', 'CONTINUATION', 'P2_BREAKOUT_RETEST', 'OUTLOOK'],
  profit_target_pct: 10,
  slippage_buffer_pct: 0.2,
  emergency_close: false,
};

const FIRM_COLORS = ['#2f6fed', '#111827', '#7a5af8', '#e11d48', '#0f766e', '#c2410c'];
type TabId = (typeof TABS)[number][0];
type SnapshotPoint = { recorded_at: string; equity: number; balance: number };

function money(value: number | null) {
  if (value == null || Number.isNaN(value)) return '—';
  const digits = Math.abs(value) >= 1000 ? 0 : 2;
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value);
}

function signed(value: number | null) {
  if (value == null || Number.isNaN(value)) return '—';
  const text = money(Math.abs(value));
  if (value > 0) return `+${text}`;
  if (value < 0) return `-${text}`;
  return text;
}

function axisMoney(value: number) {
  const abs = Math.abs(value);
  const sign = value < 0 ? '-' : '';
  if (abs >= 1000) return `${sign}$${Math.round(abs / 1000)}K`;
  return money(value);
}

function pctText(value: number | null) {
  if (value == null || Number.isNaN(value)) return null;
  const text = `${value > 0 ? '+' : ''}${value.toFixed(2)}%`;
  return text;
}

function phaseWord(lifecycle: string) {
  if (lifecycle === 'EVALUATION_PHASE_1') return 'Phase 1';
  if (lifecycle === 'EVALUATION_PHASE_2') return 'Phase 2';
  if (lifecycle === 'FUNDED' || lifecycle === 'ACTIVE') return 'Live';
  return lifecycle.replaceAll('_', ' ').toLowerCase();
}

function kindWord(lifecycle: string) {
  if (lifecycle === 'FUNDED' || lifecycle === 'ACTIVE') return 'Funded';
  if (lifecycle.startsWith('EVALUATION')) return 'Evaluation';
  return 'Setup';
}

function statusClass(status: string) {
  if (status === 'At Risk') return 'is-risk';
  if (status === 'Trading') return 'is-trade';
  if (status === 'Suspended') return 'is-stop';
  return 'is-ok';
}

function firmColor(name: string) {
  let hash = 0;
  for (const char of name) hash = (hash + char.charCodeAt(0)) % FIRM_COLORS.length;
  return FIRM_COLORS[hash];
}

function initials(name: string) {
  const parts = name.replace(/[^A-Za-z0-9 ]/g, ' ').trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return 'PF';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
}

function smooth(points: Array<[number, number]>) {
  if (!points.length) return '';
  let path = `M${points[0][0]},${points[0][1]}`;
  for (let index = 0; index < points.length - 1; index += 1) {
    const [x0, y0] = points[index];
    const [x1, y1] = points[index + 1];
    const mid = (x0 + x1) / 2;
    path += ` C${mid},${y0} ${mid},${y1} ${x1},${y1}`;
  }
  return path;
}

export function PropFirm() {
  const [tab, setTab] = useState<TabId>('overview');
  const [data, setData] = useState<PropOverview | null>(null);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [firmName, setFirmName] = useState('');
  const [firmId, setFirmId] = useState('');
  const [rules, setRules] = useState<PropRules>(EMPTY_RULES);
  const [accountName, setAccountName] = useState('');
  const [login, setLogin] = useState('');
  const [server, setServer] = useState('');
  const [size, setSize] = useState('100000');
  const [broker, setBroker] = useState('MT5');
  const [environment, setEnvironment] = useState('DEMO');
  const [lifecycle, setLifecycle] = useState('REGISTERED');
  const [automation, setAutomation] = useState(false);

  const load = useCallback(async () => {
    try {
      const next = await propApi.overview();
      setData(next);
      setError('');
      setSelectedId((current) => current && next.accounts.some((row) => row.id === current) ? current : next.accounts[0]?.id ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Prop firm accounts are unavailable');
    }
  }, []);

  useEffect(() => {
    void load();
    const id = window.setInterval(() => {
      if (document.visibilityState === 'visible') void load();
    }, 5000);
    return () => window.clearInterval(id);
  }, [load]);

  const selected = data?.accounts.find((row) => row.id === selectedId) ?? null;
  const firm = data?.firms.find((item) => item.name === selected?.firm) ?? data?.firms[0] ?? null;
  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (data?.accounts ?? []).filter((row) => !q || `${row.firm} ${row.external_id} ${row.lifecycle} ${row.status}`.toLowerCase().includes(q));
  }, [data, query]);

  const save = async () => {
    setBusy(true);
    setError('');
    try {
      let chosen = firmId;
      let ruleVersion: string | undefined;
      if (!chosen) {
        const created = await propApi.createFirm(firmName, rules);
        chosen = created.id;
        ruleVersion = created.rule_version_id;
      }
      await propApi.createAccount({
        firm_id: chosen,
        rule_version_id: ruleVersion,
        display_name: accountName,
        broker,
        broker_login: login || null,
        broker_server: server || null,
        environment,
        lifecycle,
        phase_label: lifecycle.startsWith('EVALUATION') ? phaseWord(lifecycle) : 'Registration',
        account_size: Number(size),
        automation_confirmed: automation && !!rules.automation_permitted,
      });
      setFormOpen(false);
      setAccountName('');
      setLogin('');
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Account was not saved');
    } finally {
      setBusy(false);
    }
  };

  const fields = (
    <AccountFields
      data={data}
      firmId={firmId}
      setFirmId={setFirmId}
      firmName={firmName}
      setFirmName={setFirmName}
      accountName={accountName}
      setAccountName={setAccountName}
      broker={broker}
      setBroker={setBroker}
      login={login}
      setLogin={setLogin}
      server={server}
      setServer={setServer}
      size={size}
      setSize={setSize}
      environment={environment}
      setEnvironment={setEnvironment}
      lifecycle={lifecycle}
      setLifecycle={setLifecycle}
      automation={automation}
      setAutomation={setAutomation}
      rules={rules}
      setRules={setRules}
    />
  );

  return (
    <div className="pf">
      <aside className="pf-rail">
        <p>Prop firm management</p>
        <nav aria-label="Prop firm sections">
          {TABS.map(([id, label, icon]) => (
            <button key={id} type="button" className={tab === id ? 'is-on' : ''} onClick={() => setTab(id)}>
              {icon}
              {label}
            </button>
          ))}
        </nav>
      </aside>
      <div className="pf-main">
        <header className="pf-head">
          <div>
            <h1>Prop Firm Account Management</h1>
            <p>Evaluation and funded trading with firm-specific compliance and autonomous risk protection.</p>
          </div>
          <button type="button" className="pf-add" onClick={() => setFormOpen(true)}><Plus size={16} /> Add Prop Firm Account</button>
        </header>
        {error ? <p className="pf-error">{error}</p> : null}

        {tab === 'overview' && (
          <Overview
            data={data}
            rows={rows}
            query={query}
            setQuery={setQuery}
            selectedId={selectedId}
            setSelectedId={setSelectedId}
            firm={firm}
            onOpen={(id, next) => { setSelectedId(id); setTab(next); }}
          />
        )}
        {tab === 'accounts' && (
          <section className="pf-card pf-form">
            <h2>Register a firm and connect an account</h2>
            <p>Passwords are encrypted on the server and are never returned to this page. Evaluation passed and funded status need a firm-confirmed transition.</p>
            {fields}
            <button type="button" className="pf-add" disabled={busy || !accountName || (!firmId && firmName.length < 2)} onClick={() => void save()}>{busy ? 'Saving…' : 'Save account'}</button>
          </section>
        )}
        {tab === 'risk' && (
          <section className="pf-card pf-form">
            <h2>Version the firm rules</h2>
            <p>Saving creates a new rule version. Accounts keep the version they were registered with until that version is attached.</p>
            <RuleFields rules={rules} onChange={setRules} />
            <label>Firm
              <select value={firmId || firm?.id || ''} onChange={(event) => setFirmId(event.target.value)}>
                {data?.firms.map((item) => <option key={item.id} value={item.id}>{item.name} · v{item.version}</option>)}
              </select>
            </label>
            <button type="button" className="pf-add" disabled={!firmId && !firm} onClick={() => void propApi.versionRules(firmId || firm?.id || '', rules).then(load).catch((err) => setError(err instanceof Error ? err.message : 'Rules were not saved'))}>Save new rule version</button>
            <RiskOverview rules={firm?.rules ?? null} account={selected} />
          </section>
        )}
        {tab === 'performance' && <PerformanceTab data={data} selectedId={selectedId} setSelectedId={setSelectedId} />}
        {tab === 'audit' && <AuditTab reloadKey={data?.summary.accounts ?? 0} />}

        {formOpen && (
          <div className="pf-backdrop" onMouseDown={() => setFormOpen(false)}>
            <section className="pf-modal" onMouseDown={(event) => event.stopPropagation()} role="dialog" aria-labelledby="pf-add-title">
              <div className="pf-modal-head">
                <div>
                  <h2 id="pf-add-title">Add Prop Firm Account</h2>
                  <p className="pf-note">Connect an authorized MT5 or cTrader login. Credentials stay on the server.</p>
                </div>
                <button type="button" onClick={() => setFormOpen(false)} aria-label="Close"><X size={16} /></button>
              </div>
              <div className="pf-form">
                {fields}
                <button type="button" className="pf-add" disabled={busy || !accountName || (!firmId && firmName.length < 2)} onClick={() => void save()}>{busy ? 'Saving…' : 'Save account'}</button>
              </div>
            </section>
          </div>
        )}
      </div>
    </div>
  );
}

function Overview({
  data, rows, query, setQuery, selectedId, setSelectedId, firm, onOpen,
}: {
  data: PropOverview | null;
  rows: PropAccountRow[];
  query: string;
  setQuery: (value: string) => void;
  selectedId: string | null;
  setSelectedId: (id: string) => void;
  firm: PropOverview['firms'][number] | null;
  onOpen: (id: string, tab: TabId) => void;
}) {
  const summary = data?.summary;
  const profitPct = summary && summary.accounts ? Math.round((100 * summary.in_profit) / summary.accounts) : 0;
  const pnlPct = summary?.equity && summary.open_pnl != null ? (100 * summary.open_pnl) / summary.equity : null;
  const [chartAccount, setChartAccount] = useState('all');
  const [range, setRange] = useState<7 | 30 | 90>(30);
  const idsKey = data?.accounts.map((row) => row.id).join(',') ?? '';
  const points = useEquitySeries(chartAccount, idsKey, summary?.equity ?? null);

  return (
    <>
      <section className="pf-kpis">
        <article className="pf-kpi">
          <header><span>Total Prop Accounts</span><i className="pf-ico is-blue"><UserRound /></i></header>
          <strong>{summary ? summary.accounts : '—'}</strong>
          <footer><span>{summary?.evaluation ?? 0} Evaluation</span><span>{summary?.funded ?? 0} Funded</span></footer>
        </article>
        <article className="pf-kpi">
          <header><span>Total Equity</span><i className="pf-ico is-blue"><ChartColumn /></i></header>
          <strong>{money(summary?.equity ?? null)}</strong>
          <footer>{summary?.equity == null ? 'No snapshot yet' : 'Latest reconciled equity'}</footer>
        </article>
        <article className="pf-kpi">
          <header><span>Total Open P&L</span><i className={`pf-ico ${summary?.open_pnl == null ? 'is-blue' : summary.open_pnl >= 0 ? 'is-green' : 'is-red'}`}><TrendingUp /></i></header>
          <strong className={(summary?.open_pnl ?? 0) > 0 ? 'is-up' : (summary?.open_pnl ?? 0) < 0 ? 'is-down' : ''}>{signed(summary?.open_pnl ?? null)}</strong>
          <footer className={pnlPct != null && pnlPct < 0 ? 'is-down' : 'is-up'}>{pctText(pnlPct) ?? 'Floating result'}</footer>
        </article>
        <article className="pf-kpi">
          <header>
            <span>Accounts In Profit</span>
            <Ring value={profitPct} />
          </header>
          <strong>{summary ? `${summary.in_profit} / ${summary.accounts}` : '—'}</strong>
          <footer>{summary?.accounts ? `${profitPct}%` : 'No open result'}</footer>
        </article>
        <article className="pf-kpi">
          <header><span>Compliance Status</span><i className={`pf-ico ${summary?.compliant === false ? 'is-red' : 'is-green'}`}><ShieldCheck /></i></header>
          <strong className={`is-text ${summary?.compliant ? 'is-up' : ''}`}>{summary?.compliant == null ? 'No accounts' : summary.compliant ? 'All Accounts Safe' : 'Review required'}</strong>
          <footer>{summary?.compliant ? <span className="is-up"><CircleCheck size={14} /> No rule violations</span> : summary?.compliant === false ? 'A blocked decision is on record' : 'Register an account to monitor rules'}</footer>
        </article>
      </section>

      <section className="pf-card">
        <div className="pf-card-head">
          <h2>Prop Firm Accounts</h2>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search firm, account, status" aria-label="Search prop accounts" />
        </div>
        <AccountsTable rows={rows} selectedId={selectedId} onSelect={(id) => { setSelectedId(id); setChartAccount(id); }} onOpen={onOpen} empty={data ? 'No prop firm accounts are registered for this tenant.' : 'Loading accounts…'} />
      </section>

      <section className="pf-split">
        <article className="pf-card">
          <div className="pf-card-head">
            <h2>Account Performance</h2>
            <div className="pf-tools">
              <div className="pf-legend" aria-hidden>
                <span><i className="is-balance" />Balance</span>
                <span><i className="is-equity" />Equity</span>
              </div>
              <select className="pf-select" value={chartAccount} aria-label="Chart account" onChange={(event) => setChartAccount(event.target.value)}>
                <option value="all">All Accounts</option>
                {data?.accounts.map((row) => <option key={row.id} value={row.id}>{row.firm}</option>)}
              </select>
              <div className="pf-ranges" role="group" aria-label="Chart range">
                {([7, 30, 90] as const).map((days) => (
                  <button key={days} type="button" className={range === days ? 'is-on' : ''} onClick={() => setRange(days)}>{days}D</button>
                ))}
              </div>
            </div>
          </div>
          <PerformanceChart points={points} range={range} />
        </article>
        <article className="pf-card">
          <div className="pf-card-head">
            <h2>Challenge Progress</h2>
            <span className="pf-muted">All Evaluation Accounts</span>
          </div>
          <ChallengeTable rows={rows.filter((row) => kindWord(row.lifecycle) === 'Evaluation')} />
        </article>
      </section>

      <section className="pf-split">
        <article className="pf-card">
          <h2>Autonomous Trading Flow (Prop Firm Accounts)</h2>
          <Flow />
        </article>
        <article className="pf-card">
          <h2>Risk & Compliance Overview</h2>
          <RiskOverview rules={firm?.rules ?? null} account={data?.accounts.find((row) => row.id === (chartAccount === 'all' ? selectedId : chartAccount)) ?? null} />
        </article>
      </section>
    </>
  );
}

function Ring({ value }: { value: number }) {
  const radius = 16;
  const length = 2 * Math.PI * radius;
  const shown = Math.max(0, Math.min(100, value));
  return (
    <svg viewBox="0 0 44 44" className="pf-ring" aria-hidden>
      <circle cx="22" cy="22" r={radius} />
      <circle className="is-value" cx="22" cy="22" r={radius} strokeDasharray={`${(shown / 100) * length} ${length}`} />
      <text x="22" y="25" textAnchor="middle">{shown}%</text>
    </svg>
  );
}

function AccountsTable({
  rows, selectedId, onSelect, onOpen, empty,
}: {
  rows: PropAccountRow[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onOpen: (id: string, tab: TabId) => void;
  empty: string;
}) {
  const [sort, setSort] = useState<{ key: keyof PropAccountRow; dir: 1 | -1 }>({ key: 'firm', dir: 1 });
  const [page, setPage] = useState(0);
  const [menuId, setMenuId] = useState<string | null>(null);
  const pageSize = 8;
  const sorted = useMemo(() => {
    const list = [...rows];
    list.sort((left, right) => {
      const a = left[sort.key];
      const b = right[sort.key];
      if (typeof a === 'number' && typeof b === 'number') return (a - b) * sort.dir;
      return String(a ?? '').localeCompare(String(b ?? '')) * sort.dir;
    });
    return list;
  }, [rows, sort]);
  const pages = Math.max(1, Math.ceil(sorted.length / pageSize));
  const view = sorted.slice(page * pageSize, page * pageSize + pageSize);
  const signature = rows.map((row) => row.id).join(',');
  useEffect(() => { setPage(0); }, [signature]);
  useEffect(() => {
    if (!menuId) return;
    const close = () => setMenuId(null);
    window.addEventListener('click', close);
    return () => window.removeEventListener('click', close);
  }, [menuId]);

  const head = (key: keyof PropAccountRow, label: string) => (
    <th>
      <button type="button" onClick={() => setSort((current) => ({ key, dir: current.key === key ? (current.dir * -1) as 1 | -1 : 1 }))}>{label}</button>
    </th>
  );

  return (
    <>
      <div className="pf-table-wrap">
        <table>
          <thead>
            <tr>
              {head('firm', 'Firm')}
              {head('external_id', 'Account ID')}
              {head('lifecycle', 'Type')}
              {head('phase', 'Phase')}
              {head('balance', 'Balance')}
              {head('equity', 'Equity')}
              {head('daily_pnl', 'Daily P&L')}
              {head('daily_drawdown_pct', 'Drawdown')}
              {head('progress_pct', 'Profit Target')}
              {head('status', 'Status')}
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {view.map((row) => (
              <tr key={row.id} className={row.id === selectedId ? 'is-on' : ''} onClick={() => onSelect(row.id)}>
                <td><span className="pf-firm"><i style={{ background: firmColor(row.firm) }}>{initials(row.firm)}</i>{row.firm}</span></td>
                <td>{row.external_id}</td>
                <td><span className={`pf-pill ${kindWord(row.lifecycle) === 'Funded' ? 'is-green' : kindWord(row.lifecycle) === 'Evaluation' ? 'is-blue' : 'is-gray'}`}>{kindWord(row.lifecycle)}</span></td>
                <td>{row.phase || phaseWord(row.lifecycle)}</td>
                <td>{money(row.balance)}</td>
                <td>{money(row.equity)}</td>
                <td className={(row.daily_pnl ?? 0) > 0 ? 'is-good' : (row.daily_pnl ?? 0) < 0 ? 'is-bad' : ''}>{signed(row.daily_pnl)}</td>
                <td><Ratio used={row.daily_drawdown_pct} limit={row.daily_loss_pct} /></td>
                <td>
                  <div className="pf-target">
                    <div className="pf-bar"><i className={(row.progress_pct ?? 0) < 0 ? 'is-bad' : ''} style={{ width: `${Math.max(0, Math.min(100, Math.abs(row.progress_pct ?? 0)))}%` }} /></div>
                    <span>{row.progress_pct == null ? '—' : `${row.progress_pct.toFixed(1)}% / ${row.profit_target_pct ?? '—'}%`}</span>
                  </div>
                </td>
                <td><span className={`pf-status ${statusClass(row.status)}`}>{row.status}</span></td>
                <td className="pf-actions">
                  <button type="button" aria-label={`Actions for ${row.external_id}`} onClick={(event) => { event.stopPropagation(); setMenuId(menuId === row.id ? null : row.id); }}><Ellipsis size={16} /></button>
                  {menuId === row.id && (
                    <div className="pf-menu" role="menu">
                      <button type="button" onClick={() => onOpen(row.id, 'performance')}>Trading performance</button>
                      <button type="button" onClick={() => onOpen(row.id, 'risk')}>Risk & compliance</button>
                      <button type="button" onClick={() => onOpen(row.id, 'audit')}>Violations & audit</button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
            {!view.length && <tr><td colSpan={11} className="pf-empty">{empty}</td></tr>}
          </tbody>
        </table>
      </div>
      {sorted.length > pageSize && (
        <div className="pf-pages">
          <span>{page * pageSize + 1}–{Math.min(sorted.length, (page + 1) * pageSize)} of {sorted.length}</span>
          <button type="button" disabled={page === 0} onClick={() => setPage((current) => current - 1)}>Previous</button>
          <button type="button" disabled={page + 1 >= pages} onClick={() => setPage((current) => current + 1)}>Next</button>
        </div>
      )}
    </>
  );
}

function Ratio({ used, limit }: { used: number | null; limit: number | null }) {
  if (used == null) return <span className="pf-muted">—</span>;
  const hot = used < 0 || (limit != null && limit > 0 && used >= limit * 0.8);
  return <span className={hot ? 'is-bad' : 'is-good'}><b>{used.toFixed(1)}%</b> <span className="pf-muted">/ {limit ?? '—'}%</span></span>;
}

function ChallengeTable({ rows }: { rows: PropAccountRow[] }) {
  return (
    <div className="pf-table-wrap">
      <table className="pf-challenge">
        <thead>
          <tr><th>Account</th><th>Phase</th><th>Profit Target</th><th>Progress</th><th>Days Left</th><th>Status</th></tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td><b>{row.external_id}</b></td>
              <td>{row.phase || phaseWord(row.lifecycle)}</td>
              <td>{row.profit_target_pct == null ? '—' : `${row.profit_target_pct}%`}</td>
              <td>
                <div className="pf-bar"><i className={(row.progress_pct ?? 0) < 0 ? 'is-bad' : ''} style={{ width: `${Math.max(0, Math.min(100, Math.abs(row.progress_pct ?? 0)))}%` }} /></div>
              </td>
              <td>{row.days_left == null ? '—' : row.days_left}</td>
              <td><span className={`pf-status ${statusClass(row.status)}`}>{row.status}</span></td>
            </tr>
          ))}
          {!rows.length && <tr><td colSpan={6} className="pf-empty">Evaluation progress appears when an account is in a firm-confirmed phase.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function PerformanceChart({ points, range }: { points: SnapshotPoint[]; range: 7 | 30 | 90 }) {
  const [hover, setHover] = useState<number | null>(null);
  const cutoff = Date.now() - range * 86400000;
  const series = points.filter((point) => new Date(point.recorded_at).getTime() >= cutoff);
  const used = series.length >= 2 ? series : points;
  const width = 720;
  const height = 248;
  const pad = { l: 52, r: 12, t: 16, b: 28 };
  const values = used.flatMap((point) => [point.equity, point.balance]);
  const lo = values.length ? Math.min(...values) : 0;
  const hi = values.length ? Math.max(...values) : 1;
  const span = hi - lo || 1;
  const x = (index: number) => pad.l + (used.length < 2 ? 0.5 : index / (used.length - 1)) * (width - pad.l - pad.r);
  const y = (value: number) => pad.t + (1 - (value - lo) / span) * (height - pad.t - pad.b);
  const coords = (key: 'equity' | 'balance') => used.map((point, index) => [x(index), y(point[key])] as [number, number]);
  const ticks = [0, 1, 2, 3].map((step) => lo + (span * (3 - step)) / 3);
  const active = hover == null ? null : used[hover];
  const labelAt = (index: number) => new Date(used[index].recorded_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  const xLabels = used.length < 2 ? [] : [0, Math.floor((used.length - 1) / 2), used.length - 1];

  return (
    <div className="pf-chart-wrap">
      <svg viewBox={`0 0 ${width} ${height}`} className="pf-chart" role="img" aria-label="Account balance and equity"
        onMouseMove={(event) => {
          if (used.length < 2) return;
          const rect = event.currentTarget.getBoundingClientRect();
          const ratio = (event.clientX - rect.left) / rect.width;
          const plot = (ratio * width - pad.l) / (width - pad.l - pad.r);
          setHover(Math.max(0, Math.min(used.length - 1, Math.round(plot * (used.length - 1)))));
        }}
        onMouseLeave={() => setHover(null)}
      >
        {ticks.map((tick) => (
          <g key={tick}>
            <line className="grid" x1={pad.l} x2={width - pad.r} y1={y(tick)} y2={y(tick)} />
            <text x={pad.l - 8} y={y(tick) + 4} textAnchor="end">{axisMoney(tick)}</text>
          </g>
        ))}
        {used.length >= 2 && (
          <>
            <path className="fill-balance" d={`${smooth(coords('balance'))} L${x(used.length - 1)},${height - pad.b} L${x(0)},${height - pad.b} Z`} />
            <path className="fill-equity" d={`${smooth(coords('equity'))} L${x(used.length - 1)},${height - pad.b} L${x(0)},${height - pad.b} Z`} />
            <path className="is-balance" d={smooth(coords('balance'))} />
            <path className="is-equity" d={smooth(coords('equity'))} />
            {active && hover != null && (
              <>
                <line className="grid" x1={x(hover)} x2={x(hover)} y1={pad.t} y2={height - pad.b} />
                <circle className="is-balance dot" cx={x(hover)} cy={y(active.balance)} r="4" fill="#2f6fed" />
                <circle className="is-equity dot" cx={x(hover)} cy={y(active.equity)} r="4" fill="#12b76a" />
              </>
            )}
            {xLabels.map((index) => <text key={index} x={x(index)} y={height - 8} textAnchor="middle">{labelAt(index)}</text>)}
          </>
        )}
      </svg>
      {used.length < 2 && <div className="pf-chart-empty">Snapshot history appears here after the broker account is reconciled.</div>}
      {active && hover != null && (
        <div className="pf-tip" style={{ left: `${(x(hover) / width) * 100}%` }}>
          {new Date(active.recorded_at).toLocaleString()} · Balance {money(active.balance)} · Equity {money(active.equity)}
        </div>
      )}
    </div>
  );
}

const NO_POINTS: SnapshotPoint[] = [];

function useEquitySeries(focus: string, idsKey: string, stamp: number | null) {
  const [points, setPoints] = useState<SnapshotPoint[]>(NO_POINTS);
  useEffect(() => {
    const ids = idsKey ? idsKey.split(',') : [];
    const chosen = focus === 'all' ? ids : ids.filter((id) => id === focus);
    if (!chosen.length) {
      setPoints(NO_POINTS);
      return;
    }
    let cancel = false;
    void Promise.all(chosen.map((id) => propApi.performance(id).then((payload) => payload.snapshots).catch(() => []))).then((groups) => {
      if (cancel) return;
      if (focus !== 'all') {
        setPoints(groups[0] ?? []);
        return;
      }
      const buckets = new Map<string, SnapshotPoint>();
      for (const snaps of groups) {
        for (const snap of snaps) {
          const day = snap.recorded_at.slice(0, 10);
          const current = buckets.get(day) ?? { recorded_at: snap.recorded_at, balance: 0, equity: 0 };
          current.balance += snap.balance;
          current.equity += snap.equity;
          buckets.set(day, current);
        }
      }
      setPoints([...buckets.values()].sort((left, right) => left.recorded_at.localeCompare(right.recorded_at)));
    });
    return () => { cancel = true; };
  }, [focus, idsKey, stamp]);
  return points;
}

function Flow() {
  return (
    <div className="pf-flow">
      <article className="pf-node is-intel">
        <span className="pf-node-icon"><ChartColumn size={16} /></span>
        <b>Cacsms Market Intelligence</b>
        <span>29 instruments</span>
        <span>Multi-timeframe analysis</span>
      </article>
      <span className="pf-arrow" aria-hidden>→</span>
      <div className="pf-modes">
        <article>
          <Monitor size={16} color="#2f6fed" />
          <b>Mode 1 — Technical</b>
          <span>Trend-in-Trend</span>
          <span>Channel Continuation</span>
          <span>Breakout – Retest</span>
        </article>
        <article>
          <Brain size={16} color="#7a5af8" />
          <b>Mode 2 — AI Outlook</b>
          <span>AI market direction</span>
          <span>Opportunity scoring and forecasts</span>
        </article>
      </div>
      <span className="pf-arrow" aria-hidden>→</span>
      <article className="pf-node is-engine">
        <span className="pf-node-icon"><SlidersHorizontal size={16} /></span>
        <b>Unified Opportunity & Risk Engine</b>
        <span>Deduplication</span>
        <span>Position sizing</span>
        <span>Exposure checks</span>
      </article>
      <span className="pf-arrow" aria-hidden>→</span>
      <article className="pf-node is-gate">
        <span className="pf-node-icon"><ShieldCheck size={16} /></span>
        <b>Prop Firm Compliance Gate</b>
        <span>Daily loss limits</span>
        <span>Total loss / Drawdown</span>
        <span>News restrictions</span>
        <span>Account rules</span>
        <span>Trade validation</span>
      </article>
      <span className="pf-arrow" aria-hidden>→</span>
      <div className="pf-decisions">
        <article className="is-ok"><CircleCheck size={16} /><b>Approved</b><span>Execute trade</span></article>
        <article className="is-no"><CircleX size={16} /><b>Rejected</b><span>Block and log</span></article>
      </div>
    </div>
  );
}

function RiskOverview({ rules, account }: { rules: PropRules | null; account: PropAccountRow | null }) {
  const floatingUsed = account?.equity && account.daily_pnl != null && account.daily_pnl < 0
    ? Math.abs(100 * account.daily_pnl / account.equity)
    : 0;
  const rows: Array<{ icon: ReactNode; label: string; text: string; meter: number | null; check?: boolean }> = [
    { icon: <Gauge size={16} />, label: 'Daily Loss Limit', text: rules ? `${account?.daily_drawdown_pct?.toFixed(1) ?? '0.0'}% / ${rules.daily_loss_pct}%` : '—', meter: rules ? Math.min(100, (Math.abs(account?.daily_drawdown_pct ?? 0) / (rules.daily_loss_pct || 1)) * 100) : 0 },
    { icon: <TrendingDown size={16} />, label: 'Maximum Drawdown', text: rules ? `${account?.max_drawdown_pct?.toFixed(1) ?? '0.0'}% / ${rules.max_loss_pct}%` : '—', meter: rules ? Math.min(100, (Math.abs(account?.max_drawdown_pct ?? 0) / (rules.max_loss_pct || 1)) * 100) : 0 },
    { icon: <Activity size={16} />, label: 'Floating Loss (incl. comm & slippage)', text: rules ? `${floatingUsed.toFixed(1)}% / ${rules.floating_loss_pct ?? 0}%` : '—', meter: rules?.floating_loss_pct ? Math.min(100, (floatingUsed / rules.floating_loss_pct) * 100) : 0 },
    { icon: <Newspaper size={16} />, label: 'News Trading Restriction', text: rules && (rules.news_block_minutes ?? 0) > 0 ? `No trading (±${rules.news_block_minutes} min)` : rules ? 'Not configured' : '—', meter: null, check: !!rules && (rules.news_block_minutes ?? 0) > 0 },
    { icon: <CalendarOff size={16} />, label: 'Weekend Holding Restriction', text: rules ? (rules.weekend_holding ? 'Holding allowed' : 'No positions') : '—', meter: null, check: !!rules && !rules.weekend_holding },
    { icon: <Box size={16} />, label: 'Max Lot Size (per trade)', text: rules ? `${Number(rules.max_lot ?? 0).toFixed(2)} lots` : '—', meter: null, check: false },
    { icon: <Layers size={16} />, label: 'Max Open Positions', text: rules ? `${rules.max_positions ?? '—'} positions` : '—', meter: null, check: false },
  ];
  return (
    <ul className="pf-risk">
      {rows.map((row) => (
        <li key={row.label}>
          <span className="pf-risk-ico">{row.icon}</span>
          <div>
            <div className="pf-risk-line">
              <b>{row.label}</b>
              <em>{row.text}{row.check ? <span className="is-check"> <CircleCheck size={14} /></span> : null}</em>
            </div>
            {row.meter != null && <div className="pf-meter"><i style={{ width: `${row.meter}%` }} /></div>}
          </div>
        </li>
      ))}
    </ul>
  );
}

function PerformanceTab({ data, selectedId, setSelectedId }: { data: PropOverview | null; selectedId: string | null; setSelectedId: (id: string) => void }) {
  const [performance, setPerformance] = useState<Awaited<ReturnType<typeof propApi.performance>> | null>(null);
  const [range, setRange] = useState<7 | 30 | 90>(30);
  useEffect(() => {
    if (!selectedId) {
      setPerformance(null);
      return;
    }
    void propApi.performance(selectedId).then(setPerformance).catch(() => setPerformance(null));
  }, [selectedId]);
  return (
    <section className="pf-card">
      <div className="pf-card-head">
        <h2>Trading Performance</h2>
        <div className="pf-tools">
          <select className="pf-select" value={selectedId ?? ''} aria-label="Account" onChange={(event) => setSelectedId(event.target.value)}>
            {data?.accounts.map((row) => <option key={row.id} value={row.id}>{row.firm} · {row.external_id}</option>)}
          </select>
          <div className="pf-ranges">
            {([7, 30, 90] as const).map((days) => <button key={days} type="button" className={range === days ? 'is-on' : ''} onClick={() => setRange(days)}>{days}D</button>)}
          </div>
        </div>
      </div>
      <div className="pf-legend"><span><i className="is-balance" />Balance</span><span><i className="is-equity" />Equity</span></div>
      <PerformanceChart points={performance?.snapshots ?? []} range={range} />
      <div className="pf-stats">
        <div className="pf-stat"><span>Realized P&L</span><b>{signed(performance?.realized_pnl ?? null)}</b></div>
        <div className="pf-stat"><span>Win rate</span><b>{performance?.win_rate == null ? '—' : `${performance.win_rate}%`}</b></div>
        <div className="pf-stat"><span>Profit factor</span><b>{performance?.profit_factor ?? '—'}</b></div>
        <div className="pf-stat"><span>Reconciled deals</span><b>{performance?.deals.length ?? 0}</b></div>
      </div>
      <div className="pf-table-wrap">
        <table>
          <thead><tr><th>Closed</th><th>Symbol</th><th>Direction</th><th>Volume</th><th>Strategy</th><th>Profit</th></tr></thead>
          <tbody>
            {(performance?.deals ?? []).map((deal, index) => (
              <tr key={`${deal.closed_at}-${index}`}>
                <td>{new Date(deal.closed_at).toLocaleString()}</td>
                <td>{deal.symbol}</td>
                <td>{deal.direction}</td>
                <td>{deal.volume}</td>
                <td>{deal.strategy ?? '—'}</td>
                <td className={deal.profit >= 0 ? 'is-good' : 'is-bad'}>{signed(deal.profit)}</td>
              </tr>
            ))}
            {!performance?.deals.length && <tr><td colSpan={6} className="pf-empty">Win rate and profit factor use reconciled closed deals. None are stored for this account yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function AuditTab({ reloadKey }: { reloadKey: number }) {
  const [violations, setViolations] = useState<Awaited<ReturnType<typeof propApi.violations>> | null>(null);
  useEffect(() => {
    void propApi.violations().then(setViolations).catch(() => setViolations(null));
  }, [reloadKey]);
  const rows = [
    ...(violations?.violations ?? []).map((row) => ({ when: row.created_at, account: row.display_name, decision: row.protection, detail: row.reasons.join('; ') })),
    ...(violations?.events ?? []).map((row) => ({ when: row.created_at, account: row.account_id ?? 'Firm', decision: row.action, detail: JSON.stringify(row.detail) })),
  ];
  return (
    <section className="pf-card">
      <div className="pf-card-head"><h2>Violations & Audit</h2></div>
      <div className="pf-table-wrap">
        <table>
          <thead><tr><th>When</th><th>Account</th><th>Decision</th><th>Detail</th></tr></thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`${row.when}-${index}`}><td>{new Date(row.when).toLocaleString()}</td><td>{row.account}</td><td><span className="pf-status is-risk">{row.decision}</span></td><td>{row.detail}</td></tr>
            ))}
            {!rows.length && <tr><td colSpan={4} className="pf-empty">No compliance decisions have been recorded.</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function AccountFields(props: {
  data: PropOverview | null;
  firmId: string;
  setFirmId: (value: string) => void;
  firmName: string;
  setFirmName: (value: string) => void;
  accountName: string;
  setAccountName: (value: string) => void;
  broker: string;
  setBroker: (value: string) => void;
  login: string;
  setLogin: (value: string) => void;
  server: string;
  setServer: (value: string) => void;
  size: string;
  setSize: (value: string) => void;
  environment: string;
  setEnvironment: (value: string) => void;
  lifecycle: string;
  setLifecycle: (value: string) => void;
  automation: boolean;
  setAutomation: (value: boolean) => void;
  rules: PropRules;
  setRules: (rules: PropRules) => void;
}) {
  return (
    <>
      <label>Existing firm
        <select value={props.firmId} onChange={(event) => props.setFirmId(event.target.value)}>
          <option value="">Create a new firm</option>
          {props.data?.firms.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select>
      </label>
      {!props.firmId && <label>Firm name<input value={props.firmName} onChange={(event) => props.setFirmName(event.target.value)} /></label>}
      <label>Account name<input value={props.accountName} onChange={(event) => props.setAccountName(event.target.value)} /></label>
      <label>Broker
        <select value={props.broker} onChange={(event) => props.setBroker(event.target.value)}><option>MT5</option><option>CTRADER</option></select>
      </label>
      <label>Broker login<input value={props.login} onChange={(event) => props.setLogin(event.target.value)} /></label>
      <label>Server<input value={props.server} onChange={(event) => props.setServer(event.target.value)} /></label>
      <label>Account size<input value={props.size} onChange={(event) => props.setSize(event.target.value)} /></label>
      <label>Environment
        <select value={props.environment} onChange={(event) => props.setEnvironment(event.target.value)}><option>DEMO</option><option>LIVE</option></select>
      </label>
      <label>Starting lifecycle
        <select value={props.lifecycle} onChange={(event) => props.setLifecycle(event.target.value)}>
          <option>REGISTERED</option><option>CONNECTED</option><option>EVALUATION_PHASE_1</option><option>FUNDED</option>
        </select>
      </label>
      <label className="pf-check"><input type="checkbox" checked={props.automation} onChange={(event) => props.setAutomation(event.target.checked)} /> Firm has confirmed EA/API automated trading</label>
      {!props.firmId && <RuleFields rules={props.rules} onChange={props.setRules} />}
    </>
  );
}

function RuleFields({ rules, onChange }: { rules: PropRules; onChange: (rules: PropRules) => void }) {
  const set = (key: keyof PropRules, value: string | boolean) => onChange({ ...rules, [key]: value === '' || typeof value === 'boolean' ? value : Number(value) });
  return (
    <div className="pf-rules">
      <label>Daily loss %<input value={rules.daily_loss_pct} onChange={(event) => set('daily_loss_pct', event.target.value)} /></label>
      <label>Max loss %<input value={rules.max_loss_pct} onChange={(event) => set('max_loss_pct', event.target.value)} /></label>
      <label>Drawdown
        <select value={rules.drawdown_method} onChange={(event) => onChange({ ...rules, drawdown_method: event.target.value })}>
          <option>STATIC</option><option>TRAILING</option><option>EOD_TRAILING</option>
        </select>
      </label>
      <label>Daily reference
        <select value={rules.daily_reference} onChange={(event) => onChange({ ...rules, daily_reference: event.target.value })}>
          <option>BALANCE</option><option>EQUITY</option>
        </select>
      </label>
      <label>Reset timezone<input value={rules.reset_timezone} onChange={(event) => onChange({ ...rules, reset_timezone: event.target.value })} /></label>
      <label>Max positions<input value={rules.max_positions} onChange={(event) => set('max_positions', event.target.value)} /></label>
      <label>Max lot<input value={rules.max_lot} onChange={(event) => set('max_lot', event.target.value)} /></label>
      <label>Profit target %<input value={rules.profit_target_pct} onChange={(event) => set('profit_target_pct', event.target.value)} /></label>
      <label>News block minutes<input value={rules.news_block_minutes ?? 0} onChange={(event) => set('news_block_minutes', event.target.value)} /></label>
      <label className="pf-check"><input type="checkbox" checked={!!rules.automation_permitted} onChange={(event) => onChange({ ...rules, automation_permitted: event.target.checked })} /> Firm permits automated trading</label>
      <label className="pf-check"><input type="checkbox" checked={!!rules.weekend_holding} onChange={(event) => onChange({ ...rules, weekend_holding: event.target.checked })} /> Weekend holding allowed</label>
      <label className="pf-check"><input type="checkbox" checked={!!rules.emergency_close} onChange={(event) => onChange({ ...rules, emergency_close: event.target.checked })} /> Emergency close when a hard limit is reached</label>
    </div>
  );
}

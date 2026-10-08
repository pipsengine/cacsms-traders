import { useMemo, useState, type CSSProperties } from 'react';
import { ArrowDownRight, ArrowUpRight, History, RefreshCw, Search } from 'lucide-react';
import { OPP_STATE_TONE, TYPE_SHORT, pretty, price, utc } from '../format';
import type { OpportunitiesResponse, Opportunity, StageSummary } from '../types';
import { Sym } from './DetailParts';

type Tab = { id: string; label: string; match: (o: Opportunity) => boolean };

const TABS: Tab[] = [
  { id: 'all', label: 'All Opportunities', match: (o) => o.status === 'ACTIVE' },
  { id: 'p1', label: 'P1 Retracement', match: (o) => o.status === 'ACTIVE' && o.type === 'P1_RETRACEMENT' },
  { id: 'p2', label: 'P2 Breakout', match: (o) => o.status === 'ACTIVE' && o.type === 'P2_BREAKOUT_RETEST' },
  { id: 'cont', label: 'Continuation', match: (o) => o.status === 'ACTIVE' && o.type === 'CONTINUATION' },
  { id: 'tit', label: 'TiT', match: (o) => o.status === 'ACTIVE' && o.type === 'TIT' },
  { id: 'zone', label: 'Waiting for Zone', match: (o) => o.status === 'ACTIVE' && o.state === 'WAITING_FOR_ZONE' },
  { id: 'ready', label: 'Ready', match: (o) => o.status === 'ACTIVE' && o.state === 'EXECUTION_BLOCKED_ANALYSIS_ONLY' },
  { id: 'invalid', label: 'Invalidated', match: (o) => o.status === 'CLOSED' && o.state === 'INVALIDATED' },
  { id: 'closed', label: 'Closed', match: (o) => o.status === 'CLOSED' },
];

export function OpportunitiesTable({
  data,
  loading,
  error,
  stages,
  onHistory,
  onLog,
  onRefresh,
}: {
  data: OpportunitiesResponse | null;
  loading: boolean;
  error: string;
  stages: StageSummary[];
  onHistory: (o: Opportunity) => void;
  onLog: () => void;
  onRefresh: () => void;
}) {
  const [tab, setTab] = useState('all');
  const [symbol, setSymbol] = useState('');
  const [provider, setProvider] = useState('');
  const [stage, setStage] = useState('');
  const [direction, setDirection] = useState('');
  const [tf, setTf] = useState('');
  const [q, setQ] = useState('');
  const rows = data?.rows ?? [];
  const symbols = useMemo(() => [...new Set(rows.map((r) => r.symbol))].sort(), [rows]);
  const counts = useMemo(() => Object.fromEntries(TABS.map((t) => [t.id, rows.filter(t.match).length])), [rows]);
  const active = TABS.find((t) => t.id === tab) ?? TABS[0];
  const shown = rows.filter(
    (o) =>
      active.match(o) &&
      (!symbol || o.symbol === symbol) &&
      (!provider || o.provider === provider) &&
      (!stage || o.stage === stage) &&
      (!direction || o.direction === direction) &&
      (!tf || o.trigger_tf === tf || o.parent_tf === tf) &&
      (!q || `${o.symbol} ${o.type_label} ${o.state} ${o.next_condition ?? ''}`.toLowerCase().includes(q.toLowerCase())),
  );

  return (
    <section className="ae-card ae-opps" aria-label="Opportunities">
      <nav className="ae-tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t.id} type="button" role="tab" aria-selected={tab === t.id} className={tab === t.id ? 'is-on' : ''} onClick={() => setTab(t.id)}>
            {t.label} <span>({counts[t.id] ?? 0})</span>
          </button>
        ))}
      </nav>
      <div className="ae-opps-tools">
        <select value={symbol} onChange={(e) => setSymbol(e.target.value)} aria-label="Symbol">
          <option value="">All Symbols</option>
          {symbols.map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
        <select value={provider} onChange={(e) => setProvider(e.target.value)} aria-label="Provider">
          <option value="">All Providers</option>
          <option value="mt5">MT5</option>
          <option value="ctrader">cTrader</option>
        </select>
        <select value={stage} onChange={(e) => setStage(e.target.value)} aria-label="Stage">
          <option value="">All Stages</option>
          {stages.map((s) => (
            <option key={s.key} value={s.key}>
              {s.number}. {s.label}
            </option>
          ))}
        </select>
        <select value={tf} onChange={(e) => setTf(e.target.value)} aria-label="Timeframe">
          <option value="">All Timeframes</option>
          {['W', 'D1', 'H8', 'H1'].map((t) => (
            <option key={t}>{t}</option>
          ))}
        </select>
        <select value={direction} onChange={(e) => setDirection(e.target.value)} aria-label="Direction">
          <option value="">All Directions</option>
          <option value="BULLISH">Bullish</option>
          <option value="BEARISH">Bearish</option>
        </select>
        <label className="ae-search">
          <Search size={14} />
          <input type="search" placeholder="Search symbol, type, state…" value={q} onChange={(e) => setQ(e.target.value)} />
        </label>
        <button type="button" className="ae-icon-btn" onClick={onRefresh} title="Reload opportunities" aria-label="Reload opportunities">
          <RefreshCw size={14} />
        </button>
        <button type="button" className="ae-btn is-primary" onClick={onLog}>
          <History size={14} /> View History
        </button>
      </div>

      {error && !data ? (
        <div className="ae-banner is-bad">Opportunities unavailable: {error}</div>
      ) : loading && !data ? (
        <div className="ae-skeleton-rows" aria-busy="true">
          {Array.from({ length: 5 }, (_, i) => (
            <span key={i} className="ae-skel" />
          ))}
        </div>
      ) : !shown.length ? (
        <div className="ae-empty is-tall">
          {rows.length
            ? 'No opportunities match these filters.'
            : 'No opportunities yet. They are created autonomously when closed-bar evidence qualifies a P1, P2, continuation or TiT setup — waiting is a valid state.'}
        </div>
      ) : (
        <div className="ae-table-wrap">
          <table className="ae-table ae-opps-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Direction</th>
                <th>Opportunity Type</th>
                <th>TiT Level</th>
                <th>Current Stage</th>
                <th>Current State</th>
                <th>Parent → Trigger</th>
                <th>Entry Zone / Level</th>
                <th>Current Price</th>
                <th>Next Condition</th>
                <th>Confidence</th>
                <th>Updated At</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {shown.map((o) => (
                <tr key={o.id} onDoubleClick={() => onHistory(o)}>
                  <td>
                    <Sym symbol={o.symbol} />
                  </td>
                  <td>
                    <span className={`ae-dir ${o.direction === 'BULLISH' ? 'is-up' : 'is-down'}`}>
                      {o.direction === 'BULLISH' ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
                      {o.direction === 'BULLISH' ? 'Bullish' : 'Bearish'}
                    </span>
                  </td>
                  <td>{o.type === 'TIT' || o.type === 'CONTINUATION' ? <><span className="ae-type">{TYPE_SHORT[o.type]}</span> {o.type_label}</> : o.type_label}</td>
                  <td>{o.tit_level ? <span className="ae-tag is-purple">{o.tit_level}</span> : '—'}</td>
                  <td>
                    <span className="ae-stage-chip" style={{ '--stage': o.stage_color ?? '#64748b' } as CSSProperties}>
                      <b>{o.stage_number}</b> {o.stage_label}
                    </span>
                  </td>
                  <td>
                    <span className={`ae-tag is-${OPP_STATE_TONE[o.state] ?? 'muted'}`} title={o.reason_code ?? undefined}>
                      {o.outcome && o.status === 'CLOSED' ? `${o.state} · ${o.outcome}` : o.state}
                    </span>
                  </td>
                  <td>
                    {o.parent_tf ?? '—'} → {o.trigger_tf ?? '—'}
                  </td>
                  <td className="ae-num">
                    {o.entry_lo != null && o.entry_hi != null && o.entry_lo !== o.entry_hi
                      ? `${price(o.entry_lo, o.digits)} – ${price(o.entry_hi, o.digits)}`
                      : price(o.entry_lo ?? o.entry_hi, o.digits)}
                  </td>
                  <td className="ae-num" title={o.price_at ? `Closed bar ${utc(o.price_at, true)} UTC` : undefined}>
                    {price(o.current_price, o.digits)}
                  </td>
                  <td className="ae-clip" title={o.blockers.join('\n') || undefined}>
                    {o.next_condition ?? '—'}
                  </td>
                  <td>
                    {o.confidence != null ? (
                      <span className={`ae-conf ${o.confidence >= 70 ? 'is-ok' : o.confidence >= 55 ? 'is-warn' : 'is-low'}`}>
                        <i style={{ width: `${Math.min(100, o.confidence)}%` }} />
                        {o.confidence.toFixed(1)}%
                      </span>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td>{utc(o.updated_at, true)}</td>
                  <td>
                    <button type="button" className="ae-icon-btn" onClick={() => onHistory(o)} title="View history" aria-label={`View history for ${o.symbol}`}>
                      <History size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <footer className="ae-opps-foot">
        Showing {shown.length} of {rows.length} · opportunities are created and advanced only by the backend engine
      </footer>
    </section>
  );
}

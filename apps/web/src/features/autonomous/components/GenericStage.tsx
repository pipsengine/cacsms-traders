import type { ReactNode } from 'react';
import {
  Activity,
  AlertTriangle,
  Ban,
  Briefcase,
  CircleCheck,
  CircleX,
  Clock,
  Database,
  Gauge,
  Hourglass,
  Layers,
  Percent,
  Server,
  ShieldCheck,
  Target,
  TrendingDown,
  TrendingUp,
} from 'lucide-react';
import { OPP_STATE_TONE, TYPE_SHORT, list, num, pretty, price, rec, str, tone, utc } from '../format';
import type { Opportunity, StageDetail, Transition } from '../types';
import { Blockers, CurrentOperation, DetectionsTable, Donut, Empty, KpiRow, Panel, Sym, type Kpi } from './DetailParts';

const digitsFor = (s: string) => (s.startsWith('XAU') ? 2 : s.endsWith('JPY') ? 3 : 5);
const v = (n: number | null, suffix = '') => (n == null ? '—' : `${n}${suffix}`);

function kpisFor(d: StageDetail): Kpi[] {
  const m = d.metrics;
  const c = d.color;
  switch (d.key) {
    case 'MARKET_DATA': {
      const f = rec(m, 'freshness');
      return [
        { label: 'Instruments Ready', value: `${d.processed} / ${d.active}`, sub: str(m, 'provider_label') ?? undefined, icon: <Database size={18} />, color: c },
        { label: 'Fresh', value: f.FRESH ?? 0, sub: 'closed H1 bars current', icon: <CircleCheck size={18} />, color: '#16a34a' },
        { label: 'Aging', value: f.AGING ?? 0, icon: <Hourglass size={18} />, color: '#d97706' },
        { label: 'Stale', value: f.STALE ?? 0, icon: <AlertTriangle size={18} />, color: '#dc2626' },
        { label: 'Market Closed', value: f.MARKET_CLOSED ?? 0, icon: <Clock size={18} />, color: '#64748b' },
        { label: 'Excluded', value: d.errors, sub: 'no valid history', icon: <CircleX size={18} />, color: '#dc2626' },
        { label: 'Data As Of', value: utc(str(m, 'data_as_of'), true), sub: m.connected ? 'Provider connected' : 'Provider disconnected', icon: <Server size={18} />, color: c },
      ];
    }
    case 'INTELLIGENCE':
      return [
        { label: 'Pairs Loaded', value: `${d.processed} / 28`, icon: <Database size={18} />, color: c },
        { label: 'Currencies Ranked', value: d.active, icon: <Layers size={18} />, color: c },
        { label: 'Strongest', value: str(m, 'strongest') ?? '—', icon: <TrendingUp size={18} />, color: '#16a34a' },
        { label: 'Weakest', value: str(m, 'weakest') ?? '—', icon: <TrendingDown size={18} />, color: '#dc2626' },
        { label: 'Live Data', value: m.live ? 'Yes' : 'No', sub: pretty(str(m, 'engine_state')), icon: <Activity size={18} />, color: m.live ? '#16a34a' : '#d97706' },
        { label: 'Missing History', value: d.errors, icon: <AlertTriangle size={18} />, color: '#dc2626' },
      ];
    case 'SCANNER': {
      const k = rec(m, 'counts');
      return [
        { label: 'High Inspection', value: k.HIGH_INSPECTION ?? 0, icon: <Target size={18} />, color: '#dc2626' },
        { label: 'Watching', value: k.WATCHING ?? 0, icon: <Activity size={18} />, color: '#d97706' },
        { label: 'Neutral', value: k.NEUTRAL ?? 0, icon: <Layers size={18} />, color: '#64748b' },
        { label: 'Excluded', value: k.EXCLUDED ?? 0, icon: <CircleX size={18} />, color: '#94a3b8' },
        { label: 'Cycle', value: utc(str(m, 'cycle_at'), true), sub: str(m, 'cycle_id')?.slice(0, 12), icon: <Clock size={18} />, color: c },
      ];
    }
    case 'STRUCTURE':
      return [
        { label: 'Trending', value: num(m, 'trending') ?? 0, icon: <TrendingUp size={18} />, color: c },
        { label: 'Continuation Pullbacks', value: num(m, 'continuation') ?? 0, icon: <Target size={18} />, color: '#16a34a' },
        { label: 'Reversal Risk', value: num(m, 'reversal_risk') ?? 0, icon: <AlertTriangle size={18} />, color: '#dc2626' },
        { label: 'BOS (24h)', value: num(m, 'bos_24h') ?? 0, icon: <Activity size={18} />, color: '#2563eb' },
        { label: 'CHoCH (24h)', value: num(m, 'choch_24h') ?? 0, icon: <Activity size={18} />, color: '#d97706' },
      ];
    case 'OPPORTUNITY': {
      const t = rec(m, 'by_type');
      return [
        { label: 'Waiting for Zone', value: d.active, icon: <Hourglass size={18} />, color: c },
        { label: 'Created Today', value: num(m, 'created_today') ?? 0, sub: `${num(m, 'created_this_cycle') ?? 0} this cycle`, icon: <Target size={18} />, color: '#16a34a' },
        { label: 'Candidates Evaluated', value: d.processed, sub: 'last cycle', icon: <Layers size={18} />, color: '#2563eb' },
        ...Object.keys(TYPE_SHORT).map((k) => ({ label: `${TYPE_SHORT[k]} waiting`, value: t[k] ?? 0, icon: <Activity size={18} />, color: '#64748b' })),
      ];
    }
    case 'CONFIRMATION':
      return [
        { label: 'Awaiting Reaction', value: d.waiting, icon: <Hourglass size={18} />, color: c },
        { label: 'Awaiting Confirmation', value: d.active, sub: 'reaction confirmed', icon: <Activity size={18} />, color: '#2563eb' },
        { label: 'Confirmed Today', value: num(m, 'confirmed_today') ?? 0, icon: <CircleCheck size={18} />, color: '#16a34a' },
        { label: 'Expired Today', value: num(m, 'expired_today') ?? 0, icon: <Clock size={18} />, color: '#64748b' },
        { label: 'Invalidated Today', value: num(m, 'invalidated_today') ?? 0, icon: <CircleX size={18} />, color: '#dc2626' },
      ];
    case 'RISK':
      return [
        { label: 'Authorised Today', value: num(m, 'authorised_today') ?? 0, icon: <ShieldCheck size={18} />, color: '#16a34a' },
        { label: 'Deferred', value: num(m, 'deferred') ?? 0, sub: 'portfolio limits', icon: <Hourglass size={18} />, color: '#d97706' },
        { label: 'Rejected Today', value: num(m, 'rejected_today') ?? 0, icon: <CircleX size={18} />, color: c },
        { label: 'Shadow Plans', value: d.active, sub: `max ${v(num(m, 'max_concurrent'))} concurrent`, icon: <Briefcase size={18} />, color: '#475569' },
        { label: 'Min Reward : Risk', value: v(num(m, 'min_reward_risk')), sub: `max ${v(num(m, 'max_currency_exposure'))} per currency`, icon: <Gauge size={18} />, color: '#2563eb' },
      ];
    case 'EXECUTION':
      return [
        { label: 'Broker Orders Submitted', value: num(m, 'orders_submitted') ?? 0, sub: 'execution disabled', icon: <Ban size={18} />, color: c },
        { label: 'Blocked Today', value: num(m, 'blocked_today') ?? 0, sub: 'EXECUTION_BLOCKED_ANALYSIS_ONLY', icon: <ShieldCheck size={18} />, color: '#dc2626' },
        { label: 'Shadow Plans', value: num(m, 'shadow_plans') ?? 0, sub: 'tracked for outcome', icon: <Briefcase size={18} />, color: '#475569' },
        { label: 'Operating Mode', value: (str(m, 'operating_mode') ?? '—').replaceAll('_', ' '), icon: <Gauge size={18} />, color: '#2563eb' },
      ];
    case 'MANAGEMENT':
      return [
        { label: 'Open Positions', value: num(m, 'open_positions') ?? 0, icon: <Briefcase size={18} />, color: c },
        { label: 'Broker Orders', value: num(m, 'broker_orders') ?? 0, icon: <Ban size={18} />, color: '#475569' },
        { label: 'Shadow Plans Tracked', value: num(m, 'shadow_plans_tracked') ?? 0, icon: <Activity size={18} />, color: '#2563eb' },
      ];
    case 'LEARNING': {
      const o = rec(m, 'outcomes');
      return [
        { label: 'Closed (30 days)', value: num(m, 'closed_30d') ?? 0, icon: <Layers size={18} />, color: c },
        { label: 'Shadow Hit Rate', value: v(num(m, 'hit_rate'), '%'), sub: 'target 1 before stop', icon: <Percent size={18} />, color: '#16a34a' },
        { label: 'Average R', value: v(num(m, 'avg_r')), icon: <Gauge size={18} />, color: '#2563eb' },
        { label: 'Target 1', value: o.TARGET_1 ?? 0, icon: <CircleCheck size={18} />, color: '#16a34a' },
        { label: 'Stopped', value: o.STOPPED ?? 0, icon: <CircleX size={18} />, color: '#dc2626' },
        { label: 'Invalidated / Expired', value: (o.INVALIDATED ?? 0) + (o.EXPIRED ?? 0), icon: <Clock size={18} />, color: '#64748b' },
      ];
    }
    default:
      return [];
  }
}

function OppMini({ rows, empty }: { rows: Opportunity[]; empty: string }) {
  if (!rows.length) return <Empty>{empty}</Empty>;
  return (
    <div className="ae-table-wrap">
      <table className="ae-table">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Type</th>
            <th>State</th>
            <th>Entry Zone</th>
            <th>Next Condition</th>
            <th>Conf.</th>
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 10).map((o) => (
            <tr key={o.id}>
              <td>
                <Sym symbol={o.symbol} />
              </td>
              <td>
                <span className={o.direction === 'BULLISH' ? 'is-up' : 'is-down'}>{o.direction === 'BULLISH' ? '▲' : '▼'}</span> {TYPE_SHORT[o.type] ?? o.type}
              </td>
              <td>
                <span className={`ae-badge is-${OPP_STATE_TONE[o.state] ?? 'muted'}`}>{pretty(o.outcome ?? o.state)}</span>
              </td>
              <td className="ae-num">
                {price(o.entry_lo, o.digits)} – {price(o.entry_hi, o.digits)}
              </td>
              <td className="ae-clip">{o.next_condition ?? '—'}</td>
              <td className="ae-num">{o.confidence != null ? `${Math.round(o.confidence)}%` : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

type Row = Record<string, unknown>;

function SimpleTable({ cols, rows, empty }: { cols: [string, (r: Row) => ReactNode][]; rows: Row[]; empty: string }) {
  if (!rows.length) return <Empty>{empty}</Empty>;
  return (
    <div className="ae-table-wrap">
      <table className="ae-table">
        <thead>
          <tr>
            {cols.map(([h]) => (
              <th key={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {cols.map(([h, f]) => (
                <td key={h}>{f(r)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const symCell = (r: Row) => (typeof r.symbol === 'string' ? <Sym symbol={r.symbol} /> : '—');

/** The stage-specific list: what this stage is working through right now. */
function workList(d: StageDetail): { title: string; body: ReactNode } {
  const det = d.detail;
  switch (d.key) {
    case 'MARKET_DATA':
      return {
        title: 'Instrument Feed',
        body: (
          <SimpleTable
            rows={list<Row>(det, 'instruments')}
            empty="No instruments synchronised yet."
            cols={[
              ['Symbol', symCell],
              ['Last Closed Bar', (r) => (r.excluded ? '—' : utc(r.last_close_at as string, true))],
              ['Close', (r) => (typeof r.close === 'number' ? price(r.close, digitsFor(String(r.symbol))) : '—')],
              ['Freshness', (r) => <span className={`ae-badge is-${r.excluded ? 'bad' : tone(r.freshness === 'FRESH' ? 'RUNNING' : String(r.freshness))}`}>{r.excluded ? 'Excluded' : pretty(String(r.freshness))}</span>],
            ]}
          />
        ),
      };
    case 'INTELLIGENCE': {
      const cur = list<{ currency: string; score: number }>(det, 'currencies');
      const max = Math.max(1, ...cur.map((c) => Math.abs(c.score)));
      return {
        title: 'Currency Strength (closed bars)',
        body: cur.length ? (
          <ul className="ae-bars">
            {cur.map((c) => (
              <li key={c.currency}>
                <span>{c.currency}</span>
                <i className={c.score >= 0 ? 'is-up' : 'is-down'} style={{ width: `${(Math.abs(c.score) / max) * 100}%` }} />
                <b>{c.score.toFixed(1)}</b>
              </li>
            ))}
          </ul>
        ) : (
          <Empty>Awaiting the first strength calculation.</Empty>
        ),
      };
    }
    case 'SCANNER':
      return {
        title: 'Top Ranked Instruments',
        body: (
          <SimpleTable
            rows={list<Row>(det, 'top')}
            empty="Awaiting the first scanner cycle."
            cols={[
              ['Symbol', symCell],
              ['Status', (r) => <span className="ae-badge is-info">{pretty(String(r.status))}</span>],
              ['Score', (r) => (typeof r.score === 'number' ? r.score.toFixed(1) : '—')],
              ['Structure', (r) => pretty(r.structure as string)],
              ['Reason', (r) => <span className="ae-clip">{(r.reason as string) ?? '—'}</span>],
            ]}
          />
        ),
      };
    case 'STRUCTURE':
      return {
        title: 'Trend Structure',
        body: (
          <SimpleTable
            rows={list<Row>(det, 'symbols').slice(0, 14)}
            empty="Awaiting closed-bar structure analysis."
            cols={[
              ['Symbol', symCell],
              ['Direction', (r) => <span className={r.direction === 'BULLISH' ? 'is-up' : r.direction === 'BEARISH' ? 'is-down' : ''}>{pretty(r.direction as string)}</span>],
              ['State', (r) => pretty(r.state as string)],
              ['Setup', (r) => pretty(r.setup as string)],
              ['Confidence', (r) => (typeof r.confidence === 'number' ? `${Math.round(r.confidence)}%` : '—')],
            ]}
          />
        ),
      };
    case 'RISK': {
      const exp = rec(d.metrics, 'exposure');
      return {
        title: 'Currency Exposure (shadow plans)',
        body: Object.keys(exp).length ? (
          <ul className="ae-bars">
            {Object.entries(exp).map(([k, n]) => (
              <li key={k}>
                <span>{k}</span>
                <i className={n >= 0 ? 'is-up' : 'is-down'} style={{ width: `${(Math.abs(n) / Math.max(1, num(d.metrics, 'max_currency_exposure') ?? 2)) * 100}%` }} />
                <b>{n > 0 ? `+${n}` : n}</b>
              </li>
            ))}
          </ul>
        ) : (
          <Empty>No net currency exposure from authorised plans.</Empty>
        ),
      };
    }
    case 'LEARNING': {
      const t = rec(d.metrics, 'by_type') as unknown as Record<string, { closed: number; target_1: number; stopped: number }>;
      return {
        title: 'Outcomes by Opportunity Type (30 days)',
        body: (
          <SimpleTable
            rows={Object.entries(t).map(([k, x]) => ({ type: k, ...x }))}
            empty="No closed opportunity outcomes yet."
            cols={[
              ['Type', (r) => TYPE_SHORT[r.type as string] ?? String(r.type)],
              ['Closed', (r) => String(r.closed)],
              ['Target 1', (r) => String(r.target_1)],
              ['Stopped', (r) => String(r.stopped)],
            ]}
          />
        ),
      };
    }
    default:
      return { title: 'Opportunities at this Stage', body: null };
  }
}

function structureEvents(d: StageDetail): Transition[] {
  return list<Row>(d.detail, 'events').map((e, i) => ({
    id: `${e.symbol}-${e.tf}-${e.at}-${i}`,
    entity_type: 'STRUCTURE',
    entity_id: String(e.symbol),
    symbol: e.symbol as string,
    timeframe: e.tf as string,
    from_stage: null,
    from_state: null,
    to_stage: null,
    to_state: `${e.kind}_${e.direction}${e.failed ? '_FAILED' : ''}`,
    reason_code: String(e.kind),
    detail: null,
    provider: null,
    evidence_at: String(e.at),
    cycle_id: null,
    created_at: String(e.at),
    evidence: { level: e.level },
  }));
}

export function GenericStage({ d, warnings }: { d: StageDetail; warnings: string[] }) {
  const opps = d.opportunities;
  const work = workList(d);
  const detections = d.key === 'STRUCTURE' ? structureEvents(d) : d.detections;
  const total = d.processed + d.active + d.waiting + d.errors;
  return (
    <>
      <KpiRow items={kpisFor(d)} />
      <div className="ae-grid ae-grid-3">
        <Panel title="Stage Status">
          <Donut
            total={d.active}
            label="Active"
            color={d.color}
            rows={[
              { label: 'Processed', value: d.processed, color: d.color },
              { label: 'Active', value: d.active, color: '#16a34a' },
              { label: 'Waiting', value: d.waiting, color: '#f59e0b' },
              { label: 'Errors', value: d.errors, color: '#dc2626' },
            ]}
          />
          {!total ? <p className="ae-muted ae-small">Nothing processed yet in this stage.</p> : null}
        </Panel>
        <CurrentOperation
          title={d.label}
          badge={d.status}
          operation={d.current_operation}
          startedAt={d.last_update}
          nextStep={d.next_operation}
          live={d.status === 'RUNNING'}
          color={d.color}
        />
        <Panel title="Problems & Blockers">
          <Blockers blockers={d.blockers} warnings={d.key === 'MARKET_DATA' || d.key === 'EXECUTION' ? warnings : undefined} />
        </Panel>
      </div>
      <div className={`ae-grid ${opps && work.body ? 'ae-grid-3' : 'ae-grid-2'}`}>
        {opps ? (
          <Panel title={`${d.key === 'LEARNING' ? 'Closed Opportunities' : 'Opportunities at this Stage'} (${opps.length})`}>
            <OppMini rows={opps} empty={d.key === 'LEARNING' ? 'No closed opportunities yet.' : 'No opportunity is at this stage right now — WAITING is a valid state.'} />
          </Panel>
        ) : null}
        {work.body ? <Panel title={work.title}>{work.body}</Panel> : null}
        {!opps && !work.body ? (
          <Panel title="Positions">
            <Empty>No broker positions exist — execution is disabled while the operating mode is ANALYSIS ONLY.</Empty>
          </Panel>
        ) : null}
        <Panel title="Recent Detections">
          <DetectionsTable
            rows={detections.slice(0, 10)}
            digitsFor={digitsFor}
            empty={opps ? 'No transitions into this stage in the last 48 hours.' : 'This stage does not emit discrete detections; see the stage list.'}
          />
        </Panel>
      </div>
    </>
  );
}

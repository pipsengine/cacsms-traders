import { useCallback, useEffect, useMemo, useState } from 'react';
import { Activity, CircleX, GitBranch, Layers, Mail, RefreshCw, Repeat, Star, Target, Zap } from 'lucide-react';
import { StructureChart, type ChartOverlay } from '../../market-structure/components/StructureChart';
import { usePollingAsync } from '../../market-intelligence/hooks/useMarketIntelligence';
import { autonomousApi } from '../api';
import { ALERT_LABEL, CHANNEL_STATE_TONE, list, num, pretty, price, rec, tone, until, utc } from '../format';
import type { Channel, ChannelQueueItem, StageDetail, Transition } from '../types';
import { CurrentOperation, DetectionsTable, Donut, Empty, KpiRow, Panel, Sym, useNow, type Kpi } from './DetailParts';

const TFS = ['W', 'D1', 'H8', 'H1'] as const;
const LIFECYCLE_COLORS: Record<string, string> = {
  FORMING: '#94a3b8',
  ACTIVE: '#16a34a',
  MATURE: '#0d9488',
  TOUCHED: '#2563eb',
  BREAKING: '#f59e0b',
  BROKEN: '#ea580c',
  RETESTING: '#7c3aed',
  CONTINUING: '#059669',
};

function chartOverlay(c: Channel, events: Transition[]): ChartOverlay {
  const overlay: ChartOverlay = { lines: [], bands: [], markers: [], levels: [] };
  if (c.erz_band && c.erz_band.upper.length >= 2) {
    overlay.bands!.push({
      upper: [c.erz_band.upper[0], c.erz_band.upper[1]],
      lower: [c.erz_band.lower[0], c.erz_band.lower[1]],
      tone: c.direction === 'DESCENDING' ? 'red' : 'green',
    });
  }
  if (c.lines) {
    overlay.lines!.push(
      { from: c.lines.upper[0], to: c.lines.upper[1], tone: 'res', width: 1.6 },
      { from: c.lines.lower[0], to: c.lines.lower[1], tone: 'sup', width: 1.6 },
      { from: c.lines.mid[0], to: c.lines.mid[1], tone: 'mid', dashed: true },
    );
  }
  if (c.break_level != null && c.break_at) overlay.levels!.push({ price: c.break_level, tone: 'amber', label: 'Break level', from: c.break_at });
  for (const e of events) {
    const level = e.evidence?.level;
    if (typeof level !== 'number') continue;
    const side = e.evidence?.side;
    if (e.to_state === 'TOUCHED')
      overlay.markers!.push({ at: e.evidence_at, price: level, shape: side === 'UPPER' ? 'down' : 'up', tone: 'blue', below: side !== 'UPPER' });
    else if (e.to_state === 'BREAKING' || e.to_state === 'BROKEN')
      overlay.markers!.push({ at: e.evidence_at, price: level, shape: 'diamond', tone: 'amber', label: e.to_state === 'BROKEN' ? 'Break' : undefined });
    else if (e.to_state === 'RETESTING') overlay.markers!.push({ at: e.evidence_at, price: level, shape: 'dot', tone: 'blue', label: 'Retest' });
    else if (e.to_state === 'CONTINUING') overlay.markers!.push({ at: e.evidence_at, price: level, shape: 'dot', tone: 'green', label: 'Cont.' });
  }
  return overlay;
}

function ChannelDetection({ channels, symbol, onSymbol }: { channels: Channel[]; symbol: string | null; onSymbol: (s: string) => void }) {
  const forSymbol = channels.filter((c) => c.symbol === symbol);
  const [tf, setTf] = useState<string | null>(null);
  const available = new Set(forSymbol.map((c) => c.timeframe));
  const picked = forSymbol.find((c) => c.timeframe === tf) ?? forSymbol.find((c) => c.timeframe === 'H1') ?? forSymbol[0] ?? null;
  useEffect(() => setTf(null), [symbol]);

  const loader = useCallback(() => (picked ? autonomousApi.channelChart(picked.id, 140) : Promise.resolve(null)), [picked?.id]);
  const chart = usePollingAsync(loader, [loader], { enabled: !!picked, intervalMs: 30000 });
  const c = chart.data?.channel ?? picked;
  const overlay = useMemo(() => (c && chart.data ? chartOverlay(c, chart.data.events) : null), [c, chart.data]);
  const symbols = [...new Set(channels.map((x) => x.symbol))].sort();

  return (
    <Panel
      className="ae-chart-card"
      title={
        <>
          Channel Detection
          {symbols.length ? (
            <select className="ae-inline-select" value={symbol ?? ''} onChange={(e) => onSymbol(e.target.value)} aria-label="Chart instrument">
              {symbols.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          ) : null}
        </>
      }
      extra={
        <div className="ae-seg" role="tablist" aria-label="Channel timeframe">
          {TFS.map((t) => (
            <button
              type="button"
              key={t}
              disabled={!available.has(t)}
              className={picked?.timeframe === t ? 'is-on' : ''}
              onClick={() => setTf(t)}
              aria-selected={picked?.timeframe === t}
            >
              {t}
            </button>
          ))}
        </div>
      }
    >
      {!c ? (
        <Empty>No active channel lineage for this instrument. Channels appear once closed-bar geometry qualifies.</Empty>
      ) : (
        <div className="ae-chart-body">
          <StructureChart
            symbol={c.symbol}
            title={`${c.timeframe} channel`}
            tf={c.timeframe}
            candles={chart.data?.candles ?? []}
            digits={c.digits}
            lastPrice={chart.data?.candles.at(-1)?.c}
            height={250}
            loading={chart.loading}
            error={chart.error}
            overlay={overlay}
            showVolume={false}
            compact
            heading={<span />}
            actions={<span />}
            className="ae-structure-chart"
            legend={[
              { label: 'Upper', swatch: 'is-bear-line' },
              { label: 'Lower', swatch: 'is-bull-line' },
              { label: 'Midline', swatch: 'is-ae-mid' },
              { label: 'ERZ', swatch: c.direction === 'DESCENDING' ? 'is-ae-erz-red' : 'is-ae-erz-green' },
            ]}
          />
          <dl className="ae-chart-stats">
            <div>
              <dt>Direction</dt>
              <dd className={c.direction === 'ASCENDING' ? 'is-up' : c.direction === 'DESCENDING' ? 'is-down' : ''}>{pretty(c.direction)}</dd>
            </div>
            <div>
              <dt>State</dt>
              <dd>
                <span className={`ae-badge is-${CHANNEL_STATE_TONE[c.state] ?? 'muted'}`}>{pretty(c.state)}</span>
              </dd>
            </div>
            <div>
              <dt>Upper</dt>
              <dd>{price(c.upper, c.digits)}</dd>
            </div>
            <div>
              <dt>Lower</dt>
              <dd>{price(c.lower, c.digits)}</dd>
            </div>
            <div>
              <dt>Width</dt>
              <dd>
                {price(c.width, c.digits)}
                {c.width_atr != null ? <small> ({c.width_atr.toFixed(1)} ATR)</small> : null}
              </dd>
            </div>
            <div>
              <dt>ERZ</dt>
              <dd>{c.erz_lo != null ? `${price(c.erz_lo, c.digits)} – ${price(c.erz_hi, c.digits)}` : '—'}</dd>
            </div>
            <div>
              <dt>Touches</dt>
              <dd>
                {(c.touches_upper ?? 0) + (c.touches_lower ?? 0)} <small>({c.touches_upper ?? 0}U / {c.touches_lower ?? 0}L)</small>
              </dd>
            </div>
            <div>
              <dt>Age</dt>
              <dd>{c.age_bars != null ? `${c.age_bars} bars` : '—'}</dd>
            </div>
            <div>
              <dt>Validity</dt>
              <dd>{pretty(c.validity)}</dd>
            </div>
            <div>
              <dt>Quality</dt>
              <dd className="is-strong">{c.quality != null ? `${Math.round(c.quality)}%` : '—'}</dd>
            </div>
          </dl>
        </div>
      )}
    </Panel>
  );
}

export function ChannelStage({ d, onRefresh }: { d: StageDetail; onRefresh: () => void }) {
  const m = d.metrics;
  const now = useNow(5000);
  const channels = d.channels ?? [];
  const current = (d.detail.current ?? null) as {
    symbol: string;
    timeframe: string;
    state: string;
    task: string;
    started_at: string | null;
    next_step: string | null;
    progress: number;
  } | null;
  const queue = list<ChannelQueueItem>(d.detail, 'queue');
  const byState = rec(m, 'by_state');
  const [chartSymbol, setChartSymbol] = useState<string | null>(null);
  const defaultSymbol = d.filters.symbol ?? current?.symbol ?? channels[0]?.symbol ?? null;
  const symbol = chartSymbol && channels.some((c) => c.symbol === chartSymbol) ? chartSymbol : defaultSymbol;
  const digitsFor = (s: string) => (s.startsWith('XAU') ? 2 : s.endsWith('JPY') ? 3 : 5);
  const alerts = d.alerts?.items ?? [];
  const alertToday = d.alerts?.today ?? {};

  const kpis: Kpi[] = [
    { label: 'Active Channels', value: num(m, 'active_channels') ?? 0, sub: `${num(m, 'markets') ?? 0} markets`, icon: <Layers size={18} />, color: '#16a34a' },
    { label: 'Channel Touches', value: num(m, 'touches_today') ?? 0, sub: 'today', icon: <Target size={18} />, color: '#2563eb' },
    {
      label: 'Channel Breaks',
      value: num(m, 'breaks_today') ?? 0,
      sub: `${num(m, 'breaking_today') ?? 0} breaking today`,
      icon: <Zap size={18} />,
      color: '#ea580c',
    },
    { label: 'Retests', value: num(m, 'retests_today') ?? 0, sub: `${num(m, 'continuations_today') ?? 0} continuations today`, icon: <Repeat size={18} />, color: '#0d9488' },
    { label: 'TiT Detected', value: num(m, 'tit_active') ?? 0, sub: 'active / monitoring', icon: <GitBranch size={18} />, color: '#7c3aed' },
    {
      label: 'Average Channel Quality',
      value: num(m, 'avg_quality') != null ? `${Math.round(num(m, 'avg_quality')!)}%` : '—',
      sub: 'active lineages',
      icon: <Star size={18} />,
      color: '#d97706',
    },
    { label: 'Invalidated Channels', value: num(m, 'invalidated_today') ?? 0, sub: 'today (incl. expired)', icon: <CircleX size={18} />, color: '#dc2626' },
  ];

  return (
    <>
      <KpiRow items={kpis} />
      <div className="ae-grid ae-grid-3">
        <Panel title="Stage Status">
          <Donut
            total={num(m, 'active_channels') ?? 0}
            label="Active Channels"
            color={d.color}
            rows={Object.keys(LIFECYCLE_COLORS).map((s) => ({ label: pretty(s), value: byState[s] ?? 0, color: LIFECYCLE_COLORS[s] }))}
          />
          <div className="ae-mini-stats">
            <span>
              Touches today <b>{num(m, 'touches_today') ?? 0}</b>
            </span>
            <span>
              Breaks today <b>{num(m, 'breaks_today') ?? 0}</b>
            </span>
            <span>
              Retests today <b>{num(m, 'retests_today') ?? 0}</b>
            </span>
            <span>
              Invalidated <b>{num(m, 'invalidated_today') ?? 0}</b>
            </span>
          </div>
        </Panel>
        <CurrentOperation
          title={current ? current.timeframe : 'Channel Intelligence'}
          symbol={current?.symbol}
          badge={current ? `CHANNEL_${current.state}` : null}
          operation={d.current_operation}
          progress={current?.progress ?? null}
          startedAt={current?.started_at ?? d.last_update}
          nextStep={current?.next_step ?? d.next_operation}
          live={d.status === 'RUNNING'}
          color={d.color}
        />
        <ChannelDetection channels={channels} symbol={symbol} onSymbol={setChartSymbol} />
      </div>

      <section className="ae-lifecycle" aria-label="Channel lifecycle">
        {(d.lifecycle_states ?? []).map((s, i, all) => {
          const terminal = s === 'INVALIDATED' || s === 'EXPIRED';
          return (
            <span key={s} className={`ae-life is-${CHANNEL_STATE_TONE[s] ?? 'muted'}`}>
              {pretty(s)}
              {!terminal ? <b>{byState[s] ?? 0}</b> : null}
              {i < all.length - 1 ? <i aria-hidden>{all[i + 1] === 'EXPIRED' ? '/' : '›'}</i> : null}
            </span>
          );
        })}
        <span className="ae-muted ae-small">{num(m, 'invalidated_today') ?? 0} invalidated or expired today</span>
      </section>

      <div className="ae-grid ae-grid-3">
        <Panel
          title={`Processing Queue (${queue.length})`}
          extra={
            <button type="button" className="ae-icon-btn" onClick={onRefresh} title="Reload stage data">
              <RefreshCw size={14} />
            </button>
          }
        >
          {queue.length ? (
            <div className="ae-table-wrap">
              <table className="ae-table">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Task</th>
                    <th>Status</th>
                    <th>ETA</th>
                  </tr>
                </thead>
                <tbody>
                  {queue.map((q) => (
                    <tr key={q.channel_id} className={q.symbol === symbol ? 'is-hl' : ''} onClick={() => setChartSymbol(q.symbol)}>
                      <td>
                        <Sym symbol={q.symbol} /> <small className="ae-muted">{q.timeframe}</small>
                      </td>
                      <td className="ae-clip is-task" title={q.task}>
                        {q.task}
                      </td>
                      <td>
                        <span className={`ae-badge is-${q.status === 'Due' ? 'info' : 'muted'}`}>{q.status === 'Due' ? 'In Progress' : 'Pending'}</span>
                      </td>
                      <td className="ae-num">{until(q.next_at, now)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty>No channel lineage waiting for a closed bar.</Empty>
          )}
        </Panel>
        <Panel title="Recent Detections">
          <DetectionsTable rows={d.detections.slice(0, 8)} digitsFor={digitsFor} empty="No channel transitions in the last 48 hours." />
        </Panel>
        <Panel
          title="Channel Alerts (Today)"
          extra={
            <span className="ae-muted ae-small">
              <Mail size={12} /> {alertToday.SENT ?? 0} sent · {alertToday.FAILED ?? 0} failed · {Object.entries(alertToday).filter(([k]) => !['SENT', 'FAILED'].includes(k)).reduce((a, [, v]) => a + v, 0)} other
            </span>
          }
        >
          {alerts.length ? (
            <div className="ae-table-wrap">
              <table className="ae-table">
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Symbol</th>
                    <th>Event</th>
                    <th>TF</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {alerts.slice(0, 8).map((a) => (
                    <tr key={a.id} title={a.status_reason ?? undefined}>
                      <td>{utc(a.detected_at, true)}</td>
                      <td>
                        <Sym symbol={a.symbol} />
                      </td>
                      <td>{ALERT_LABEL[a.event_type] ?? pretty(a.event_type)}</td>
                      <td>{a.timeframe ?? '—'}</td>
                      <td>
                        <span className={`ae-badge is-${tone(a.status)}`}>{pretty(a.status)}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty>
              <Activity size={14} /> No channel alerts recorded yet. Touch, break, break-retest and TiT events are emailed through the SMTP notification
              worker with persistent de-duplication.
            </Empty>
          )}
        </Panel>
      </div>
    </>
  );
}

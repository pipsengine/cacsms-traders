import { useCallback, useMemo, useState } from 'react';
import { Activity, CircleX, GitBranch, Layers, Mail, RefreshCw, Repeat, Star, Target, Zap } from 'lucide-react';
import { StructureChart, type ChartOverlay } from '../../market-structure/components/StructureChart';
import { useLive, useLiveCandles } from '../../market-structure/live';
import { usePollingAsync } from '../../market-intelligence/hooks/useMarketIntelligence';
import { autonomousApi } from '../api';
import { ALERT_LABEL, CHANNEL_STATE_TONE, list, num, pretty, price, rec, tone, until, utc } from '../format';
import type { ChannelLines, ChannelQueueItem, StageDetail } from '../types';
import { CurrentOperation, DetectionsTable, Donut, Empty, KpiRow, Panel, Sym, useNow, type Kpi } from './DetailParts';

/** Every timeframe the XAUUSD chart must offer. None of these is disabled. */
export const CHART_TFS = ['M1', 'M5', 'M15', 'H1', 'H4', 'W1'] as const;

const BARS_PER_DAY: Record<string, number> = { M1: 1440, M5: 288, M15: 96, H1: 24, H4: 6, H8: 3, D1: 1, W: 1 / 7, W1: 1 / 7 };
const DIR_WORD: Record<string, string> = { ASCENDING: 'Bullish', DESCENDING: 'Bearish', FLAT: 'Ranging' };

function ageText(bars: number | null, tf: string) {
  if (bars == null) return '—';
  const per = BARS_PER_DAY[tf];
  if (!per) return `${bars} bars`;
  const days = bars / per;
  if (days >= 1.5) return `${Math.round(days)} days`;
  if (days >= 1) return '1 day';
  return `${bars} bars`;
}

function chartOverlay(lines: ChannelLines | null, direction: string | null): ChartOverlay {
  const overlay: ChartOverlay = { lines: [], bands: [] };
  if (!lines) return overlay;
  const bear = direction === 'DESCENDING';
  overlay.bands!.push({ upper: [lines.upper[0], lines.upper[1]], lower: [lines.lower[0], lines.lower[1]], tone: bear ? 'red' : 'green' });
  overlay.lines!.push(
    { from: lines.upper[0], to: lines.upper[1], tone: 'res', width: 1.6 },
    { from: lines.lower[0], to: lines.lower[1], tone: 'sup', width: 1.6 },
    { from: lines.mid[0], to: lines.mid[1], tone: 'mid', dashed: true },
  );
  return overlay;
}

function ChannelDetection({ symbol }: { symbol: string | null }) {
  const [tf, setTf] = useState<(typeof CHART_TFS)[number]>('H1');
  const loader = useCallback(
    () => (symbol ? autonomousApi.symbolChart(symbol, tf, 140) : Promise.resolve(null)),
    [symbol, tf],
  );
  const chart = usePollingAsync(loader, [loader], { enabled: !!symbol, intervalMs: 5000 });
  const live = useLive(symbol, [tf], !!symbol);
  const fresh = chart.data?.symbol === symbol && chart.data.timeframe === tf ? chart.data : null;
  const closed = (fresh?.candles ?? []).map((c) => ({ ...c, v: c.v ?? 0 }));
  const bars = useLiveCandles(`${symbol}|${tf}`, closed, live.data?.forming?.[tf]);
  const view = fresh?.channel ?? null;
  const digits = view?.digits ?? (symbol?.startsWith('XAU') ? 2 : symbol?.endsWith('JPY') ? 3 : 5);
  const last = live.data?.quote && !live.data.quote.stale ? live.data.quote.price : bars.at(-1)?.c;
  const overlay = useMemo(() => chartOverlay(view?.lines ?? null, view?.direction ?? null), [view]);
  const widthPct = view?.width != null && view.mid ? (view.width / view.mid) * 100 : null;

  return (
    <Panel
      className="ae-chart-card"
      title={<>Channel Detection {symbol ? <span className="ae-chart-sym">({symbol})</span> : null}</>}
      extra={
        <div className="ae-seg" role="tablist" aria-label="Channel timeframe">
          {CHART_TFS.map((t) => (
            <button type="button" key={t} className={tf === t ? 'is-on' : ''} onClick={() => setTf(t)} aria-selected={tf === t}>
              {t}
            </button>
          ))}
        </div>
      }
    >
      <div className="ae-chart-body">
        <StructureChart
          symbol={symbol ?? ''}
          title={`${tf} channel`}
          tf={tf === 'W1' ? 'W' : tf}
          candles={bars}
          digits={digits}
          lastPrice={last}
          height={268}
          loading={chart.loading && !fresh}
          error={chart.error || undefined}
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
          ]}
        />
        <dl className="ae-chart-stats">
          <div>
            <dt>Channel Direction</dt>
            <dd className={view?.direction === 'ASCENDING' ? 'is-up' : view?.direction === 'DESCENDING' ? 'is-down' : ''}>
              {view?.direction ? DIR_WORD[view.direction] ?? pretty(view.direction) : '—'}
            </dd>
          </div>
          <div>
            <dt>Channel Status</dt>
            <dd>
              {view ? <span className={`ae-badge is-${CHANNEL_STATE_TONE[view.state] ?? 'ok'}`}>{pretty(view.state)}</span> : '—'}
            </dd>
          </div>
          <div>
            <dt>Upper Channel</dt>
            <dd>{price(view?.upper, digits)}</dd>
          </div>
          <div>
            <dt>Lower Channel</dt>
            <dd>{price(view?.lower, digits)}</dd>
          </div>
          <div>
            <dt>Channel Width</dt>
            <dd>
              {price(view?.width, digits)}
              {widthPct != null ? <small> ({widthPct.toFixed(2)}%)</small> : null}
            </dd>
          </div>
          <div>
            <dt>Touches</dt>
            <dd>{view ? (view.touches_upper ?? 0) + (view.touches_lower ?? 0) : '—'}</dd>
          </div>
          <div>
            <dt>Channel Age</dt>
            <dd>{ageText(view?.age_bars ?? null, tf)}</dd>
          </div>
          <div>
            <dt>Quality Score</dt>
            <dd className="is-strong">{view?.quality != null ? `${Math.round(view.quality)}%` : '—'}</dd>
          </div>
        </dl>
      </div>
    </Panel>
  );
}

export function ChannelStage({ d, onRefresh }: { d: StageDetail; onRefresh: () => void }) {
  const m = d.metrics;
  const now = useNow(1000);
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
  const known = d.symbols ?? [];
  const preferred = known.includes('XAUUSD') ? 'XAUUSD' : current?.symbol ?? channels[0]?.symbol ?? known[0] ?? null;
  const defaultSymbol = d.filters.symbol || preferred;
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
            color="#16a34a"
            rows={[
              { label: 'Active Channels', value: num(m, 'active_channels') ?? 0, color: '#16a34a' },
              { label: 'Forming', value: byState.FORMING ?? 0, color: '#94a3b8' },
              { label: 'Touches (Today)', value: num(m, 'touches_today') ?? 0, color: '#2563eb' },
              { label: 'Breaks (Today)', value: num(m, 'breaks_today') ?? 0, color: '#f59e0b' },
              { label: 'Retests (Today)', value: num(m, 'retests_today') ?? 0, color: '#0d9488' },
              { label: 'TiT Detected', value: num(m, 'tit_active') ?? 0, color: '#7c3aed' },
              { label: 'Invalidated', value: num(m, 'invalidated_today') ?? 0, color: '#dc2626' },
            ]}
          />
        </Panel>
        <CurrentOperation
          heading="Current Channel"
          title={current ? `${current.symbol} ${current.timeframe}` : 'Channel Intelligence'}
          badge={current ? `CHANNEL_${current.state}` : null}
          operation={d.current_operation}
          progress={current?.progress ?? null}
          startedAt={current?.started_at ?? d.last_update}
          nextStep={current?.next_step ?? d.next_operation}
          live={d.status === 'RUNNING'}
          color={d.color}
        />
        <ChannelDetection symbol={symbol} />
      </div>

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
                    <th>#</th>
                    <th>Symbol</th>
                    <th>Task</th>
                    <th>Status</th>
                    <th>ETA</th>
                  </tr>
                </thead>
                <tbody>
                  {queue.map((q, i) => (
                    <tr key={q.channel_id} className={q.symbol === symbol ? 'is-hl' : ''} onClick={() => setChartSymbol(q.symbol)}>
                      <td><span className="ae-idx">{i + 1}</span></td>
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

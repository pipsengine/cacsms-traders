import { useMemo, useState } from 'react';
import { ArrowRight, BarChart3, BrainCircuit, CircleCheck, CircleX, Crosshair, Layers, MapPin, Target, TrendingDown, TrendingUp, TriangleAlert, X } from 'lucide-react';
import { ANNOTATION_GROUPS, DEFAULT_GROUPS, type GroupKey } from '../overlay';
import type { MtfPayload, Outlook } from '../types';
import { monitorTitle } from './DailyOutlook';
import { OutlookChart, type CandleState } from './OutlookChart';
import { Card, Chip, Kpi, MiniCandles, TFS, dirTone, dirWord, pct, px, type OutlookTf } from './shared';

const MINI_TFS: OutlookTf[] = ['Y', 'YTD', 'HY', 'Q', 'MN', 'W', 'D1', 'H8', 'H1'];
const SUMMARY_TABS = [
  ['technical', 'Technical Analysis'],
  ['structure', 'Structure Analysis'],
  ['channel', 'Channel Analysis'],
  ['context', 'Context'],
] as const;
const MARK_TONE: Record<string, string> = { res: 'is-red', target: 'is-red', erz: 'is-green', sup: 'is-green', inv: 'is-red' };

export function ChartAnalysis({ o, tf, onTf, candles, chartHeight, mtf }: { o: Outlook; tf: OutlookTf; onTf: (t: OutlookTf) => void; candles: CandleState; chartHeight: number; mtf: MtfPayload | null }) {
  const dp = o.digits;
  const up = o.expected_direction !== 'BEARISH';
  const word = dirWord(o.expected_direction);
  const [groups, setGroups] = useState<GroupKey[]>(DEFAULT_GROUPS);
  const [picked, setPicked] = useState<string | null>(null);
  const [tab, setTab] = useState<(typeof SUMMARY_TABS)[number][0]>('technical');
  const ann = o.chart_annotations.find((a) => a.id === picked) ?? null;
  const linked = useMemo(() => (ann?.evidence_key ? o.evidence.filter((e) => e.key === ann.evidence_key) : []), [ann, o.evidence]);
  const toggle = (g: GroupKey) => setGroups((cur) => (cur.includes(g) ? cur.filter((x) => x !== g) : [...cur, g]));
  const rowFor = (t: string) => o.channels.find((r) => r.tf === t);
  const channelFor = (t: string) => (mtf?.annotations ?? o.chart_annotations).find((a) => a.type === 'channel' && a.tf === t) ?? null;

  return (
    <>
      <div className="mao-kpis">
        <Kpi icon={up ? <TrendingUp size={18} /> : <TrendingDown size={18} />} tone={dirTone(o.expected_direction)} label="AI Verdict" value={<span className={dirTone(o.expected_direction)}>{word.toUpperCase()} (Primary)</span>} bar={o.confidence.primary} sub={`${pct(o.confidence.primary)} Probability`} />
        <Kpi icon={<Layers size={18} />} tone="is-blue" label="Current Phase" value={o.phase.title} sub={o.phase.subtitle} />
        <Kpi icon={<Target size={18} />} tone="is-blue" label="Next Expected Move" value={<span className={dirTone(o.expected_direction)}>{o.expected_next_move.label}</span>}>
          <b className={`mao-kpi-big ${dirTone(o.expected_direction)}`}>{o.expected_next_move.path}</b>
        </Kpi>
        <Kpi icon={<TriangleAlert size={18} />} tone="is-bear" label="Invalidation" value={<span className="is-bear">{px(o.invalidation.price, dp)}</span>} sub={`Close ${up ? 'below' : 'above'} invalidates ${word.toLowerCase()} scenario`} />
        <Kpi icon={<BarChart3 size={18} />} tone="is-blue" label="Timeframe Focus" value={o.timeframe_focus.join(' → ')} sub={o.monitoring?.status ? monitorTitle(o) : `Looking for ${word.toLowerCase()} confirmation`} />
      </div>

      <div className="mao-main">
        <OutlookChart
          o={o}
          tf={tf}
          onTf={onTf}
          candles={candles}
          title={`AI Chart Analysis (${tf})`}
          mode="chart"
          height={chartHeight}
          groups={groups}
          onPick={(id) => setPicked((cur) => (cur === id ? null : id))}
          selected={picked}
          footer={
            ann ? (
              <div className="mao-pick">
                <header>
                  <MapPin size={14} />
                  <b>{ann.label}</b>
                  <Chip tone="is-blue">{ann.type.replace('_', ' ')}</Chip>
                  <Chip tone="is-gray">{ann.tf === '*' ? 'All TFs' : ann.tf}</Chip>
                  <small>Source: {ann.source}</small>
                  <button aria-label="Close annotation detail" onClick={() => setPicked(null)}>
                    <X size={14} />
                  </button>
                </header>
                <p>{ann.detail}</p>
                {linked.length ? (
                  <ul>
                    {linked.map((e) => (
                      <li key={e.id}>
                        <b>{e.id}</b> {e.title} — {e.detail} <small>({e.source} · {e.tf} · weight {e.weight.toFixed(2)})</small>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <small className="mao-muted">Derived directly from the {ann.source} output at the frozen close.</small>
                )}
              </div>
            ) : (
              <small className="mao-hint">Select a tag, zone, level or marker on the chart to see its evidence and source engine.</small>
            )
          }
        />
        <Card title="Multi-Timeframe Chart View" icon={<Layers size={15} />} className="mao-mtf">
          <div className="mao-tf is-full" role="group" aria-label="Main chart timeframe">
            {TFS.map((t) => (
              <button key={t} className={tf === t ? 'is-on' : ''} onClick={() => onTf(t)}>
                {t}
              </button>
            ))}
          </div>
          <div className="mao-mtf-grid">
            {MINI_TFS.map((t) => {
              const r = rowFor(t);
              const tag = !r?.available ? 'N/A' : r.state === 'Pullback' ? 'Pullback' : r.direction ?? '—';
              return (
                <button key={t} className={`mao-mtf-cell ${tf === t ? 'is-on' : ''}`} onClick={() => onTf(t)} title={r?.available ? `${t}: ${r.direction} channel, ${r.zone?.toLowerCase()}` : `${t}: no valid channel`}>
                  <header>
                    <b>{t}</b>
                    <Chip tone={tag === 'Pullback' ? 'is-rose' : tag === 'Bullish' ? 'is-green' : tag === 'Bearish' ? 'is-red' : 'is-gray'}>{tag}</Chip>
                  </header>
                  <MiniCandles candles={mtf?.candles?.[t] ?? []} channel={channelFor(t)} tone={r?.dir === -1 ? 'red' : 'blue'} height={58} />
                </button>
              );
            })}
          </div>
        </Card>
      </div>

      <div className="mao-row3 is-chart">
        <Card title="AI Chart Annotations" icon={<Crosshair size={15} />}>
          <div className="mao-toggles">
            {ANNOTATION_GROUPS.map((g) => (
              <label key={g.key} className={g.key === 'invalidation' ? 'is-inv' : ''}>
                <input type="checkbox" checked={groups.includes(g.key)} onChange={() => toggle(g.key)} />
                <span>{g.label}</span>
                <small>{o.chart_annotations.filter((a) => a.group === g.key && (a.tf === '*' || a.tf === tf || (tf === 'M30' && a.tf === 'H1'))).length}</small>
              </label>
            ))}
          </div>
        </Card>
        <Card title="Smart Analysis Summary" icon={<BrainCircuit size={15} />}>
          <div className="mao-subtabs" role="tablist">
            {SUMMARY_TABS.map(([k, label]) => (
              <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? 'is-on' : ''} onClick={() => setTab(k)}>
                {label}
              </button>
            ))}
          </div>
          <ul className="mao-summary">
            {(o.smart_summary[tab] ?? []).map((l) => (
              <li key={l.evidence_id + l.text} className={`is-${l.tone}`}>
                {l.tone === 'fail' ? <CircleX size={14} /> : l.tone === 'warn' ? <TriangleAlert size={14} /> : <CircleCheck size={14} />}
                <span>{l.text}</span>
              </li>
            ))}
            {!(o.smart_summary[tab] ?? []).length ? <li className="mao-muted">No evidence from this engine group at the frozen close.</li> : null}
          </ul>
        </Card>
        <Card title={`AI Mark Points (${tf})`} icon={<MapPin size={15} />}>
          <table className="mao-table is-compact">
            <thead>
              <tr>
                <th>Type</th>
                <th>Price</th>
                <th>Label</th>
                <th>Description</th>
              </tr>
            </thead>
            <tbody>
              {o.mark_points.map((m, i) => (
                <tr key={i}>
                  <td className={`mao-type ${MARK_TONE[m.tone] ?? ''}`}>{m.type}</td>
                  <td className="num">{m.lo != null && m.hi != null ? `${px(m.lo, dp)} – ${px(m.hi, dp)}` : px(m.price, dp)}</td>
                  <td>{m.label}</td>
                  <td>{m.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <small className="mao-foot">
            Plan <ArrowRight size={11} /> {o.handoff}
          </small>
        </Card>
      </div>
    </>
  );
}

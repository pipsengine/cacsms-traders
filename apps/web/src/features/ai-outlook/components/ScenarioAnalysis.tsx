import { Activity, BrainCircuit, Crosshair, GitBranch, ListChecks, Route, Sparkles, TrendingDown, TrendingUp } from 'lucide-react';
import type { Outlook } from '../types';
import { ScenarioList } from './DailyOutlook';
import { OutlookChart, type CandleState } from './OutlookChart';
import { Card, Check, Chip, Kpi, dirTone, dirWord, pct, stepLabel, stepTone, type OutlookTf } from './shared';

const signWord = (s: number | undefined) => (s === 1 ? 'Bullish' : s === -1 ? 'Bearish' : 'Neutral');

export function contextCards(o: Outlook) {
  const ev = o.evidence;
  const top = (keys: string[], tfs?: string[]) =>
    ev.filter((e) => keys.includes(e.source_key) && (!tfs || tfs.includes(e.tf))).sort((a, b) => b.weight - a.weight)[0];
  const structure = top(['STRUCTURE'], ['D1']) ?? top(['STRUCTURE']);
  const fractal = top(['FRACTAL']);
  const d1 = o.channels.find((r) => r.tf === 'D1' && r.available) ?? o.channels.find((r) => r.tf === 'W' && r.available);
  const st = o.strength;
  return { structure, fractal, d1, st };
}

export function ScenarioAnalysis({ o, tf, onTf, candles, chartHeight }: { o: Outlook; tf: OutlookTf; onTf: (t: OutlookTf) => void; candles: CandleState; chartHeight: number }) {
  const { structure, fractal, d1, st } = contextCards(o);
  const steps = o.monitoring?.steps ?? [];
  const p = o.primary_scenario;
  const a = o.alternative_scenario;
  const pWord = dirWord(o.expected_direction === 'RANGE' ? null : o.expected_direction);
  const aWord = a.direction ?? '—';
  return (
    <>
      <div className="mao-kpis">
        <Kpi icon={signWord(structure?.sign) === 'Bearish' ? <TrendingDown size={18} /> : <TrendingUp size={18} />} tone={dirTone(signWord(structure?.sign))} label="Market Structure" value={<span className={dirTone(signWord(structure?.sign))}>{signWord(structure?.sign)}</span>} sub={structure?.detail ?? 'No confirmed swing structure'} />
        <Kpi icon={<GitBranch size={18} />} tone="is-blue" label="Channel Context" value={d1 ? <span className={dirTone(d1.direction)}>{d1.direction === 'Ranging' ? 'Inside Flat Channel' : `Within ${d1.direction === 'Bullish' ? 'Uptrend' : 'Downtrend'} Channel`}</span> : '—'} sub={d1 ? `${d1.tf} channel: price in ${d1.zone?.toLowerCase()}, ${d1.validity?.toLowerCase()} channel.` : 'No valid channel'} />
        <Kpi icon={<Sparkles size={18} />} tone="is-purple" label="Fractal Context" value={<span className="is-purple-t">{fractal?.title ?? 'No active fractal'}</span>} sub={fractal?.detail ?? '—'} />
        <Kpi icon={<Activity size={18} />} tone={st ? dirTone(st.differential > 0 ? 'Bullish' : 'Bearish') : 'is-gray'} label="Strength Intelligence" value={st ? <span className={dirTone(st.differential > 0 ? 'Bullish' : 'Bearish')}>{st.differential > 0 ? 'Bullish' : st.differential < 0 ? 'Bearish' : 'Balanced'}</span> : '—'} sub={st ? `${st.label ?? ''} (differential ${st.differential > 0 ? '+' : ''}${st.differential.toFixed(1)}).` : 'No strength snapshot at the frozen close'} />
        <Kpi icon={<BrainCircuit size={18} />} tone={dirTone(o.expected_direction)} label="AI Bias (Next 1–5 Days)" value={<span className={dirTone(o.expected_direction)}>{p.label}</span>} bar={p.probability} sub={`${pct(p.probability)} Probability`} />
      </div>

      <div className="mao-main">
        <OutlookChart o={o} tf={tf} onTf={onTf} candles={candles} title={`${tf === 'D1' ? 'Daily' : tf} Chart with AI Scenarios`} mode="scenarios" height={chartHeight} />
        <Card title="AI Scenario Probabilities" icon={<Crosshair size={15} />}>
          <ScenarioList o={o} detailed />
        </Card>
      </div>

      <div className="mao-row3 is-even">
        <Card title="Scenario Conditions & Triggers" icon={<ListChecks size={15} />}>
          {o.scenario_conditions.length ? (
            <table className="mao-table is-compact">
              <thead>
                <tr>
                  <th>Condition</th>
                  <th className="center">{pWord}</th>
                  <th className="center">{aWord}</th>
                  <th className="center">Consolidation</th>
                </tr>
              </thead>
              <tbody>
                {o.scenario_conditions.map((c) => (
                  <tr key={c.condition}>
                    <td>{c.condition}</td>
                    <td className="center">
                      <Check value={c.primary} />
                    </td>
                    <td className="center">
                      <Check value={c.alternative} />
                    </td>
                    <td className="center">
                      <Check value={c.range} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="mao-muted">Primary scenario is consolidation — directional triggers are not applicable.</p>
          )}
        </Card>
        <Card title={`Expected Sequence (${p.label})`} icon={<Route size={15} />}>
          <ol className="mao-seq">
            {(p.sequence ?? []).map((s) => {
              const m = steps.find((x) => x.key === s.key);
              return (
                <li key={s.key}>
                  <i className={dirTone(o.expected_direction)}>{s.step}</i>
                  <span>{s.label}</span>
                  <Chip tone={stepTone(m)} title={m?.at ?? undefined}>
                    {stepLabel(m)}
                  </Chip>
                </li>
              );
            })}
          </ol>
          <small className="mao-foot">Status is updated intraday from closed H1/M30 bars; the published sequence never changes.</small>
        </Card>
        <Card title={`Alternative Scenario (${aWord})`} icon={<Route size={15} />}>
          <ol className="mao-seq">
            {(a.sequence ?? []).map((s) => (
              <li key={s.key}>
                <i className={dirTone(a.direction)}>{s.step}</i>
                <span>{s.label}</span>
                <Chip tone={o.monitoring?.status === 'INVALIDATED' && s.step === 1 ? 'is-red' : 'is-amber'}>{o.monitoring?.status === 'INVALIDATED' && s.step === 1 ? 'Triggered' : 'Pending'}</Chip>
              </li>
            ))}
          </ol>
        </Card>
      </div>
    </>
  );
}

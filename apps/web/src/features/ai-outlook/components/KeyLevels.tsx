import { BarChart3, CircleCheck, Layers, Lightbulb, Radar, ShieldCheck, Target, TrendingDown, TrendingUp, TriangleAlert } from 'lucide-react';
import type { Outlook } from '../types';
import { OutlookChart, type CandleState } from './OutlookChart';
import { Card, Chip, Kpi, dirTone, dirWord, pct, px, type OutlookTf } from './shared';

const IMP_TONE: Record<string, string> = { High: 'is-red', Medium: 'is-amber', Low: 'is-gray' };

export function KeyLevels({ o, tf, onTf, candles, chartHeight }: { o: Outlook; tf: OutlookTf; onTf: (t: OutlookTf) => void; candles: CandleState; chartHeight: number }) {
  const dp = o.digits;
  const up = o.expected_direction !== 'BEARISH';
  const word = dirWord(o.expected_direction);
  const range = o.range_scenario.range;
  const width = range ? range[1] - range[0] : null;
  const keySup = o.supports[0];
  const keyRes = o.resistances[0];
  const rows = [...o.key_levels]
    .filter((l) => Math.abs(l.distance_atr ?? 99) <= 6)
    .sort((a, b) => (a.type === b.type ? b.price - a.price : a.type === 'Resistance' ? -1 : 1))
    .slice(0, 22);
  const p = o.primary_scenario;
  const a = o.alternative_scenario;
  const r = o.range_scenario;
  const takeaways = [
    `${word} bias at ${pct(o.confidence.primary)}; key ${up ? 'support' : 'resistance'} at the ERZ ${o.erz.label} (${o.erz.basis}).`,
    o.primary_scenario.key_trigger ? `Watch for ${o.primary_scenario.key_trigger} toward ${o.targets.map((t) => px(t.price, dp)).join(' → ')}.` : null,
    `Close ${up ? 'below' : 'above'} ${px(o.invalidation.price, dp)} invalidates the ${word.toLowerCase()} view and activates the ${a.label.toLowerCase()} toward ${px(a.targets?.[0]?.price, dp)}.`,
    o.session_plan.map((s) => `${s.label.replace(' Session', '')}: ${s.badge.toLowerCase()}`).join('. ') + '.',
  ].filter(Boolean) as string[];
  return (
    <>
      <div className="mao-kpis is-six">
        <Kpi icon={up ? <TrendingUp size={18} /> : <TrendingDown size={18} />} tone={dirTone(o.expected_direction)} label="Market Bias" value={<span className={dirTone(o.expected_direction)}>{word.toUpperCase()}</span>} bar={o.confidence.primary} sub={`${pct(o.confidence.primary)} Probability`} />
        <Kpi icon={<BarChart3 size={18} />} tone="is-purple" label="Primary Range (D1)" value={range ? `${px(range[0], dp)} – ${px(range[1], dp)}` : '—'} sub={width != null ? `${px(width, dp)} (${((width / o.price) * 100).toFixed(2)}%)` : undefined} />
        <Kpi icon={<ShieldCheck size={18} />} tone="is-bull" label="Key Support" value={<span className="is-bull">{px(keySup?.price, dp)}</span>} sub={keySup?.label ?? '—'} />
        <Kpi icon={<ShieldCheck size={18} />} tone="is-bear" label="Key Resistance" value={<span className="is-bear">{px(keyRes?.price, dp)}</span>} sub={keyRes?.label ?? '—'} />
        <Kpi icon={<Radar size={18} />} tone="is-blue" label="Next Target" value={px(o.targets[0]?.price, dp)} sub={o.targets[0]?.label} />
        <Kpi icon={<TriangleAlert size={18} />} tone="is-bear" label="Invalidation Level" value={<span className="is-bear">{px(o.invalidation.price, dp)}</span>} sub={`Close ${up ? 'below' : 'above'} invalidates ${word.toLowerCase()} view`} />
      </div>

      <div className="mao-main is-wide-side">
        <OutlookChart o={o} tf={tf} onTf={onTf} candles={candles} title={`Key Levels Chart (${tf})`} mode="levels" height={chartHeight} />
        <Card title="Key Levels (Multi-Timeframe)" icon={<Layers size={15} />}>
          <div className="mao-scroll">
            <table className="mao-table is-compact">
              <thead>
                <tr>
                  <th>TF</th>
                  <th>Type</th>
                  <th>Level</th>
                  <th>Details</th>
                  <th>Importance</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((l, i) => (
                  <tr key={i} title={`${l.source} · ${l.distance_atr != null ? `${l.distance_atr > 0 ? '+' : ''}${l.distance_atr.toFixed(2)} ATR` : ''}`}>
                    <td>
                      <b>{l.tf}</b>
                    </td>
                    <td>
                      <Chip tone={l.type === 'Resistance' ? 'is-red' : 'is-green'}>{l.type}</Chip>
                    </td>
                    <td className="num">{px(l.price, dp)}</td>
                    <td>
                      {l.label}
                      {l.liquidity ? <small className="mao-liq"> · liquidity</small> : null}
                    </td>
                    <td>
                      <Chip tone={IMP_TONE[l.importance]}>{l.importance}</Chip>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      <div className="mao-row2">
        <Card title="Key Levels Zones" icon={<Target size={15} />}>
          <table className="mao-table is-compact">
            <thead>
              <tr>
                <th>Zone</th>
                <th>From</th>
                <th>To</th>
                <th>Width (ATR)</th>
                <th>Type</th>
                <th>Strength</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {o.key_zones.map((z) => (
                <tr key={z.zone}>
                  <td>
                    <Chip tone={z.zone.startsWith('Target') ? 'is-red' : z.zone.startsWith('Invalidation') ? 'is-rose' : 'is-green'}>{z.zone}</Chip>
                  </td>
                  <td className="num">{px(z.from, dp)}</td>
                  <td className="num">{px(z.to, dp)}</td>
                  <td className="num">{z.width_atr?.toFixed(2) ?? '—'}</td>
                  <td>
                    <Chip tone={z.type === 'Resistance' ? 'is-red' : 'is-green'}>{z.type}</Chip>
                  </td>
                  <td>
                    <Chip tone={z.strength === 'Strong' ? 'is-green' : 'is-amber'}>{z.strength}</Chip>
                  </td>
                  <td>
                    <Chip tone={z.status === 'Testing' ? 'is-amber' : 'is-green'}>{z.status}</Chip>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
        <div className="mao-stack">
          <Card title="Today's Opportunity Summary" icon={<CircleCheck size={15} />}>
            <table className="mao-table is-compact">
              <thead>
                <tr>
                  <th>Setup</th>
                  <th>Direction</th>
                  <th>Reaction Zone</th>
                  <th>Objective 1</th>
                  <th>Objective 2</th>
                  <th>Invalidation</th>
                  <th>Probability</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Primary Setup</td>
                  <td>
                    <Chip tone={up ? 'is-green' : 'is-red'}>{word}</Chip>
                  </td>
                  <td className="num">{o.erz.label}</td>
                  <td className="num">{px(p.targets?.[0]?.price, dp)}</td>
                  <td className="num">{px(p.targets?.[1]?.price, dp)}</td>
                  <td className="num is-bear">{px(o.invalidation.price, dp)}</td>
                  <td>
                    <Chip tone="is-green">{pct(p.probability)}</Chip>
                  </td>
                </tr>
                <tr>
                  <td>Alternative Setup</td>
                  <td>
                    <Chip tone={a.direction === 'Bearish' ? 'is-red' : 'is-green'}>{a.direction}</Chip>
                  </td>
                  <td className="num">{a.key_trigger}</td>
                  <td className="num">{px(a.targets?.[0]?.price, dp)}</td>
                  <td className="num">{px(a.targets?.[1]?.price, dp)}</td>
                  <td className="num is-bear">{px(a.invalidation.price, dp)}</td>
                  <td>
                    <Chip tone="is-red">{pct(a.probability)}</Chip>
                  </td>
                </tr>
                <tr>
                  <td>Consolidation</td>
                  <td>
                    <Chip tone="is-blue">Range</Chip>
                  </td>
                  <td className="num">{r.range ? `${px(r.range[0], dp)} – ${px(r.range[1], dp)}` : '—'}</td>
                  <td>—</td>
                  <td>—</td>
                  <td>Outside range</td>
                  <td>
                    <Chip tone="is-blue">{pct(r.probability)}</Chip>
                  </td>
                </tr>
              </tbody>
            </table>
            <small className="mao-foot">{o.handoff}</small>
          </Card>
          <Card title="Key Takeaways" icon={<Lightbulb size={15} />} className="mao-takeaways">
            <ul>
              {takeaways.map((t) => (
                <li key={t}>
                  <CircleCheck size={13} /> {t}
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </>
  );
}

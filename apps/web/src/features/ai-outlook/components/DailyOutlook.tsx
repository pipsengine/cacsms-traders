import { ArrowLeftRight, Crosshair, Flag, Gauge, Hourglass, Layers, Lightbulb, ListChecks, Route, Target, TrendingDown, TrendingUp, TriangleAlert } from 'lucide-react';
import type { Outlook } from '../types';
import { OutlookChart, type CandleState } from './OutlookChart';
import { Card, Chip, Kpi, ProbBar, dirTone, dirWord, pct, px, type OutlookTf } from './shared';

const dirIcon = (d: string | null | undefined, size = 20) =>
  d === 'Bullish' || d === 'BULLISH' ? <TrendingUp size={size} /> : d === 'Bearish' || d === 'BEARISH' ? <TrendingDown size={size} /> : <ArrowLeftRight size={size} />;

function invalidationText(o: Outlook, s: Outlook['primary_scenario'], n: number) {
  if (s.invalidation.price == null) return s.invalidation.label;
  if (n !== 1) return s.invalidation.label;
  return `Close ${o.expected_direction === 'BEARISH' ? 'above' : 'below'} ${px(s.invalidation.price, o.digits)}`;
}

export function ScenarioList({ o, detailed = false }: { o: Outlook; detailed?: boolean }) {
  const dp = o.digits;
  const items = [
    { s: o.primary_scenario, n: 1, suffix: ' (Primary)' },
    { s: o.alternative_scenario, n: 2, suffix: '' },
    { s: o.range_scenario, n: 3, suffix: '' },
  ];
  return (
    <div className="mao-scenarios">
      {items.map(({ s, n, suffix }) => {
        const tone = n === 3 ? 'is-range' : dirTone(s.direction);
        return (
          <article key={n} className={`mao-scenario ${tone}`}>
            <span className="mao-scenario-icon">{n === 3 ? <ArrowLeftRight size={18} /> : dirIcon(s.direction, 18)}</span>
            <div>
              <header>
                <b>
                  {n}. {s.label}
                  {suffix}
                </b>
                <Chip tone={n === 3 ? 'is-blue' : tone === 'is-bull' ? 'is-green' : 'is-red'}>{pct(s.probability)}</Chip>
              </header>
              <p>{s.summary}</p>
              <ProbBar value={s.probability} tone={tone} />
              {detailed ? (
                <table className="mao-scn-kv">
                  <tbody>
                    {s.key_trigger ? (
                      <tr>
                        <th>Key Trigger</th>
                        <td>{s.key_trigger}</td>
                      </tr>
                    ) : null}
                    {(s.targets ?? []).slice(0, 2).map((t, i) => (
                      <tr key={i}>
                        <th>Target {i + 1}</th>
                        <td>
                          {px(t.price, dp)} <small>({t.label})</small>
                        </td>
                      </tr>
                    ))}
                    {s.range ? (
                      <tr>
                        <th>Range</th>
                        <td>
                          {px(s.range[0], dp)} – {px(s.range[1], dp)}
                        </td>
                      </tr>
                    ) : null}
                    <tr>
                      <th className="is-inv">Invalidation</th>
                      <td>{invalidationText(o, s, n)}</td>
                    </tr>
                  </tbody>
                </table>
              ) : null}
            </div>
          </article>
        );
      })}
    </div>
  );
}

export function ConfidenceMeter({ o }: { o: Outlook }) {
  const c = o.confidence;
  const rows = [
    { label: 'Overall Confidence', v: c.primary, tone: 'is-bull' },
    { label: 'Bullish Scenario', v: c.bullish, tone: 'is-bull' },
    { label: 'Bearish Scenario', v: c.bearish, tone: 'is-bear' },
    { label: 'Consolidation', v: c.range, tone: 'is-range' },
  ];
  return (
    <Card title="AI Confidence Meter" icon={<Gauge size={15} />} className="mao-conf">
      {rows.map((r) => (
        <div key={r.label} className="mao-conf-row">
          <span>{r.label}</span>
          <b>{pct(r.v)}</b>
          <ProbBar value={r.v} tone={r.tone} />
        </div>
      ))}
      <small className="mao-foot">
        {c.calibration.applied
          ? `Calibrated on ${c.calibration.samples} evaluated outlooks (bucket ${c.calibration.bucket}: ${pct(c.calibration.hit_rate)} hit rate; raw ${pct(c.calibration.raw)}).`
          : `Evidence score in the ${c.calibration.bucket} bucket — historical calibration starts once evaluated outlooks exist.`}{' '}
        This score is closed-bar evidence alignment, not a win probability. Uncertainty {o.uncertainty.toFixed(0)}%.
      </small>
    </Card>
  );
}

export function SessionPlanCard({ o }: { o: Outlook }) {
  return (
    <Card title="Next Session Plan" icon={<Route size={15} />} className="mao-plan">
      <ol className="mao-plan-list">
        {o.session_plan.map((s) => (
          <li key={s.key}>
            <i aria-hidden />
            <b>{s.label}</b>
            <span>{s.plan}</span>
          </li>
        ))}
      </ol>
    </Card>
  );
}

export function KeyLevelsMini({ o }: { o: Outlook }) {
  const dp = o.digits;
  const up = o.expected_direction !== 'BEARISH';
  const res = o.resistances.slice(0, 2);
  const sup = o.supports.slice(0, 3);
  const rows = [
    ...res.map((r) => ({ type: 'Resistance', price: r.price, detail: r.label, tone: 'is-red' })),
    ...sup.map((r) => ({ type: 'Support', price: r.price, detail: r.label, tone: 'is-green' })),
    { type: up ? 'Support' : 'Resistance', price: o.erz.lo, detail: 'ERZ Lower Boundary', tone: up ? 'is-green' : 'is-red' },
    ...o.targets.map((t, i) => ({ type: `Target ${i + 1}`, price: t.price, detail: i ? 'Second objective' : 'First objective', tone: 'is-green' })),
    { type: 'Invalidation', price: o.invalidation.price, detail: `Close ${up ? 'below' : 'above'} (${o.invalidation.label})`, tone: 'is-red' },
  ];
  return (
    <table className="mao-table is-compact">
      <thead>
        <tr>
          <th>Type</th>
          <th>Level</th>
          <th>Details</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>
            <td className={`mao-type ${r.tone}`}>{r.type}</td>
            <td className={`num ${r.tone}`}>{px(r.price, dp)}</td>
            <td>{r.detail}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function MtfChannelTable({ o }: { o: Outlook }) {
  const dp = o.digits;
  return (
    <table className="mao-table is-compact">
      <thead>
        <tr>
          <th>TF</th>
          <th>Channel State</th>
          <th>Direction</th>
          <th>Price Position</th>
          <th>Key Level (Lower – Upper)</th>
        </tr>
      </thead>
      <tbody>
        {o.channels.map((r) => (
          <tr key={r.tf}>
            <td>
              <b>{r.tf}</b>
            </td>
            {r.available ? (
              <>
                <td>
                  <Chip tone={r.state === 'Pullback' ? 'is-red' : r.state === 'Forming' ? 'is-amber' : r.state?.startsWith('Breakout') ? 'is-blue' : 'is-green'}>{r.state}</Chip>
                </td>
                <td>
                  <Chip tone={r.dir === 1 ? 'is-green' : r.dir === -1 ? 'is-red' : 'is-gray'}>{r.direction}</Chip>
                </td>
                <td className={r.zone === 'Lower Zone' || r.zone === 'Upper Zone' ? 'is-amber-t' : ''}>{r.zone}</td>
                <td className="num">
                  {px(r.lower, dp)} – {px(r.upper, dp)}
                </td>
              </>
            ) : (
              <td colSpan={4} className="mao-muted">
                Insufficient history for a valid channel
              </td>
            )}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function AnalysisOutcome({ o }: { o: Outlook }) {
  const dp = o.digits;
  const tg = o.targets.length ? o.targets : o.primary_scenario.targets ?? [];
  const entry = o.erz.mid;
  const rows = [
    { label: 'Possible entry', price: entry, tone: 'is-blue' as const },
    { label: 'Target 1', price: tg[0]?.price ?? null, tone: 'is-bull' as const },
    { label: 'Target 2', price: tg[1]?.price ?? null, tone: 'is-bull' as const },
    { label: 'SL', price: o.invalidation.price, tone: 'is-bear' as const },
  ];
  return (
    <table className="mao-outcome-kv" aria-label="Primary scenario trade levels">
      <tbody>
        {rows.map((r) => (
          <tr key={r.label}>
            <th>{r.label}</th>
            <td className={r.tone}>{px(r.price, dp)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function DailyOutlook({ o, tf, onTf, candles, chartHeight }: { o: Outlook; tf: OutlookTf; onTf: (t: OutlookTf) => void; candles: CandleState; chartHeight: number }) {
  const dp = o.digits;
  const up = o.expected_direction !== 'BEARISH';
  const word = dirWord(o.expected_direction);
  return (
    <>
      <div className="mao-kpis is-daily is-six">
        <Kpi icon={dirIcon(o.expected_direction)} tone={dirTone(o.expected_direction)} label="AI Bias" value={<span className={dirTone(o.expected_direction)}>{o.directional_context ?? word}</span>} bar={o.evidence_score?.value ?? o.confidence.primary} sub={`${pct(o.evidence_score?.value ?? o.confidence.primary)} evidence score · ${(o.market_regime ?? o.regime).label} regime`} />
        <Kpi icon={<ListChecks size={18} />} tone="is-blue" label="Key Drivers">
          <ul className="mao-drivers">
            {o.key_drivers.map((k) => (
              <li key={k.id} title={`${k.source} · ${k.tf} — ${k.detail}`}>
                {k.title}
              </li>
            ))}
          </ul>
        </Kpi>
        <Kpi icon={<Target size={18} />} tone="is-blue" label="Expected Next Move" value={<span className={dirTone(o.expected_direction)}>{o.expected_next_move.label}</span>} sub="Target Zone">
          <b className={`mao-kpi-big ${dirTone(o.expected_direction)}`}>{o.expected_next_move.target_zone}</b>
        </Kpi>
        <Kpi icon={<Hourglass size={18} />} tone="is-blue" label="Current Status" value={o.monitoring?.status ? monitorTitle(o) : o.current_status.title} sub={o.monitoring?.system_action?.detail ?? o.current_status.detail} />
        <Kpi icon={<TriangleAlert size={18} />} tone="is-bear" label="Invalidation Level" value={<span className="is-bear">{px(o.invalidation.price, dp)}</span>} sub={`Close ${up ? 'below' : 'above'} invalidates the ${word.toLowerCase()} scenario and activates the ${o.alternative_scenario.label.toLowerCase()} hypothesis.`} />
        <Kpi icon={<Flag size={18} />} tone="is-purple" label="Analysis Outcome" sub="Primary scenario · published at daily close">
          <AnalysisOutcome o={o} />
        </Kpi>
      </div>

      <div className="mao-main">
        <OutlookChart o={o} tf={tf} onTf={onTf} candles={candles} title={`${tf === 'D1' ? 'Daily' : tf} Outlook Chart`} mode="outlook" height={chartHeight} />
        <Card title="AI Scenario Analysis" icon={<Crosshair size={15} />}>
          <ScenarioList o={o} />
        </Card>
      </div>

      <div className="mao-row3">
        <Card title="Multi-Timeframe Channel Analysis" icon={<Layers size={15} />}>
          <MtfChannelTable o={o} />
        </Card>
        <div className="mao-stack">
          <Card title="Key Levels" icon={<Target size={15} />}>
            <KeyLevelsMini o={o} />
          </Card>
          <Card title="AI Conclusion" icon={<Lightbulb size={15} />} className="mao-conclusion">
            <p>{o.conclusion}</p>
            <small className="mao-foot">{o.handoff}</small>
          </Card>
        </div>
        <div className="mao-stack">
          <SessionPlanCard o={o} />
          <ConfidenceMeter o={o} />
        </div>
      </div>
    </>
  );
}

const MONITOR_TITLE: Record<string, string> = {
  AWAITING_REACTION: 'Waiting for reaction at ERZ',
  REACTION: 'Reaction at ERZ observed',
  EXHAUSTION: 'Exhaustion inside the ERZ',
  CHOCH: 'H1 CHoCH confirmed',
  BOS: 'H1 BOS confirmed',
  RETEST: 'Retest confirmed',
  T1: 'Objective 1 reached',
  T2: 'Objective 2 reached',
  INVALIDATED: 'Scenario invalidated',
  RANGE_WATCH: 'Watching range boundaries',
};
export const monitorTitle = (o: Outlook) => MONITOR_TITLE[o.monitoring?.status ?? ''] ?? o.current_status.title;

import type { ReactNode } from 'react';
import {
  ArrowDownRight,
  ArrowLeftRight,
  ArrowUpRight,
  Check,
  Circle,
  CircleDot,
  Crosshair,
  Gauge,
  GitBranch,
  Info,
  Layers3,
  LocateFixed,
  Search,
  ShieldCheck,
  Waves,
} from 'lucide-react';
import { fmtPrice } from '../../market-scanner/format';
import type { RangeCore, RangeRow, RangeView } from '../types';

const fmtDate = (iso: string | null | undefined) =>
  iso ? new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(new Date(iso)) : '—';

export function Pill({ tone, children }: { tone: 'green' | 'amber' | 'red' | 'gray' | 'blue'; children: ReactNode }) {
  return <span className={`mst-pill is-${tone}`}>{children}</span>;
}

export const regimeTone = (k?: string) =>
  k === 'RANGING' ? 'amber' : k === 'BULLISH' ? 'green' : k === 'BEARISH' ? 'red' : 'gray';

const stateTone = (k?: string) => (k === 'MATURE' || k === 'VALIDATED' ? 'green' : k === 'BREAKOUT_THREAT' ? 'red' : 'amber');

function Card({ icon, label, children, cls = '' }: { icon: ReactNode; label: string; children: ReactNode; cls?: string }) {
  return (
    <div className={`mst-card mst-stat ${cls}`}>
      <span className="mst-stat-icon" aria-hidden>
        {icon}
      </span>
      <div className="mst-stat-body">
        <span className="mst-stat-label">{label}</span>
        {children}
      </div>
    </div>
  );
}

export function RangeSummaryCards({ row, core, view, digits }: { row: RangeRow; core: RangeCore; view: RangeView; digits: number }) {
  const pos = Math.max(0, Math.min(100, view.position));
  const posTone = view.position_band.key.includes('LOWER') || view.position_band.key === 'BELOW_RANGE' ? 'green' : view.position_band.key.includes('UPPER') || view.position_band.key === 'ABOVE_RANGE' ? 'red' : 'blue';
  return (
    <section className="mst-stats">
      <Card icon={<Waves size={18} />} label="W Regime">
        <strong className={`mst-regime is-${regimeTone(core.regime.key)}`}>
          {core.regime.label.toUpperCase()} {core.state ? <Pill tone={stateTone(core.state.key)}>{core.state.label.toUpperCase()}</Pill> : null}
        </strong>
        <small>
          {core.ranging
            ? `Sideways within range for ${core.age_weeks} weeks`
            : `No validated range · last ${core.age_weeks} weeks of swings`}
        </small>
      </Card>
      <Card icon={<ArrowLeftRight size={18} />} label={core.ranging ? 'Weekly Range' : 'Weekly Swing Range'}>
        <strong>
          {fmtPrice(core.range_low, digits)} – {fmtPrice(core.range_high, digits)}
        </strong>
        <small>
          Range Width: {fmtPrice(core.width, digits)}
          {core.width_atr != null ? ` (${core.width_atr.toFixed(2)} ATR)` : ''}
          <br />
          Tests: High <b>{core.touches_high}</b> | Low <b>{core.touches_low}</b>
        </small>
      </Card>
      <Card icon={<Crosshair size={18} />} label="Current Price">
        <strong>{fmtPrice(row.price, digits)}</strong>
        <small className={row.change == null ? '' : row.change >= 0 ? 'up' : 'down'}>
          {row.change != null ? `${row.change > 0 ? '+' : ''}${fmtPrice(row.change, digits)} (${row.change_pct! > 0 ? '+' : ''}${row.change_pct?.toFixed(2)}%)` : '—'}
          <span className="mst-muted"> · {row.price_live ? 'live' : 'last close'}</span>
        </small>
      </Card>
      <Card icon={<LocateFixed size={18} />} label="Range Position">
        <strong className="mst-pos">
          <span className="mst-meter">
            <i style={{ width: `${pos}%` }} />
          </span>
          {view.position.toFixed(0)}%
        </strong>
        <small>
          <Pill tone={posTone}>● {view.position_band.label}</Pill>
        </small>
      </Card>
      <Card icon={<GitBranch size={18} />} label="Developing Fractal">
        <strong>{view.developing_fractal ? view.developing_fractal.label : `No developing ${view.fractal_kind}`}</strong>
        <small>
          {view.developing_fractal ? fmtPrice(view.developing_fractal.price, digits) : '—'} &nbsp;|&nbsp;{' '}
          <b className={view.evidence_score >= 70 ? 'up' : view.evidence_score >= 50 ? 'amber' : 'mst-muted'}>Score {view.evidence_score}</b>
        </small>
      </Card>
      <Card icon={<ShieldCheck size={18} />} label="Range Quality">
        {core.quality != null ? (
          <>
            <strong className={core.quality >= 75 ? 'up' : core.quality >= 55 ? 'amber' : 'down'}>{core.quality} / 100</strong>
            <small className="mst-kv">
              <span>Range Age:</span> <b>{core.age_weeks} weeks</b>
              <span>False Breakouts:</span> <b>{core.false_breakouts}</b>
              <span>Reliability:</span> <b className={core.reliability === 'HIGH' ? 'up' : core.reliability === 'MEDIUM' ? 'amber' : 'down'}>{core.reliability}</b>
            </small>
          </>
        ) : (
          <>
            <strong className="mst-muted">—</strong>
            <small>Quality applies to validated ranges only</small>
          </>
        )}
      </Card>
    </section>
  );
}

export function BoundaryDetails({ core, digits }: { core: RangeCore; digits: number }) {
  const zone = (z: [number, number] | null, fallback: number) =>
    z ? `${fmtPrice(z[0], digits)} – ${fmtPrice(z[1], digits)}` : fmtPrice(fallback, digits);
  return (
    <section className="mst-card mst-panel">
      <h3>
        <CircleDot size={15} /> Boundary Details (Weekly)
      </h3>
      <table className="mst-kv-table">
        <thead>
          <tr>
            <th>Parameter</th>
            <th>Upper Range</th>
            <th>Lower Range</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Fractal Cluster</td>
            <td>{zone(core.high_zone, core.range_high)}</td>
            <td>{zone(core.low_zone, core.range_low)}</td>
          </tr>
          <tr>
            <td>Touches (Fractals)</td>
            <td>{core.touches_high}</td>
            <td>{core.touches_low}</td>
          </tr>
          <tr>
            <td>Last Touch</td>
            <td>{fmtDate(core.last_touch_high)}</td>
            <td>{fmtDate(core.last_touch_low)}</td>
          </tr>
          <tr>
            <td>Range Width</td>
            <td colSpan={2}>
              {fmtPrice(core.width, digits)}
              {core.width_atr != null ? ` (${core.width_atr.toFixed(2)} ATR)` : ''}
            </td>
          </tr>
          <tr>
            <td>Range Age</td>
            <td colSpan={2}>{core.age_weeks} weeks</td>
          </tr>
          <tr>
            <td>Range State</td>
            <td colSpan={2}>{core.state ? <Pill tone={stateTone(core.state.key)}>{core.state.label.toUpperCase()}</Pill> : <span className="mst-muted">No validated range</span>}</td>
          </tr>
          <tr>
            <td>False Breakouts</td>
            <td colSpan={2}>{core.false_breakouts}</td>
          </tr>
          <tr>
            <td>Midpoint</td>
            <td colSpan={2}>{fmtPrice(core.midpoint, digits)}</td>
          </tr>
        </tbody>
      </table>
    </section>
  );
}

export function DevelopingFractalPanel({ view, digits }: { view: RangeView; digits: number }) {
  const dev = view.developing_fractal;
  return (
    <section className="mst-card mst-panel">
      <h3>
        <Search size={15} /> Developing Fractal ({view.fractal_kind})
      </h3>
      <div className="mst-fractal-head">
        <strong>
          <Search size={17} /> {dev ? dev.label : `No developing ${view.fractal_kind}`}
        </strong>
        <span>
          Evidence Score
          <b>{view.evidence_score} / 100</b>
        </span>
      </div>
      <div className="mst-detail">
        <span>Candidate Price</span>
        <b>{dev ? fmtPrice(dev.price, digits) : '—'}</b>
      </div>
      <div className="mst-detail">
        <span>Location</span>
        <b>{dev ? dev.location : `${view.position_band.label} (${view.position.toFixed(0)}%)`}</b>
      </div>
      {dev ? (
        <div className="mst-detail">
          <span>Confirmation</span>
          <b>
            {dev.bars_to_confirm} closed week{dev.bars_to_confirm === 1 ? '' : 's'} pending
          </b>
        </div>
      ) : null}
      <div className="mst-evidence">
        <span>Evidence</span>
        <ul>
          {view.evidence.map((e) => (
            <li key={e.key} className={e.met ? 'is-met' : ''}>
              {e.met ? <Check size={12} /> : <Circle size={11} />}
              {e.label}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

export function MtfAlignment({ view }: { view: RangeView }) {
  return (
    <section className="mst-card mst-panel">
      <h3>
        <Layers3 size={15} /> MTF Alignment
      </h3>
      <table className="mst-mtf">
        <thead>
          <tr>
            <th>TF</th>
            <th>Structure</th>
            <th>Channel</th>
            <th>Signal</th>
          </tr>
        </thead>
        <tbody>
          {view.mtf.map((m) => (
            <tr key={m.timeframe}>
              <td>
                <b>{m.timeframe}</b>
              </td>
              <td>
                <Pill tone={regimeTone(m.structure.key === 'RANGE' ? 'NEUTRAL' : m.structure.key)}>{m.structure.label}</Pill>
              </td>
              <td className="mst-mtf-ch">
                {m.channel === 'Ascending' ? <ArrowUpRight size={13} /> : m.channel === 'Descending' ? <ArrowDownRight size={13} /> : m.channel === 'Sideways' ? <ArrowLeftRight size={13} /> : null}
                {m.channel}
              </td>
              <td className={`mst-signal is-${m.signal.tone}`}>
                <i />
                {m.signal.label}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

export function HypothesisPanel({ view }: { view: RangeView }) {
  const h = view.hypotheses;
  const tone = (b: string) => (b === 'STRONG' ? 'green' : b === 'MODERATE' ? 'amber' : 'red');
  return (
    <section className="mst-card mst-panel">
      <h3>
        <Gauge size={15} /> Hypothesis Analysis
      </h3>
      {h ? (
        <div className="mst-hyp">
          <div className="mst-hyp-box is-rev">
            <div>
              <b>
                Range Reversal {h.reversal.direction === 'UP' ? '↑' : '↓'}
              </b>
              <Pill tone={tone(h.reversal.band.key)}>{h.reversal.band.label.toUpperCase()}</Pill>
            </div>
            <span>
              Evidence Score <strong>{h.reversal.score} / 100</strong>
            </span>
          </div>
          <div className="mst-hyp-box is-brk">
            <div>
              <b>
                Range Breakout {h.breakout.direction === 'UP' ? '↑' : '↓'}
              </b>
              <Pill tone={tone(h.breakout.band.key)}>{h.breakout.band.label.toUpperCase()}</Pill>
            </div>
            <span>
              Evidence Score <strong>{h.breakout.score} / 100</strong>
            </span>
          </div>
        </div>
      ) : (
        <p className="mst-note">Range hypotheses apply only while a validated weekly range is active.</p>
      )}
    </section>
  );
}

export function DecisionPanel({ view }: { view: RangeView }) {
  const d = view.decision;
  const tone = d.key === 'ALERT' ? 'red' : d.key === 'NO_RANGE' || d.key === 'IDLE' ? 'gray' : d.direction === 'DOWN' ? 'red' : 'green';
  return (
    <section className="mst-card mst-panel mst-decision">
      <h3>
        <Crosshair size={15} /> Autonomous Decision
      </h3>
      <div className={`mst-decision-box is-${tone}`}>
        <span className="mst-decision-icon" aria-hidden>
          {d.direction === 'DOWN' ? <ArrowDownRight size={18} /> : d.direction === 'UP' ? <ArrowUpRight size={18} /> : <CircleDot size={18} />}
        </span>
        <div>
          <strong>{d.title}</strong>
          <span>{d.subtitle}</span>
        </div>
        <Info size={15} className="mst-decision-info" aria-label="Analysis only — never initiates execution" />
      </div>
      <p className="mst-note">{d.narrative}</p>
      <h4>Workflow State</h4>
      <ul className="mst-workflow">
        {view.workflow.map((w) => (
          <li key={w.label} className={w.done ? 'is-done' : ''}>
            <span className="mst-wf-dot">{w.done ? <Check size={11} /> : null}</span>
            {w.label}
            <span className="mst-wf-end">{w.done ? <Check size={11} /> : <Circle size={10} />}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

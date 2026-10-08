import type { CSSProperties, ReactNode } from 'react';
import {
  BarChart3,
  Ban,
  Briefcase,
  CircleCheck,
  Database,
  Layers,
  Lightbulb,
  LineChart,
  ScanSearch,
  ShieldCheck,
  TrendingUp,
} from 'lucide-react';
import { pretty, stageLines, tone } from '../format';
import type { StageKey, StageSummary } from '../types';

/** Short card titles, matching the stage dashboard. The detail header keeps the full stage name. */
const CARD_LABEL: Record<StageKey, string> = {
  MARKET_DATA: 'Market Data',
  INTELLIGENCE: 'Intelligence',
  SCANNER: 'Scanner',
  STRUCTURE: 'Structure',
  CHANNEL: 'Channel',
  OPPORTUNITY: 'Opportunity',
  CONFIRMATION: 'Confirmation',
  RISK: 'Risk & Portfolio',
  EXECUTION: 'Execution',
  MANAGEMENT: 'Management',
  LEARNING: 'Performance & Learning',
};

export const STAGE_ICON: Record<StageKey, ReactNode> = {
  MARKET_DATA: <Database size={17} />,
  INTELLIGENCE: <TrendingUp size={17} />,
  SCANNER: <ScanSearch size={17} />,
  STRUCTURE: <Layers size={17} />,
  CHANNEL: <LineChart size={17} />,
  OPPORTUNITY: <Lightbulb size={17} />,
  CONFIRMATION: <CircleCheck size={17} />,
  RISK: <ShieldCheck size={17} />,
  EXECUTION: <Ban size={17} />,
  MANAGEMENT: <Briefcase size={17} />,
  LEARNING: <BarChart3 size={17} />,
};

export function StagePipeline({
  stages,
  selected,
  onSelect,
  loading,
}: {
  stages: StageSummary[];
  selected: StageKey;
  onSelect: (k: StageKey) => void;
  loading: boolean;
}) {
  if (loading && !stages.length) {
    return (
      <section className="ae-pipeline" aria-busy="true">
        {Array.from({ length: 11 }, (_, i) => (
          <div key={i} className="ae-stage is-skeleton">
            <span className="ae-skel" style={{ width: '60%' }} />
            <span className="ae-skel" style={{ width: '40%' }} />
            <span className="ae-skel" style={{ width: '80%' }} />
          </div>
        ))}
      </section>
    );
  }
  return (
    <section className="ae-pipeline" aria-label="Autonomous pipeline stages">
      {stages.map((s) => {
        const [a, b] = stageLines(s);
        return (
          <button
            type="button"
            key={s.key}
            className={`ae-stage ${selected === s.key ? 'is-selected' : ''} ${s.stale ? 'is-stale' : ''}`}
            style={{ '--stage': s.color } as CSSProperties}
            onClick={() => onSelect(s.key)}
            aria-pressed={selected === s.key}
            title={[s.current_operation, s.next_operation ? `Next: ${s.next_operation}` : '', ...s.blockers.slice(0, 3)].filter(Boolean).join('\n')}
          >
            <span className="ae-stage-icon" aria-hidden>
              <span className="ae-stage-num">{s.number}</span>
              {STAGE_ICON[s.key]}
            </span>
            <strong>{CARD_LABEL[s.key]}</strong>
            <span className={`ae-badge is-${tone(s.status)}`}>{s.stale ? 'Stale' : pretty(s.status)}</span>
            <span className="ae-stage-line">{a}</span>
            <span className="ae-stage-sub">{b}</span>
          </button>
        );
      })}
    </section>
  );
}

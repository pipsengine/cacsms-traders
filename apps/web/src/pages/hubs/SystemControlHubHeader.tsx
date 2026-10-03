import { BarChart3, ChevronRight, RefreshCcw, Settings, ShieldCheck } from 'lucide-react';
import type { Health, Summary } from '../../types';

export function SystemControlHubHeader({
  health,
  summary,
  enginesLabel,
}: {
  health: Health | null;
  summary: Summary | null;
  enginesLabel: string;
}) {
  const apiOk = health?.api === 'HEALTHY';
  const mode = (summary?.mode ?? 'ANALYSIS_ONLY').replaceAll('_', ' ');
  const enginesStopped = enginesLabel.toLowerCase().includes('stopped') || enginesLabel.toLowerCase().includes('degraded');

  return (
    <>
      <div className="sc-breadcrumb">
        System <ChevronRight size={14} /> <b>System Control</b>
      </div>
      <div className="sc-hero">
        <div className="sc-heroLeft">
          <div className="sc-heroIcon">
            <Settings />
          </div>
          <div>
            <h1>System Control</h1>
            <p>Health, connections, operating mode, engines, configuration and audit.</p>
          </div>
        </div>
        <div className="sc-summaryStrip">
          <div>
            <i className={`sc-dot ${apiOk ? 'green' : 'red'}`} />
            <span>
              System Health
              <b className={apiOk ? 'sc-ok' : 'sc-bad'}>{apiOk ? 'Healthy' : 'Degraded'}</b>
            </span>
          </div>
          <div>
            <RefreshCcw />
            <span>
              Operating Mode
              <b>{mode}</b>
            </span>
          </div>
          <div>
            <BarChart3 />
            <span>
              Engines
              <b className={enginesStopped ? 'sc-bad' : 'sc-ok'}>{enginesStopped ? 'Stopped' : 'Ready'}</b>
            </span>
          </div>
          <div>
            <ShieldCheck />
            <span>
              Configuration
              <b className="sc-ok">Synced</b>
            </span>
          </div>
        </div>
      </div>
    </>
  );
}

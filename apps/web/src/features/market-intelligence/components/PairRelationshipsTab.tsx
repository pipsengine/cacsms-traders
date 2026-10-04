import { useMemo, useState } from 'react';
import { ArrowDown, ArrowUp, Network, Search } from 'lucide-react';
import { marketIntelligenceApi } from '../api';
import { usePollingAsync } from '../hooks/useMarketIntelligence';
import type { PairRelationship, RelationshipKey } from '../types';
import { IntelBadge, SI_CURRENCIES, ageText, signed } from '../intelUi';
import { CurrencyFlag } from './CurrencyFlag';
import { EmptyState } from './EmptyState';
import { MatrixBlockingState, MatrixStatusBanners } from './MatrixPanelStates';
import { fmtUtc } from './TimeSeriesChart';

const POLL_MS = 1000;
const TF_ORDER = ['YTD', 'Q', 'MN', 'W', 'D1', 'H8', 'H1', 'M15', 'M5', 'M1'];
const REL_ORDER: RelationshipKey[] = ['STRONG_DIVERGENCE', 'DIVERGENCE', 'MODERATE', 'BALANCED'];

type SortKey = 'pair' | 'base_strength' | 'quote_strength' | 'differential' | 'abs_differential' | 'dynamics' | 'alignment';

const SORTERS: Record<SortKey, (r: PairRelationship) => number | string> = {
  pair: (r) => r.pair,
  base_strength: (r) => r.base_strength,
  quote_strength: (r) => r.quote_strength,
  differential: (r) => r.differential,
  abs_differential: (r) => r.abs_differential,
  dynamics: (r) => (r.dynamics.change === null ? -Infinity : Math.abs(r.differential) - Math.abs(r.dynamics.previous ?? 0)),
  alignment: (r) => r.alignment.pct,
};

function StrengthValue({ v, tone }: { v: number; tone: string }) {
  return (
    <span className={`si-str si-str--${tone}`}>
      <span className="si-str-bar">
        <i style={{ width: `${Math.max(2, Math.min(100, v))}%` }} />
      </span>
      {v.toFixed(1)}
    </span>
  );
}

export function DifferentialBar({ value, max = 60 }: { value: number; max?: number }) {
  const w = Math.min(50, (Math.abs(value) / max) * 50);
  return (
    <span className="si-diff">
      <span className="si-diff-track">
        <span className="si-diff-mid" />
        <i className={value >= 0 ? 'base' : 'quote'} style={value >= 0 ? { left: '50%', width: `${w}%` } : { right: '50%', width: `${w}%` }} />
      </span>
      <b>{signed(value)}</b>
    </span>
  );
}

export function AlignmentDots({ timeframes, eps }: { timeframes: Record<string, number>; eps: number }) {
  return (
    <span className="si-dots" aria-hidden>
      {TF_ORDER.map((tf) => {
        const d = timeframes[tf];
        const cls = d === undefined ? 'na' : d > eps ? 'base' : d < -eps ? 'quote' : 'flat';
        return <i key={tf} className={cls} title={d === undefined ? `${tf}: no data` : `${tf}: ${signed(d)}`} />;
      })}
    </span>
  );
}

export function PairRelationshipsTab({ enabled, onAnalyse }: { enabled: boolean; onAnalyse: (pair: string) => void }) {
  const q = usePollingAsync(marketIntelligenceApi.pairRelationships, [], { enabled, intervalMs: POLL_MS });
  const [search, setSearch] = useState('');
  const [currency, setCurrency] = useState('ALL');
  const [rel, setRel] = useState<RelationshipKey | 'ALL'>('ALL');
  const [dyn, setDyn] = useState('ALL');
  const [align, setAlign] = useState('ALL');
  const [sortKey, setSortKey] = useState<SortKey>('abs_differential');
  const [asc, setAsc] = useState(false);
  const data = q.data;

  const rows = useMemo(() => {
    if (!data) return [];
    const s = search.trim().toUpperCase().replace('/', '');
    const out = data.rows.filter(
      (r) =>
        (!s || r.pair.includes(s)) &&
        (currency === 'ALL' || r.base === currency || r.quote === currency) &&
        (rel === 'ALL' || r.relationship.key === rel) &&
        (dyn === 'ALL' || r.dynamics.key === dyn) &&
        (align === 'ALL' || r.alignment.key === align),
    );
    const f = SORTERS[sortKey];
    return out.sort((a, b) => {
      const va = f(a);
      const vb = f(b);
      const c = typeof va === 'string' ? va.localeCompare(vb as string) : (va as number) - (vb as number);
      return asc ? c : -c;
    });
  }, [data, search, currency, rel, dyn, align, sortKey, asc]);

  const sortBy = (k: SortKey) => {
    setAsc((a) => (k === sortKey ? !a : k === 'pair'));
    setSortKey(k);
  };
  const th = (k: SortKey, label: string, className?: string) => (
    <th className={className}>
      <button type="button" className={`mi-th-sort ${sortKey === k ? 'active' : ''}`} onClick={() => sortBy(k)}>
        {label}
        {sortKey === k ? asc ? <ArrowUp size={11} /> : <ArrowDown size={11} /> : null}
      </button>
    </th>
  );

  const counts = data?.summary.relationship_counts;
  const labels = Object.fromEntries((data?.thresholds.relationship ?? []).map((t) => [t.key, t]));
  const refAge = ageText(data?.meta.reference_age_minutes);

  return (
    <section className="mi-card si-intel-card">
      <header className="mi-matrix-card-head">
        <div className="si-card-head">
          <span className="si-icon-block" aria-hidden>
            <Network size={16} />
          </span>
          <div>
            <h2>Pair relationships — 28-pair FX basket</h2>
            <p className="mi-matrix-sub">
              Base vs quote strength differentials from the same scores as the Strength Matrix. Pair intelligence only — not
              a trade signal.
            </p>
          </div>
        </div>
        <div className="si-intel-controls">
          <label className="si-search">
            <Search size={14} aria-hidden />
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search pair" aria-label="Search pair" />
          </label>
          <label>
            Currency
            <select value={currency} onChange={(e) => setCurrency(e.target.value)} aria-label="Currency filter">
              <option value="ALL">All</option>
              {SI_CURRENCIES.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </label>
          <label>
            Dynamics
            <select value={dyn} onChange={(e) => setDyn(e.target.value)} aria-label="Dynamics filter">
              <option value="ALL">All</option>
              <option value="EXPANDING">Expanding</option>
              <option value="CONTRACTING">Contracting</option>
              <option value="REVERSING">Reversing</option>
              <option value="STABLE">Stable</option>
              <option value="NO_HISTORY">Awaiting history</option>
            </select>
          </label>
          <label>
            Alignment
            <select value={align} onChange={(e) => setAlign(e.target.value)} aria-label="Alignment filter">
              <option value="ALL">All</option>
              <option value="ALIGNED">Aligned</option>
              <option value="PARTIAL">Partially aligned</option>
              <option value="CONFLICTED">Conflicted</option>
              <option value="NEUTRAL">No clear direction</option>
            </select>
          </label>
        </div>
      </header>

      {!data ? (
        <MatrixBlockingState loading={q.loading || enabled} error={q.error} onRetry={q.refresh} label="pair relationships" />
      ) : (
        <>
          <div className="si-intel-banners">
            <MatrixStatusBanners meta={data.meta} error={q.error} hasScores onRetry={q.refresh} />
          </div>
          <div className="si-rel-summary" role="group" aria-label="Relationship classes">
            <button type="button" className={rel === 'ALL' ? 'active' : ''} onClick={() => setRel('ALL')}>
              <strong>{data.rows.length}</strong>
              <span>All pairs</span>
            </button>
            {REL_ORDER.map((k) => (
              <button
                key={k}
                type="button"
                className={`si-rel-${k.toLowerCase()} ${rel === k ? 'active' : ''}`}
                onClick={() => setRel(rel === k ? 'ALL' : k)}
              >
                <strong>{counts?.[k] ?? 0}</strong>
                <span>
                  {labels[k]?.label ?? k}
                  <em>{k === 'BALANCED' ? `< ${labels.MODERATE?.min ?? ''}` : `≥ ${labels[k]?.min ?? ''}`} pts</em>
                </span>
              </button>
            ))}
          </div>

          <div className={`si-table-wrap ${data.meta.stale ? 'is-stale' : ''}`}>
            {rows.length ? (
              <table className="si-table si-rel-table">
                <thead>
                  <tr>
                    <th className="num">#</th>
                    {th('pair', 'Pair', 'left')}
                    {th('base_strength', 'Base strength')}
                    {th('quote_strength', 'Quote strength')}
                    {th('differential', 'Differential')}
                    {th('abs_differential', '|Diff|')}
                    <th>Relationship</th>
                    {th('dynamics', 'Dynamics')}
                    {th('alignment', 'Alignment')}
                    <th aria-label="Analyse" />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.pair}>
                      <td className="num muted">{r.rank}</td>
                      <td className="left">
                        <span className="si-pair">
                          <CurrencyFlag code={r.base} size={16} />
                          <CurrencyFlag code={r.quote} size={16} />
                          <strong>
                            {r.base}/{r.quote}
                          </strong>
                        </span>
                      </td>
                      <td>
                        <StrengthValue v={r.base_strength} tone={r.base_class.tone} />
                      </td>
                      <td>
                        <StrengthValue v={r.quote_strength} tone={r.quote_class.tone} />
                      </td>
                      <td>
                        <DifferentialBar value={r.differential} />
                      </td>
                      <td className="num strong">{r.abs_differential.toFixed(1)}</td>
                      <td>
                        <IntelBadge k={r.relationship.key} label={r.relationship.label} />
                      </td>
                      <td>
                        <span className="si-dyn">
                          <IntelBadge k={r.dynamics.key} label={r.dynamics.label} />
                          {r.dynamics.change !== null ? <small>{signed(r.dynamics.change)}</small> : null}
                        </span>
                      </td>
                      <td>
                        <span className="si-align" title={`${r.alignment.label}: ${r.alignment.aligned} of ${r.alignment.total} timeframes`}>
                          <AlignmentDots timeframes={r.timeframes} eps={data.thresholds.alignment_epsilon} />
                          <small>
                            {r.alignment.aligned}/{r.alignment.total}
                          </small>
                        </span>
                      </td>
                      <td>
                        <button type="button" className="si-link-btn" onClick={() => onAnalyse(r.pair)}>
                          Analyse
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <EmptyState title="No pairs match" body="Adjust the filters to see more pairs." />
            )}
          </div>

          <footer className="si-matrix-footer">
            <span className="si-footer-item">
              <span className="si-key base" /> Base stronger <span className="si-key quote" /> Quote stronger
            </span>
            <span className="si-footer-item">
              Dynamics vs{' '}
              <strong>
                {data.meta.reference_as_of ? `${fmtUtc(data.meta.reference_as_of)} snapshot (${refAge} ago)` : 'no reference snapshot yet'}
              </strong>
            </span>
            <span className="si-footer-item">
              Pairs <strong>{data.meta.pairs_available}/28</strong>
            </span>
            <span className="si-footer-item">Alignment dots: YTD → M1</span>
          </footer>
        </>
      )}
    </section>
  );
}

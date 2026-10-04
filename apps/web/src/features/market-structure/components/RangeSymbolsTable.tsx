import { useMemo, useState } from 'react';
import { Search } from 'lucide-react';
import { InstrumentIcon } from '../../market-scanner/components/InstrumentIcon';
import { fmtPrice, priceDigits } from '../../market-scanner/format';
import { Pill, regimeTone } from './RangePanels';
import type { RangeCounts, RangeRow } from '../types';

type Filter = 'ranging' | 'near_upper' | 'near_lower' | 'breakout_risk' | 'all';

const FILTERS: { id: Filter; label: string }[] = [
  { id: 'ranging', label: 'Ranging Symbols' },
  { id: 'near_upper', label: 'Near Upper Range' },
  { id: 'near_lower', label: 'Near Lower Range' },
  { id: 'breakout_risk', label: 'Breakout Risk' },
  { id: 'all', label: 'All Symbols' },
];

const short = (s: string | null | undefined) =>
  !s ? '—' : s === 'Ranging' ? 'Range' : s === 'Bullish' ? 'Bull' : s === 'Bearish' ? 'Bear' : s === 'Transitional' ? 'Trans' : s;

function mtfTone(s: string | null | undefined) {
  return s === 'Bullish' ? 'up' : s === 'Bearish' ? 'down' : '';
}

export function RangeSymbolsTable({
  rows,
  counts,
  extremePct,
  breakoutMin,
  selected,
  onView,
}: {
  rows: RangeRow[];
  counts: RangeCounts | null;
  extremePct: number;
  breakoutMin: number;
  selected: string;
  onView: (symbol: string) => void;
}) {
  const [filter, setFilter] = useState<Filter>('ranging');
  const [q, setQ] = useState('');
  const [asset, setAsset] = useState('ALL');
  const [regime, setRegime] = useState('ALL');

  const visible = useMemo(() => {
    const match = (r: RangeRow) => {
      const ranging = r.available && r.ranging;
      switch (filter) {
        case 'ranging':
          return ranging;
        case 'near_upper':
          return ranging && (r.position ?? 0) >= 100 - extremePct;
        case 'near_lower':
          return ranging && (r.position ?? 100) <= extremePct;
        case 'breakout_risk':
          return ranging && (r.state?.key === 'BREAKOUT_THREAT' || (r.breakout_score ?? 0) >= breakoutMin);
        default:
          return true;
      }
    };
    return rows
      .filter(match)
      .filter((r) => !q || r.symbol.includes(q.trim().toUpperCase()))
      .filter((r) => asset === 'ALL' || r.asset === asset)
      .filter((r) => regime === 'ALL' || r.regime.key === regime)
      .sort((a, b) => (b.evidence_score ?? -1) - (a.evidence_score ?? -1) || a.symbol.localeCompare(b.symbol));
  }, [rows, filter, q, asset, regime, extremePct, breakoutMin]);

  return (
    <section className="mst-card mst-symbols">
      <div className="mst-tools">
        <div className="mst-filters" role="tablist">
          {FILTERS.map((f) => (
            <button key={f.id} role="tab" aria-selected={filter === f.id} className={filter === f.id ? 'is-on' : ''} onClick={() => setFilter(f.id)}>
              {f.label} ({counts?.[f.id] ?? 0})
            </button>
          ))}
        </div>
        <div className="mst-search">
          <label className="mst-search-input">
            <Search size={14} aria-hidden />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search symbol..." aria-label="Search symbol" />
          </label>
          <select value={asset} onChange={(e) => setAsset(e.target.value)} aria-label="Asset class">
            <option value="ALL">All Assets</option>
            <option value="Forex">Forex</option>
            <option value="Commodity">Commodity</option>
          </select>
          <select value={regime} onChange={(e) => setRegime(e.target.value)} aria-label="Weekly regime">
            <option value="ALL">W Any Regime</option>
            <option value="RANGING">W Ranging</option>
            <option value="BULLISH">W Bullish</option>
            <option value="BEARISH">W Bearish</option>
            <option value="TRANSITIONAL">W Transitional</option>
          </select>
        </div>
      </div>
      <div className="mst-table-wrap">
        <table className="mst-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Symbol</th>
              <th>Asset</th>
              <th>W Regime</th>
              <th className="num">Range High</th>
              <th className="num">Range Low</th>
              <th className="num">Current Price</th>
              <th>Position</th>
              <th>Developing Fractal</th>
              <th className="center">Score</th>
              <th>MTF Alignment</th>
              <th>Hypothesis</th>
              <th className="center">Action</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((r, i) => {
              const d = priceDigits({ digits: r.digits ?? undefined, symbol: r.symbol, quote: r.quote });
              const pos = r.position ?? null;
              const posCls = pos == null ? '' : pos <= extremePct ? 'is-low' : pos >= 100 - extremePct ? 'is-high' : 'is-mid';
              const hyp = r.hypothesis;
              const hypTone = hyp?.key === 'REVERSAL' ? (hyp.direction === 'UP' ? 'green' : 'red') : hyp?.key === 'BREAKOUT' ? 'amber' : 'gray';
              const sc = r.evidence_score;
              return (
                <tr key={r.symbol} className={selected === r.symbol ? 'is-selected' : ''}>
                  <td className="mst-muted">{i + 1}</td>
                  <td>
                    <span className="mst-sym">
                      <InstrumentIcon base={r.base} quote={r.quote} size="sm" />
                      <b>{r.symbol}</b>
                    </span>
                  </td>
                  <td className="mst-muted">{r.asset}</td>
                  <td>
                    <Pill tone={regimeTone(r.regime.key)}>{r.regime.label.toUpperCase()}</Pill>
                  </td>
                  <td className="num">{r.available ? fmtPrice(r.range_high, d) : '—'}</td>
                  <td className="num">{r.available ? fmtPrice(r.range_low, d) : '—'}</td>
                  <td className="num">
                    <b>{fmtPrice(r.price, d)}</b>
                    <small className={r.change_pct == null ? '' : r.change_pct >= 0 ? 'up' : 'down'}>
                      {r.change_pct != null ? `${r.change_pct > 0 ? '+' : ''}${r.change_pct.toFixed(2)}%` : '—'}
                    </small>
                  </td>
                  <td>
                    {pos != null ? (
                      <span className={`mst-posc ${posCls}`}>
                        <b>{pos.toFixed(0)}%</b>
                        <span className="mst-meter">
                          <i style={{ width: `${Math.max(0, Math.min(100, pos))}%` }} />
                        </span>
                        <small>{r.position_band?.label}</small>
                      </span>
                    ) : (
                      <span className="mst-muted">{r.unavailable_reason ?? '—'}</span>
                    )}
                  </td>
                  <td>
                    {r.developing_fractal ? (
                      <span className="mst-devf">
                        <b className={r.developing_fractal.kind === 'WFL' ? 'up' : 'down'}>
                          {r.developing_fractal.kind} ({sc}%)
                        </b>
                        <small>{fmtPrice(r.developing_fractal.price, d)}</small>
                      </span>
                    ) : (
                      <span className="mst-muted">{r.available ? `No ${r.fractal_kind}` : '—'}</span>
                    )}
                  </td>
                  <td className="center">
                    {sc != null ? <span className={`mst-score ${sc >= 70 ? 'is-green' : sc >= 50 ? 'is-amber' : 'is-gray'}`}>{sc}</span> : '—'}
                  </td>
                  <td className="mst-mtfs">
                    {r.mtf ? (
                      <>
                        W: <b className={mtfTone(r.mtf.W)}>{short(r.mtf.W)}</b> | D1: <b className={mtfTone(r.mtf.D1)}>{short(r.mtf.D1)}</b> | H8:{' '}
                        <b className={mtfTone(r.mtf.H8)}>{short(r.mtf.H8)}</b>
                      </>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td>{hyp ? <Pill tone={hypTone}>{hyp.label}</Pill> : '—'}</td>
                  <td className="center">
                    <button className="mst-view" onClick={() => onView(r.symbol)} disabled={!r.available}>
                      View
                    </button>
                  </td>
                </tr>
              );
            })}
            {!visible.length ? (
              <tr>
                <td colSpan={13} className="mst-empty">
                  No instruments match this filter in the current cycle.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}

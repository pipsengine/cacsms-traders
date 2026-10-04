import { useEffect, useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight, Star } from 'lucide-react';
import { InstrumentIcon } from './InstrumentIcon';
import { CHANNEL_CLASS, STATUS_CLASS, fmtPct, fmtPrice, priceDigits, tone } from '../format';
import type { ScannerCounts, ScannerRow, ScannerStatusKey } from '../types';

export type StatusFilter = 'ALL' | ScannerStatusKey;

const TABS: { id: StatusFilter; label: string }[] = [
  { id: 'ALL', label: 'All' },
  { id: 'HIGH_INSPECTION', label: 'High Inspection' },
  { id: 'WATCHING', label: 'Watching' },
  { id: 'NEUTRAL', label: 'Neutral' },
  { id: 'EXCLUDED', label: 'Excluded' },
];
const PAGE_SIZES = [10, 12, 24, 50];
const defaultPageSize = () => (typeof window !== 'undefined' && window.innerHeight < 800 ? 10 : 12);

export function StrengthMeter({ row }: { row: ScannerRow }) {
  const s = row.strength;
  if (!s) return <span className="ms-muted">—</span>;
  if (s.differential === null) {
    const q = s.quote_score;
    return (
      <span className="ms-strength" title={`${row.quote} strength ${q?.toFixed(1) ?? '—'}/100 (${row.base} not in currency basket)`}>
        <span className="ms-strength-track is-single">
          <span className="ms-strength-fill is-quote" style={{ width: `${q ?? 0}%` }} />
        </span>
        <small>
          {row.quote} {q !== null ? q.toFixed(0) : '—'}
        </small>
      </span>
    );
  }
  const d = s.differential;
  const w = Math.min(50, (Math.abs(d) / 50) * 50);
  return (
    <span
      className="ms-strength"
      title={`${row.base} ${s.base_score?.toFixed(1)} vs ${row.quote} ${s.quote_score?.toFixed(1)} — differential ${d.toFixed(1)}`}
    >
      <span className="ms-strength-track">
        <span className={`ms-strength-fill ${d >= 0 ? 'is-base' : 'is-quote-neg'}`} style={d >= 0 ? { left: '50%', width: `${w}%` } : { right: '50%', width: `${w}%` }} />
        <i className="ms-strength-mid" />
      </span>
      <small className={tone(d)}>{d > 0 ? '+' : ''}{d.toFixed(1)}</small>
    </span>
  );
}

export function VolatilityGlyph({ k }: { k?: string }) {
  const level = k === 'HIGH' ? 3 : k === 'NORMAL' ? 2 : k === 'LOW' ? 1 : 0;
  return (
    <span className={`ms-vol-glyph is-l${level}`} aria-hidden>
      <i />
      <i />
      <i />
    </span>
  );
}

function StructureCell({ row }: { row: ScannerRow }) {
  const st = row.structure;
  if (!st || st.key === 'INSUFFICIENT') return <span className="ms-muted">—</span>;
  const cls = st.key === 'BULLISH' ? 'up' : st.key === 'BEARISH' ? 'down' : 'flat';
  return (
    <span className={`ms-structure ${cls}`} title={st.event?.label ?? undefined}>
      {st.label} <small>({st.timeframe})</small>
    </span>
  );
}

export function ScoreBadge({ row, size = 'md' }: { row: Pick<ScannerRow, 'score' | 'status'>; size?: 'md' | 'lg' }) {
  if (row.score === null) return <span className={`ms-score ms-score--${size} is-excluded`}>—</span>;
  return <span className={`ms-score ms-score--${size} ${STATUS_CLASS[row.status.key]}`}>{row.score}</span>;
}

export function StatusPill({ status }: { status: ScannerRow['status'] }) {
  return <span className={`ms-status-pill ${STATUS_CLASS[status.key]}`}>{status.label}</span>;
}

export function ChannelPill({ channel }: { channel?: ScannerRow['channel'] }) {
  if (!channel || channel.key === 'INSUFFICIENT') return <span className="ms-muted">—</span>;
  return <span className={`ms-channel-pill ${CHANNEL_CLASS[channel.key] ?? ''}`}>{channel.label}</span>;
}

function pageList(page: number, pages: number): (number | '…')[] {
  if (pages <= 7) return Array.from({ length: pages }, (_, i) => i + 1);
  const out: (number | '…')[] = [1];
  const lo = Math.max(2, page - 1);
  const hi = Math.min(pages - 1, page + 1);
  if (lo > 2) out.push('…');
  for (let i = lo; i <= hi; i++) out.push(i);
  if (hi < pages - 1) out.push('…');
  out.push(pages);
  return out;
}

export function ScannerTable({
  rows,
  counts,
  selected,
  onSelect,
  starred,
  onToggleStar,
  stale,
}: {
  rows: ScannerRow[];
  counts: ScannerCounts | null;
  selected: string | null;
  onSelect: (symbol: string) => void;
  starred: Set<string>;
  onToggleStar: (symbol: string) => void;
  stale: boolean;
}) {
  const [filter, setFilter] = useState<StatusFilter>('ALL');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(defaultPageSize);

  const filtered = useMemo(() => (filter === 'ALL' ? rows : rows.filter((r) => r.status.key === filter)), [rows, filter]);
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  useEffect(() => setPage((p) => Math.min(p, pages)), [pages]);
  const start = (page - 1) * pageSize;
  const visible = filtered.slice(start, start + pageSize);
  const count = (id: StatusFilter) => (id === 'ALL' ? rows.length : counts?.[id] ?? 0);

  return (
    <section className={`ms-card ms-table-card ${stale ? 'is-stale' : ''}`}>
      <div className="ms-tabs" role="tablist" aria-label="Status filter">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={filter === t.id}
            className={`ms-tab ${filter === t.id ? 'is-active' : ''}`}
            onClick={() => {
              setFilter(t.id);
              setPage(1);
            }}
          >
            {t.label} <span className="ms-tab-count">({count(t.id)})</span>
          </button>
        ))}
      </div>

      <div className="ms-table-scroll">
        <table className="ms-table">
          <thead>
            <tr>
              <th className="ms-col-rank">
                <Star size={13} aria-hidden /> #
              </th>
              <th>Symbol</th>
              <th className="num">Price</th>
              <th className="num">24h %</th>
              <th>Strength</th>
              <th>Structure</th>
              <th>Channel</th>
              <th>Volatility</th>
              <th>Status</th>
              <th className="center">Score</th>
              <th>Key Reasons</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((r) => {
              const digits = priceDigits(r);
              const fav = starred.has(r.symbol);
              return (
                <tr
                  key={r.symbol}
                  className={`${selected === r.symbol ? 'is-selected' : ''} ${r.status.key === 'EXCLUDED' ? 'is-excluded' : ''}`}
                  onClick={() => onSelect(r.symbol)}
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      onSelect(r.symbol);
                    }
                  }}
                  aria-selected={selected === r.symbol}
                >
                  <td className="ms-col-rank">
                    <button
                      className={`ms-star ${fav ? 'is-on' : ''}`}
                      aria-label={fav ? `Unstar ${r.symbol}` : `Star ${r.symbol}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        onToggleStar(r.symbol);
                      }}
                    >
                      <Star size={14} />
                    </button>
                    <span>{r.rank}</span>
                  </td>
                  <td>
                    <span className="ms-symbol">
                      <InstrumentIcon base={r.base} quote={r.quote} size="sm" />
                      <strong>{r.symbol}</strong>
                    </span>
                  </td>
                  <td className="num ms-price">{fmtPrice(r.price, digits)}</td>
                  <td className={`num ${tone(r.change_24h_pct)}`}>{fmtPct(r.change_24h_pct)}</td>
                  <td>
                    <StrengthMeter row={r} />
                  </td>
                  <td>
                    <StructureCell row={r} />
                  </td>
                  <td>
                    <ChannelPill channel={r.channel} />
                  </td>
                  <td>
                    {r.volatility && r.volatility.key !== 'INSUFFICIENT' ? (
                      <span className="ms-vol" title={r.volatility.ratio ? `ATR ×${r.volatility.ratio.toFixed(2)} of baseline` : undefined}>
                        <VolatilityGlyph k={r.volatility.key} />
                        {r.volatility.label}
                      </span>
                    ) : (
                      <span className="ms-muted">—</span>
                    )}
                  </td>
                  <td>
                    <StatusPill status={r.status} />
                  </td>
                  <td className="center">
                    <ScoreBadge row={r} />
                  </td>
                  <td className="ms-reasons">
                    {r.reasons.slice(0, 2).map((x) => (
                      <span key={x}>{x}</span>
                    ))}
                  </td>
                </tr>
              );
            })}
            {!visible.length ? (
              <tr>
                <td colSpan={11} className="ms-table-empty">
                  No instruments in this category for the current cycle.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      <footer className="ms-pager">
        <span>
          Showing {filtered.length ? start + 1 : 0} to {Math.min(start + pageSize, filtered.length)} of {filtered.length}{' '}
          instruments
        </span>
        <div className="ms-pages">
          <button aria-label="Previous page" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            <ChevronLeft size={15} />
          </button>
          {pageList(page, pages).map((p, i) =>
            p === '…' ? (
              <span key={`gap-${i}`} className="ms-page-gap">
                …
              </span>
            ) : (
              <button key={p} className={p === page ? 'is-active' : ''} onClick={() => setPage(p)} aria-current={p === page}>
                {p}
              </button>
            ),
          )}
          <button aria-label="Next page" disabled={page >= pages} onClick={() => setPage(page + 1)}>
            <ChevronRight size={15} />
          </button>
        </div>
        <label className="ms-page-size">
          Show
          <select
            value={pageSize}
            onChange={(e) => {
              setPageSize(Number(e.target.value));
              setPage(1);
            }}
          >
            {PAGE_SIZES.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
          per page
        </label>
      </footer>
    </section>
  );
}

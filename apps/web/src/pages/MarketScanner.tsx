import { useCallback, useEffect, useMemo, useState } from 'react';
import { usePollingAsync } from '../features/market-intelligence/hooks/useMarketIntelligence';
import { marketScannerApi } from '../features/market-scanner/api';
import { ScannerHeader } from '../features/market-scanner/components/ScannerHeader';
import { ScannerPipeline } from '../features/market-scanner/components/ScannerPipeline';
import { ScannerKpis } from '../features/market-scanner/components/ScannerKpis';
import { ScannerTable } from '../features/market-scanner/components/ScannerTable';
import { InstrumentPanel } from '../features/market-scanner/components/InstrumentPanel';

const POLL_MS = 2000;
const STAR_KEY = 'ms_starred';

function loadStarred() {
  try {
    return new Set<string>(JSON.parse(localStorage.getItem(STAR_KEY) ?? '[]'));
  } catch {
    return new Set<string>();
  }
}

export function MarketScanner() {
  const [visible, setVisible] = useState(() => typeof document === 'undefined' || document.visibilityState === 'visible');
  useEffect(() => {
    const onVis = () => setVisible(document.visibilityState === 'visible');
    document.addEventListener('visibilitychange', onVis);
    return () => document.removeEventListener('visibilitychange', onVis);
  }, []);

  const loader = useCallback(() => marketScannerApi.scanner(), []);
  const scan = usePollingAsync(loader, [loader], { enabled: visible, intervalMs: POLL_MS });
  const data = scan.data;
  const meta = data?.meta ?? null;
  const rows = data?.rows ?? [];

  const [selected, setSelected] = useState<string | null>(null);
  useEffect(() => {
    if (!selected && rows.length) setSelected(rows[0].symbol);
  }, [rows, selected]);
  const selectedRow = useMemo(() => rows.find((r) => r.symbol === selected) ?? null, [rows, selected]);

  const [starred, setStarred] = useState(loadStarred);
  const toggleStar = (symbol: string) =>
    setStarred((prev) => {
      const next = new Set(prev);
      if (next.has(symbol)) next.delete(symbol);
      else next.add(symbol);
      localStorage.setItem(STAR_KEY, JSON.stringify([...next]));
      return next;
    });

  return (
    <div className="ms-page">
      <ScannerHeader meta={meta} apiError={!!scan.error} />
      <ScannerPipeline meta={meta} counts={data?.counts ?? null} />
      <ScannerKpis meta={meta} counts={data?.counts ?? null} />

      {scan.loading && !data ? (
        <section className="ms-card ms-blocking">
          <span className="ms-spinner" aria-hidden />
          Loading scanner cycle…
        </section>
      ) : scan.error && !data ? (
        <section className="ms-card ms-blocking is-error">
          <strong>Market Scanner unavailable</strong>
          <span>{scan.error}</span>
          <button className="ms-btn" onClick={scan.refresh}>
            Retry
          </button>
        </section>
      ) : !rows.length ? (
        <section className="ms-card ms-blocking">
          <strong>Waiting for the first scanner cycle</strong>
          <span>Instruments appear once closed-bar analysis completes.</span>
        </section>
      ) : (
        <div className="ms-main">
          <ScannerTable
            rows={rows}
            counts={data?.counts ?? null}
            selected={selected}
            onSelect={setSelected}
            starred={starred}
            onToggleStar={toggleStar}
            stale={!!meta?.stale}
          />
          {selectedRow ? (
            <InstrumentPanel
              key={selectedRow.symbol}
              row={selectedRow}
              meta={meta}
              starred={starred.has(selectedRow.symbol)}
              onToggleStar={() => toggleStar(selectedRow.symbol)}
              enabled={visible}
            />
          ) : null}
        </div>
      )}
    </div>
  );
}

import { useCallback, useMemo, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { channelApi } from '../features/channel-intelligence/api';
import { BreakoutRetest } from '../features/channel-intelligence/components/BreakoutRetest';
import { ChannelAnalysis } from '../features/channel-intelligence/components/ChannelAnalysis';
import { CHANNEL_BARS, CHANNEL_TFS } from '../features/channel-intelligence/components/shared';
import { TrendInTrend, titCharts } from '../features/channel-intelligence/components/TrendInTrend';
import type { ChannelTf, EventTf } from '../features/channel-intelligence/types';
import { usePollingAsync } from '../features/market-intelligence/hooks/useMarketIntelligence';
import { InstrumentIcon } from '../features/market-scanner/components/InstrumentIcon';
import { Blocking, rowDigits } from '../features/market-structure/components/StructureUi';
import { localStamp, liveStatus, useCandles, useShortScreen, useVisible } from '../features/market-structure/hooks';

const TABS = [
  { id: 'channels', label: 'Channel Analysis' },
  { id: 'breakout', label: 'Breakout & Retest' },
  { id: 'tit', label: 'Trend-in-Trend' },
];
const SUBTITLE: Record<string, string> = {
  channels: 'Regression channels from yearly to hourly — direction, position, width and multi-timeframe alignment',
  breakout: 'Walk-forward channel breakouts, retests and continuation across W / D1 / H8 / H1',
  tit: 'Countertrend channels inside higher-timeframe trends — maturity, rejoin zones and continuation structure',
};

export function ChannelIntelligence() {
  const visible = useVisible();
  const short = useShortScreen();
  const [tab, setTab] = useState('channels');
  const [symbol, setSymbol] = useState('XAUUSD');
  const [tf, setTf] = useState<ChannelTf>('W');
  const [btf, setBtf] = useState<EventTf>('H1');
  const [tick, setTick] = useState(0);

  const listLoader = useCallback(() => channelApi.list(), [tick]);
  const list = usePollingAsync(listLoader, [listLoader], { enabled: visible, intervalMs: 10000 });
  const detailLoader = useCallback(() => channelApi.detail(symbol, tf, btf), [symbol, tf, btf, tick]);
  const detail = usePollingAsync(detailLoader, [detailLoader], { enabled: visible, intervalMs: 5000 });
  const d = detail.data && detail.data.summary.symbol === symbol ? detail.data : null;
  const live = d?.available ? d : null;

  const charts = titCharts(live?.tit);
  const chanCandles = useCandles(symbol, tf, visible && tab === 'channels', tick, CHANNEL_BARS[tf]);
  const bkCandles = useCandles(symbol, btf, visible && tab === 'breakout', tick, btf === 'H1' ? 140 : 120);
  const titOn = visible && tab === 'tit';
  const l1 = useCandles(symbol, charts.L1, titOn, tick, 110);
  const ct = useCandles(symbol, charts.CT, titOn, tick, 110);
  const ex = useCandles(symbol, charts.EXEC, titOn, tick, 110);

  const meta = list.data?.meta ?? null;
  const rows = list.data?.rows ?? [];
  const row = d?.summary ?? rows.find((r) => r.symbol === symbol) ?? null;
  const digits = row ? rowDigits(row) : 2;
  const status = liveStatus(meta, !!list.error);
  const symbols = useMemo(() => (rows.length ? rows.map((r) => r.symbol) : ['XAUUSD']), [rows]);
  const price = row?.price ?? null;
  const chartHeight = short ? 262 : 330;

  const body = () => {
    if (!list.data) {
      return list.error ? (
        <Blocking title="Channel Intelligence unavailable" error={list.error} />
      ) : (
        <Blocking loading="Loading channel intelligence…" />
      );
    }
    if (tab === 'breakout') {
      return (
        <BreakoutRetest
          data={list.data}
          symbol={symbol}
          breakout={live?.breakout ?? null}
          digits={digits}
          tf={btf}
          onTf={setBtf}
          onSelect={setSymbol}
          candles={bkCandles}
          chartHeight={chartHeight}
          price={price}
        />
      );
    }
    if (!d) return detail.error ? <Blocking title="Channel analysis unavailable" error={detail.error} /> : <Blocking loading={`Loading ${symbol} channels…`} />;
    if (!live) return <Blocking title={`${symbol} — channels unavailable`} reason={d.summary.reason ?? 'Insufficient closed history'} />;
    if (tab === 'tit') {
      return (
        <TrendInTrend
          data={list.data}
          symbol={symbol}
          onSelect={setSymbol}
          tit={live.tit}
          tfLines={live.tf_lines}
          digits={digits}
          price={price}
          candles={{ L1: l1, CT: ct, EXEC: ex }}
          chartHeight={short ? 196 : 236}
        />
      );
    }
    if (!live.channel.available) return <Blocking title={`${symbol} · ${tf} channel unavailable`} reason={live.channel.reason} />;
    if (live.channel.tf !== tf) return <Blocking loading={`Loading ${symbol} ${tf} channel…`} />;
    return <ChannelAnalysis symbol={symbol} d={live.channel} digits={digits} tf={tf} onTf={setTf} candles={chanCandles} chartHeight={chartHeight} />;
  };

  return (
    <div className="mst-page mci-page">
      <header className="mst-head">
        <div>
          <nav className="mst-crumb" aria-label="Breadcrumb">
            Market Vision <span aria-hidden>›</span> <span>Channel Intelligence</span>
          </nav>
          <h1>Channel Intelligence</h1>
          <p>{SUBTITLE[tab]}</p>
        </div>
        <div className="mst-head-actions">
          <label className="mst-symbol-select">
            <InstrumentIcon base={symbol.slice(0, 3)} quote={symbol.slice(3, 6)} size="sm" />
            <select value={symbol} onChange={(e) => setSymbol(e.target.value)} aria-label="Instrument">
              {symbols.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          {tab === 'channels' ? (
            <div className="mst-tf mci-tfbar" role="group" aria-label="Channel timeframe">
              {CHANNEL_TFS.map((x) => (
                <button key={x} className={tf === x ? 'is-on' : ''} onClick={() => setTf(x)} aria-pressed={tf === x}>
                  {x}
                </button>
              ))}
            </div>
          ) : null}
          <div className={`mst-live is-${status.tone}`} role="status">
            <b>
              <i aria-hidden /> {status.label}
            </b>
            <small>Last update: {localStamp(meta?.last_cycle_at)}</small>
          </div>
          <button className="mst-refresh" aria-label="Reload analysis" title="Reload latest analysis" onClick={() => setTick((t) => t + 1)}>
            <RefreshCw size={16} className={list.refreshing || detail.refreshing ? 'is-spin' : ''} />
          </button>
        </div>
      </header>

      <div className="mst-tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t.id} role="tab" aria-selected={tab === t.id} className={tab === t.id ? 'is-on' : ''} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </div>

      {body()}
    </div>
  );
}

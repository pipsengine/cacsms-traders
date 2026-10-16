import { useCallback, useMemo, useState } from 'react';
import { X } from 'lucide-react';
import { autonomousApi } from '../../autonomous/api';
import type { ChannelLines } from '../../autonomous/types';
import { outlookApi } from '../../ai-outlook/api';
import { OutlookChart, type CandleState } from '../../ai-outlook/components/OutlookChart';
import { GOLD_TFS, HISTORY_LIMIT, TFS as OUTLOOK_TFS, type OutlookTf } from '../../ai-outlook/components/shared';
import { usePollingAsync } from '../../market-intelligence/hooks/useMarketIntelligence';
import { InstrumentIcon } from '../../market-scanner/components/InstrumentIcon';
import { StructureChart, type ChartOverlay } from '../../market-structure/components/StructureChart';
import { useCandles } from '../../market-structure/hooks';
import { useLive, useLiveCandles } from '../../market-structure/live';
import type { Campaign } from '../types';

const TFS = ['M15', 'H1', 'H4', 'H8', 'D1', 'W'] as const;
type ChartTf = (typeof TFS)[number];

function pairOf(symbol: string) {
  const clean = symbol.replace(/[^A-Za-z]/g, '').toUpperCase();
  if (clean.startsWith('XAU')) return { base: 'XAU', quote: clean.slice(3) || 'USD' };
  return { base: clean.slice(0, 3), quote: clean.slice(3, 6) };
}

function digitsFor(symbol: string) {
  if (symbol.startsWith('XAU')) return 2;
  if (symbol.includes('JPY')) return 3;
  return 5;
}

const HORIZON_TF: Partial<Record<Campaign['horizon'], ChartTf>> = {
  DAILY: 'D1',
  WEEKLY: 'W',
  GOLD_H8: 'H8',
};

/** Parent timeframe on the scenario is the chart that qualified the setup; the last token is the trigger. */
function analysisTf(campaign: Campaign): ChartTf {
  const named = campaign.scenarioId.split('|').filter((part): part is ChartTf => (TFS as readonly string[]).includes(part));
  if (named.length >= 2) return named[named.length - 2];
  return named.at(-1) ?? HORIZON_TF[campaign.horizon] ?? 'H1';
}

function outlookTf(campaign: Campaign): OutlookTf {
  if (campaign.horizon === 'GOLD_H8') return 'H8';
  if (campaign.horizon === 'WEEKLY') return 'W';
  if (campaign.horizon === 'MONTHLY') return 'MN';
  if (campaign.horizon === 'QUARTERLY') return 'Q';
  return 'D1';
}

function overlayFor(campaign: Campaign, lines: ChannelLines | null, channelDirection: string | null): ChartOverlay {
  const overlay: ChartOverlay = { lines: [], bands: [], levels: [], zones: [] };
  if (lines) {
    const bear = channelDirection === 'DESCENDING' || campaign.direction === 'SELL';
    overlay.bands!.push({
      upper: [lines.upper[0], lines.upper[1]],
      lower: [lines.lower[0], lines.lower[1]],
      tone: bear ? 'red' : 'green',
    });
    overlay.lines!.push(
      { from: lines.upper[0], to: lines.upper[1], tone: 'res', width: 1.6 },
      { from: lines.lower[0], to: lines.lower[1], tone: 'sup', width: 1.6 },
      { from: lines.mid[0], to: lines.mid[1], tone: 'mid', dashed: true },
    );
  }
  const from = campaign.publishedAt ?? undefined;
  if (campaign.entry != null && campaign.stopLoss != null && campaign.entry !== campaign.stopLoss) {
    const lo = Math.min(campaign.entry, campaign.stopLoss);
    const hi = Math.max(campaign.entry, campaign.stopLoss);
    overlay.zones!.push({ lo, hi, tone: 'blue', from, label: 'Entry to stop' });
  }
  if (campaign.entry != null) overlay.levels!.push({ price: campaign.entry, tone: 'blue', from, label: 'Entry' });
  if (campaign.stopLoss != null) overlay.levels!.push({ price: campaign.stopLoss, tone: 'red', from, label: 'Stop' });
  if (campaign.invalidation != null && campaign.invalidation !== campaign.stopLoss) {
    overlay.levels!.push({ price: campaign.invalidation, tone: 'red', dashed: true, from, label: 'Invalidation' });
  }
  campaign.targets.forEach((price, index) => {
    if (price != null) overlay.levels!.push({ price, tone: 'green', dashed: true, from, label: `Target ${index + 1}` });
  });
  return overlay;
}

function OutlookAnalysis({ campaign }: { campaign: Campaign }) {
  const horizon = campaign.horizon === 'GOLD_H8' ? 'H8' : campaign.horizon;
  const choices = horizon === 'H8' ? GOLD_TFS : OUTLOOK_TFS;
  const [tf, setTf] = useState<OutlookTf>(() => outlookTf(campaign));
  const detail = usePollingAsync(
    useCallback(() => outlookApi.symbol(campaign.symbol, null, horizon), [campaign.symbol, horizon]),
    [campaign.symbol, horizon],
    { intervalMs: 30000 },
  );
  const outlook = detail.data?.outlook?.symbol === campaign.symbol ? detail.data.outlook : null;
  const loaded = useCandles(campaign.symbol, tf, true, 0, HISTORY_LIMIT[tf]);
  const live = useLive(campaign.symbol, [tf], true);
  const bars = useLiveCandles(`${campaign.symbol}|outlook|${tf}`, loaded.candles, live.data?.forming?.[tf]);
  const candles: CandleState = {
    candles: bars,
    loading: loaded.loading && !bars.length,
    error: loaded.error ?? detail.error,
    price: live.data?.quote && !live.data.quote.stale ? live.data.quote.price : null,
    forming: bars.length > 0 && bars.at(-1) !== loaded.candles.at(-1),
  };
  if (!outlook) {
    return <p className="ce-chart-wait">{detail.error || 'Loading the outlook chart…'}</p>;
  }
  return (
    <OutlookChart
      o={outlook}
      tf={tf}
      onTf={setTf}
      candles={candles}
      title="Outlook"
      mode="outlook"
      height={500}
      tfs={choices}
    />
  );
}

function StrategyAnalysis({ campaign }: { campaign: Campaign }) {
  const [tf, setTf] = useState<ChartTf>(() => analysisTf(campaign));
  const chart = usePollingAsync(
    useCallback(() => autonomousApi.symbolChart(campaign.symbol, tf, 180), [campaign.symbol, tf]),
    [campaign.symbol, tf],
    { intervalMs: 5000 },
  );
  const live = useLive(campaign.symbol, [tf], true);
  const fresh = chart.data?.symbol === campaign.symbol && chart.data.timeframe === tf ? chart.data : null;
  const closed = (fresh?.candles ?? []).map((bar) => ({ ...bar, v: bar.v ?? 0 }));
  const bars = useLiveCandles(`${campaign.symbol}|${tf}`, closed, live.data?.forming?.[tf]);
  const channel = fresh?.channel ?? null;
  const overlay = useMemo(() => overlayFor(campaign, channel?.lines ?? null, channel?.direction ?? null), [campaign, channel]);
  const digits = channel?.digits ?? digitsFor(campaign.symbol);
  const last = live.data?.quote && !live.data.quote.stale ? live.data.quote.price : bars.at(-1)?.c;

  return (
    <>
      <div className="ce-chart-tfs" role="tablist" aria-label="Analysis timeframe">
        {TFS.map((name) => (
          <button key={name} type="button" role="tab" aria-selected={tf === name} className={tf === name ? 'is-on' : ''} onClick={() => setTf(name)}>{name === 'W' ? 'W1' : name}</button>
        ))}
      </div>
      <div className="ce-chart-body">
        <StructureChart
          symbol={campaign.symbol}
          title={`${tf} analysis`}
          tf={tf}
          candles={bars}
          digits={digits}
          lastPrice={last}
          height={520}
          loading={chart.loading && !bars.length}
          error={chart.error || undefined}
          overlay={overlay}
          showVolume={false}
          zoomable
          defaultSpan={120}
          heading={<span>{tf === 'W' ? 'W1' : tf} chart used to qualify this setup</span>}
        />
      </div>
    </>
  );
}

export function CampaignChartModal({ campaign, onClose }: { campaign: Campaign; onClose: () => void }) {
  const outlook = campaign.sourceMode === 'OUTLOOK' && !campaign.strategyType;
  const setup = campaign.strategyType || campaign.status;
  return (
    <div className="ce-backdrop is-chart" role="presentation" onMouseDown={onClose}>
      <section className="ce-chart-modal" role="dialog" aria-modal="true" aria-label={`${campaign.symbol} analysis chart`} onMouseDown={(event) => event.stopPropagation()}>
        <header className="ce-chart-head">
          <div>
            <small>{setup} · {campaign.direction === 'BUY' ? 'Bullish' : campaign.direction === 'SELL' ? 'Bearish' : 'Neutral'}</small>
            <h2>
              <InstrumentIcon {...pairOf(campaign.symbol)} size="sm" />
              {campaign.symbol}
            </h2>
          </div>
          <button type="button" aria-label="Close chart" onClick={onClose}><X size={18} /></button>
        </header>
        {outlook ? (
          <div className="ce-chart-body">
            <OutlookAnalysis campaign={campaign} />
          </div>
        ) : (
          <StrategyAnalysis campaign={campaign} />
        )}
      </section>
    </div>
  );
}

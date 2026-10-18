import { useCallback } from 'react';
import { usePollingAsync } from '../market-intelligence/hooks/useMarketIntelligence';
import { outlookApi } from '../ai-outlook/api';
import { marketStructureApi } from '../market-structure/api';
import type { SymbolPayload } from '../ai-outlook/types';
import type { RangeDetail, TrendDetail } from '../market-structure/types';

export function useChartIntel(symbol: string) {
  const load = useCallback(async () => {
    const [outlook, range, trend] = await Promise.all([
      outlookApi.symbol(symbol).catch(() => null),
      marketStructureApi.range(symbol).catch(() => null),
      marketStructureApi.trend(symbol).catch(() => null),
    ]);
    return { outlook: outlook as SymbolPayload | null, range: range as RangeDetail | null, trend: trend as TrendDetail | null };
  }, [symbol]);

  return usePollingAsync(load, [load], { enabled: !!symbol, intervalMs: 60_000 });
}

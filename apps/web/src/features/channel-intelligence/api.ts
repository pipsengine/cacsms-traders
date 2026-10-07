import { get } from '../market-structure/api';
import type { ChannelPayload, ChannelSymbolDetail } from './types';

export const channelApi = {
  list: () => get<ChannelPayload>('/channels'),
  detail: (symbol: string, timeframe: string, breakoutTimeframe: string) =>
    get<ChannelSymbolDetail>(
      `/channels/${encodeURIComponent(symbol)}?${new URLSearchParams({ timeframe, breakout_timeframe: breakoutTimeframe })}`,
    ),
};

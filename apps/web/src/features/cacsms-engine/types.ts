export type Horizon = 'DAILY' | 'WEEKLY' | 'MONTHLY' | 'QUARTERLY' | 'GOLD_H8';
export type Stage =
  | 'QUALIFICATION'
  | 'CONFIRMATION'
  | 'RISK'
  | 'EXECUTION'
  | 'MANAGEMENT'
  | 'MONITORING'
  | 'BLOCKED'
  | 'CLOSED';
export type Direction = 'BUY' | 'SELL' | 'NEUTRAL';
export type TradingMode = 'SHADOW' | 'DEMO' | 'LIVE' | 'PAUSED';

export interface BrokerPosition {
  ticket: string;
  symbol: string;
  direction: Direction;
  volume: number;
  priceOpen: number;
  priceCurrent: number | null;
  stopLoss: number | null;
  takeProfit: number | null;
  profit: number | null;
  openedAt?: string | null;
}

export interface Campaign {
  id: string;
  tenantId: string;
  accountId: string;
  outlookId: string;
  scenarioId: string;
  analysisVersion: number;
  symbol: string;
  horizon: Horizon;
  sourceMode?: 'STRATEGY' | 'OUTLOOK' | 'COMBINED';
  strategyType?: string | null;
  conflict?: string | null;
  linkedIds?: string[];
  outlookQualified?: boolean;
  direction: Direction;
  evidenceScore: number;
  stage: Stage;
  status: string;
  entry?: number | null;
  stopLoss?: number | null;
  targets: number[];
  invalidation?: number | null;
  positionsOpen: number;
  positionsPending: number;
  positionsUsed: number;
  maxPositions: number | null;
  brokerPositions?: BrokerPosition[];
  nextAction: string;
  updatedAt: string;
  publishedAt?: string | null;
  reason?: string;
  isStale?: boolean;
  pipelineStage?: string | null;
}

export interface EngineSummary {
  qualified: number;
  monitoring: number;
  awaitingConfirmation: number;
  pendingRisk: number;
  executing: number;
  openPositions: number;
  fxPositions?: number | null;
  goldPositions?: number | null;
  pendingOrders?: number;
  rejected?: number;
  confirmed?: number;
  campaigns: number;
  exposurePercent: number | null;
  maxExposurePercent: number | null;
  exposureRemainingPercent?: number | null;
  tradingMode: TradingMode;
  marketDataStatus: string;
  brokerStatus: string;
  brokerBasis?: string;
  horizonCounts?: Partial<Record<Horizon, number>>;
  sourceCounts?: { outlook: number; strategy: number; combined: number; conflicts: number };
  performance?: { basis: string; strategy: Record<string, { closed: number; targets: number; stopped: number }> };
}

export interface EngineResponse {
  summary: EngineSummary;
  campaigns: Campaign[];
  generatedAt: string;
}

export interface CampaignDetail extends Campaign {
  evidence?: Array<{ label: string; value: string }>;
  events?: Array<{ at: string; stage: string; message: string }>;
  risk?: Record<string, string | number | boolean | null>;
}

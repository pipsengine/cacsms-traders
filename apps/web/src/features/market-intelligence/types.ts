export type RelationshipState =
  | 'DIVERGENCE'
  | 'EQUILIBRIUM'
  | 'CONVERGENCE'
  | 'ROTATION'
  | 'TRANSITIONING'
  | 'UNCERTAIN';
export type InspectionPriority = 'CRITICAL' | 'HIGH' | 'NORMAL' | 'LOW';
export type CalculationMode =
  | 'CLOSE_CLOSE'
  | 'MA'
  | 'RSI'
  | 'RSI_MA'
  | 'STOCH_MAIN'
  | 'STOCH_SIGNAL';

export interface StrengthRow {
  currency: string;
  timeframe: string;
  as_of: string;
  value: number;
  slope: number;
  velocity: number;
  acceleration: number;
  persistence: number;
  confidence: number;
  sample_count: number;
  quality: string;
}

export type StrengthTone = 'positive' | 'neutral' | 'negative';
export type EngineState = 'STARTING' | 'SYNCING' | 'READY' | 'MT5_DISCONNECTED' | 'ERROR';
export type StaleReason = 'MT5_DISCONNECTED' | 'ENGINE_STALLED';

export interface StrengthClassification {
  key: string;
  label: string;
  tone: StrengthTone;
}

export interface MatrixMeta {
  as_of: string | null;
  last_calculated_at: string | null;
  calculation_mode: CalculationMode;
  bars_difference: number;
  sort_by: string;
  closed_bar_only: boolean;
  bar_basis?: 'earnforex' | 'closed';
  mode_pending?: boolean;
  data_source: string;
  mt5_connected: boolean;
  mt5_server?: string;
  live_data?: boolean;
  historical_ok: boolean;
  missing_history: { symbol: string; timeframe: string }[];
  stale: boolean;
  stale_reason?: StaleReason | null;
  currency_order: string[];
  pairs_loaded?: number;
  pairs_total?: number;
  missing_pairs?: string[];
  classification_thresholds?: { key: string; label: string; tone: StrengthTone; min: number }[];
  engine_state?: EngineState | string;
  engine_error?: string | null;
  live_refresh_at?: string | null;
  last_persisted_at?: string | null;
  last_bar_change_at?: string | null;
}

export interface MatrixCurrencyRow {
  currency: string;
  values: Record<string, number>;
  scores: Record<string, number>;
  quality: Record<string, string>;
  sample_counts: Record<string, number>;
}

export interface AvgRankRow {
  currency: string;
  value: number;
  score: number | null;
  rank: number;
  classification: StrengthClassification | null;
}

export interface CurrencySummary {
  currency: string;
  score: number;
  classification: StrengthClassification;
  sparkline: number[];
  change: number;
  change_pct: number;
  rank: number;
}

export interface StrengthMatrixPayload {
  meta: MatrixMeta;
  matrix: MatrixCurrencyRow[];
  avg_ranking: AvgRankRow[];
  currency_summary: CurrencySummary[];
}

export interface RelationshipRow {
  pair: string;
  timeframe: string;
  as_of: string;
  base_value: number;
  quote_value: number;
  gap: number;
  abs_gap: number;
  gap_velocity: number;
  gap_acceleration: number;
  persistence: number;
  state: RelationshipState;
  confidence: number;
  inspection_priority: InspectionPriority;
  reason_codes: string;
}

export interface QualityRow {
  symbol: string;
  timeframe: string;
  state: string;
  last_closed_at?: string;
  age_seconds?: number;
  missing_bars: number;
  reason?: string;
}

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

export interface MatrixMeta {
  as_of: string | null;
  last_calculated_at: string | null;
  calculation_mode: CalculationMode;
  bars_difference: number;
  sort_by: string;
  closed_bar_only: boolean;
  data_source: string;
  mt5_connected: boolean;
  historical_ok: boolean;
  missing_history: { symbol: string; timeframe: string }[];
  stale: boolean;
  currency_order: string[];
}

export interface MatrixCurrencyRow {
  currency: string;
  values: Record<string, number>;
  quality: Record<string, string>;
  sample_counts: Record<string, number>;
}

export interface AvgRankRow {
  currency: string;
  value: number;
  rank: number;
}

export interface StrengthMatrixPayload {
  meta: MatrixMeta;
  matrix: MatrixCurrencyRow[];
  avg_ranking: AvgRankRow[];
  rows: StrengthRow[];
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

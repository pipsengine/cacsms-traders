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
export type EngineState = 'STARTING' | 'SYNCING' | 'READY' | 'PROVIDER_DISCONNECTED' | 'ERROR';
export type StaleReason = 'PROVIDER_DISCONNECTED' | 'ENGINE_STALLED';

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
  provider_connected?: boolean;
  active_provider?: string;
  provider_status?: string;
  authorization_status?: string;
  error_code?: string | null;
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

export type EngineMeta = Pick<
  MatrixMeta,
  | 'as_of'
  | 'last_calculated_at'
  | 'provider_connected'
  | 'active_provider'
  | 'live_data'
  | 'historical_ok'
  | 'missing_history'
  | 'pairs_loaded'
  | 'pairs_total'
  | 'missing_pairs'
  | 'engine_state'
  | 'bar_basis'
  | 'closed_bar_only'
  | 'engine_error'
  | 'stale'
  | 'stale_reason'
  | 'live_refresh_at'
  | 'last_persisted_at'
  | 'last_bar_change_at'
> & { snapshot_interval_seconds: number };

export interface KeyLabel<K extends string = string> {
  key: K;
  label: string;
}

export interface Coverage {
  complete: boolean;
  pct: number;
  first_available: string | null;
}

export interface IntelThresholds {
  relationship: { key: string; label: string; min: number }[];
  dynamics_epsilon: number;
  alignment_epsilon: number;
  aligned_ratio: number;
  persistent_ratio: number;
  developing_ratio: number;
  trend_band: number;
  momentum_epsilon: number;
  reversal_amplitude: number;
  crossover_min_gap: number;
  dynamics_lookback_minutes: number;
  htf: string[];
  ltf: string[];
  classification: { key: string; label: string; tone: StrengthTone; min: number }[];
}

export type HistoryPeriod = '24H' | '7D' | '1M' | '3M' | '6M' | 'YTD';

export interface CurrencyHistoryStats {
  currency: string;
  available: boolean;
  points?: number;
  rank?: number;
  current?: number;
  classification?: StrengthClassification;
  start?: number;
  start_at?: string;
  change?: number;
  change_pct?: number | null;
  trend?: KeyLabel<'STRENGTHENING' | 'WEAKENING' | 'STABLE'>;
  momentum?: KeyLabel<'ACCELERATING' | 'DECELERATING' | 'STABLE' | 'INSUFFICIENT'> & {
    recent: number | null;
    prior: number | null;
  };
  high?: number;
  high_at?: string;
  low?: number;
  low_at?: string;
  average?: number;
}

export interface StrengthEvent {
  type: 'REVERSAL' | 'CROSSOVER' | 'MIDLINE';
  at: string;
  detail: string;
  currency?: string;
  currencies?: string[];
  leader?: string;
  laggard?: string;
  direction?: string;
  score?: number;
}

export interface HistoricalStrengthPayload {
  meta: EngineMeta & { timeframe: string };
  thresholds: IntelThresholds;
  period: HistoryPeriod;
  from: string;
  to: string;
  points: number;
  coverage: Coverage;
  currencies: CurrencyHistoryStats[];
  chart: { times: string[]; values: Record<string, (number | null)[]> };
  events: StrengthEvent[];
  event_count: number;
}

export type RelationshipKey = 'STRONG_DIVERGENCE' | 'DIVERGENCE' | 'MODERATE' | 'BALANCED';
export type DynamicsKey = 'EXPANDING' | 'CONTRACTING' | 'REVERSING' | 'STABLE' | 'NO_HISTORY';
export type AlignmentKey = 'ALIGNED' | 'PARTIAL' | 'CONFLICTED' | 'NEUTRAL';
export type Side = 'BASE' | 'QUOTE' | 'NONE';

export interface PairRelationship {
  pair: string;
  base: string;
  quote: string;
  rank: number;
  base_strength: number;
  quote_strength: number;
  base_class: StrengthClassification;
  quote_class: StrengthClassification;
  differential: number;
  abs_differential: number;
  dominant: Side;
  relationship: KeyLabel<RelationshipKey>;
  dynamics: KeyLabel<DynamicsKey> & { change: number | null; previous: number | null };
  alignment: KeyLabel<AlignmentKey> & { aligned: number; total: number; pct: number; direction: Side };
  timeframes: Record<string, number>;
}

export interface PairRelationshipsPayload {
  meta: EngineMeta & {
    reference_as_of: string | null;
    reference_age_minutes: number | null;
    lookback_minutes: number;
    pairs_available: number;
    scope: { tenant_id: string | null; trading_account_id: string | null };
  };
  thresholds: IntelThresholds;
  summary: { relationship_counts: Record<RelationshipKey, number> };
  rows: PairRelationship[];
}

export type AnalysisStateKey =
  | 'EXPANDING_DIVERGENCE'
  | 'CONTRACTING_DIVERGENCE'
  | 'CONVERGENCE'
  | 'EQUILIBRIUM'
  | 'REVERSAL'
  | 'PERSISTENT_DIVERGENCE'
  | 'STABLE_DIVERGENCE'
  | 'DIVERGENCE';

export interface AnalysisMatrixRow {
  timeframe: string;
  available: boolean;
  group?: 'HTF' | 'LTF';
  base?: number;
  quote?: number;
  differential?: number;
  previous?: number | null;
  change?: number | null;
  relationship?: KeyLabel<RelationshipKey>;
  state?: KeyLabel<AnalysisStateKey>;
  persistence?: number | null;
  favours?: Side;
}

export interface RelationshipAnalysisPayload {
  meta: EngineMeta & {
    pair: string;
    period: HistoryPeriod;
    from: string;
    to: string;
    lookback_minutes: number;
    reference_age_minutes: number | null;
    reference_as_of: string | null;
    coverage: Coverage;
    history_points: number;
  };
  thresholds: IntelThresholds;
  relationship: PairRelationship;
  summary: {
    state: KeyLabel<AnalysisStateKey>;
    alignment: PairRelationship['alignment'];
    htf_ltf: KeyLabel<'AGREE' | 'DISAGREE' | 'INCONCLUSIVE'> & { htf: Side; ltf: Side };
    base_direction: KeyLabel & { change: number | null };
    quote_direction: KeyLabel & { change: number | null };
    persistence: KeyLabel & { ratio: number | null; pct?: number };
    trajectory: KeyLabel & { slope_per_hour: number | null; window_change: number | null };
    run: { since: string | null; bounded_by_history: boolean; last_reversal_at: string | null };
    states_by_timeframe: Record<AnalysisStateKey, number>;
  };
  matrix: AnalysisMatrixRow[];
  history: { at: string; differential: number }[];
  interpretation: string[];
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

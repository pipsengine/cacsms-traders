import type { ScannerMeta } from '../market-scanner/types';

export type KeyLabel = { key: string; label: string };
export type Tone = 'up' | 'down' | 'amber' | 'muted';

export type RangeRow = {
  symbol: string;
  base: string;
  quote: string;
  name: string;
  asset: 'Forex' | 'Commodity';
  digits: number | null;
  price: number | null;
  price_live: boolean;
  change: number | null;
  change_pct: number | null;
  available: boolean;
  regime: KeyLabel;
  unavailable_reason?: string;
  state?: KeyLabel | null;
  ranging?: boolean;
  range_high?: number;
  range_low?: number;
  midpoint?: number;
  width?: number;
  width_atr?: number | null;
  age_weeks?: number;
  touches_high?: number;
  touches_low?: number;
  false_breakouts?: number;
  quality?: number | null;
  reliability?: 'HIGH' | 'MEDIUM' | 'LOW' | null;
  position?: number;
  position_band?: KeyLabel;
  developing_fractal?: { kind: 'WFH' | 'WFL'; price: number } | null;
  fractal_kind?: 'WFH' | 'WFL';
  evidence_score?: number;
  mtf?: { W: string | null; D1: string | null; H8: string | null };
  hypothesis?: { key: string; label: string; direction: 'UP' | 'DOWN' | null };
  breakout_score?: number | null;
  decision?: string;
};

export type RangeCounts = { ranging: number; near_upper: number; near_lower: number; breakout_risk: number; all: number };

export type RangeMeta = ScannerMeta & { range_settings: Record<string, unknown> & { extreme_pct: number } };

export type RangePayload = { meta: RangeMeta; counts: RangeCounts; rows: RangeRow[] };

export type FractalMark = { kind: 'WFH' | 'WFL'; at: string; price: number; in_cluster: boolean; major?: boolean };

export type RangeCore = {
  regime: KeyLabel;
  state: KeyLabel | null;
  ranging: boolean;
  basis: 'VALIDATED_RANGE' | 'RECENT_SWINGS';
  start: string;
  age_weeks: number;
  atr: number;
  tolerance: number;
  range_high: number;
  range_low: number;
  midpoint: number;
  width: number;
  width_atr: number | null;
  high_zone: [number, number] | null;
  low_zone: [number, number] | null;
  touches_high: number;
  touches_low: number;
  last_touch_high: string | null;
  last_touch_low: string | null;
  false_breakouts: number;
  last_close_outside: boolean;
  quality: number | null;
  reliability: 'HIGH' | 'MEDIUM' | 'LOW' | null;
  fractals: FractalMark[];
  channel_direction: string | null;
  volatility_trend: string | null;
};

export type Evidence = { key: string; label: string; met: boolean; weight: number };

export type MtfRow = {
  timeframe: string;
  structure: KeyLabel;
  channel: string;
  signal: KeyLabel & { tone: Tone };
};

export type Hypothesis = { direction: 'UP' | 'DOWN'; score: number; band: KeyLabel };

export type RangeView = {
  available: true;
  position: number;
  position_band: KeyLabel;
  developing_fractal: null | {
    kind: 'WFH' | 'WFL';
    price: number;
    at: string;
    bars_to_confirm: number;
    label: string;
    location: string;
  };
  fractal_kind: 'WFH' | 'WFL';
  evidence: Evidence[];
  evidence_score: number;
  mtf: MtfRow[];
  hypotheses: { reversal: Hypothesis; breakout: Hypothesis } | null;
  summary_hypothesis: { key: string; label: string; direction: 'UP' | 'DOWN' | null };
  workflow: { label: string; done: boolean }[];
  stage: number;
  decision: { key: string; title: string; subtitle: string; narrative: string; direction: 'UP' | 'DOWN' | null };
};

export type ChannelOverlay = {
  key: string;
  upper?: number;
  mid?: number;
  lower?: number;
  slope_pct_per_bar?: number;
  direction?: string;
  period?: number;
};

export type RangeDetail =
  | { meta: RangeMeta; available: false; summary: RangeRow }
  | {
      meta: RangeMeta;
      available: true;
      summary: RangeRow;
      range: RangeCore;
      view: RangeView;
      channels: { D1: ChannelOverlay; H8: ChannelOverlay };
      last_closed: Record<string, number | null>;
    };

export type VCandle = { t: string; o: number; h: number; l: number; c: number; v: number };

export type HeaderTf = 'W' | 'D' | 'H8' | 'H4';

// ----- Structure Overview -----

export type RegimeKey = 'BULLISH' | 'BEARISH' | 'RANGING' | 'TRANSITION';
export type OverviewTf = 'W' | 'D1' | 'H8' | 'H1';
export type RegimeCounts = { bullish: number; bearish: number; ranging: number; transition: number };
export type Alignment = { score: number; key: 'BULLISH' | 'BEARISH' | 'MIXED'; label: string };
export type MatrixCell = (KeyLabel & { regime: RegimeKey }) | null;

export type OverviewRow = {
  symbol: string;
  base: string;
  quote: string;
  name: string;
  asset: 'Forex' | 'Commodity';
  digits: number | null;
  price: number | null;
  available: boolean;
  reason?: string;
  regime?: KeyLabel;
  cells?: Record<OverviewTf, MatrixCell>;
  state?: KeyLabel;
  strength?: Alignment;
  ranging?: boolean;
  range_age_weeks?: number | null;
};

export type StructuralEvent = {
  symbol: string;
  digits: number | null;
  tf: OverviewTf;
  kind: 'BOS' | 'CHOCH';
  direction: 'UP' | 'DOWN';
  level: number;
  at: string;
  label: string;
  status: KeyLabel;
};

export type RegimeChange = { symbol: string; tf: OverviewTf; from: KeyLabel; to: KeyLabel; at: string };
export type AttentionItem = { symbol: string; reason: string; tf: string; detail: string; status: KeyLabel };
export type OpportunityGroup = { key: string; label: string; count: number; examples: string[] };
export type AlignmentEntry = { symbol: string; base: string; quote: string; strength: Alignment };

// ----- Trend Structure -----

export type TrendTf = 'W' | 'D1' | 'H8' | 'H1';
export type TrendDirection = 'BULLISH' | 'BEARISH' | null;
export type TrendCell = (KeyLabel & { regime: string }) | null;
export type TrendSetupKey = 'CONTINUATION' | 'EXTENSION' | 'REVERSAL_RISK' | 'DEVELOPING' | 'NO_TREND';

export type TrendRow = {
  symbol: string;
  base: string;
  quote: string;
  name: string;
  asset: 'Forex' | 'Commodity';
  digits: number | null;
  price: number | null;
  available: boolean;
  reason?: string;
  direction?: TrendDirection;
  cells?: Record<TrendTf, TrendCell>;
  state?: KeyLabel;
  strength?: number;
  age_weeks?: number | null;
  setup?: TrendSetupKey;
  pullback?: boolean;
  reversal_risk?: boolean;
};

export type TrendCounts = {
  analysed: number;
  total: number;
  trending: number;
  bullish: number;
  bearish: number;
  pullback: number;
  continuation: number;
  reversal_risk: number;
};

export type TrendMeta = ScannerMeta & {
  trend_settings: { analysis_tf: TrendTf; strong_min: number; continuation_zone: [number, number] } & Record<string, unknown>;
};

export type TrendPayload = { meta: TrendMeta; counts: TrendCounts; rows: TrendRow[] };

export type TrendGeometry = {
  leg_start: number;
  leg_extreme: number;
  leg_size: number;
  depth_pct: number;
  pullback: KeyLabel;
  zone: [number, number];
  invalidation: number;
  objective_1: number;
  objective_2: number;
  ratio: number | null;
  status: KeyLabel;
};

export type TrendView = {
  available: true;
  closed_bar_only: boolean;
  price: number;
  direction: TrendDirection;
  alignment: Alignment;
  state: KeyLabel;
  strength: number;
  components: { alignment: number; structure: number; channel: number; momentum: number };
  age_weeks: number | null;
  trend_started_at: string | null;
  structure_sequence: string[];
  pullback_cells: TrendTf[];
  geometry: TrendGeometry | null;
  reversal_reasons: string[];
  setup: { key: TrendSetupKey; title: string; subtitle: string };
  confidence: number;
  health: {
    structure_strength: number;
    channel_position: number | null;
    momentum_alignment: number;
    pullback_depth: number | null;
    trend_continuation: number;
  };
  key_levels: { support: number | null; resistance: number | null; basis: string };
  analysis_tf: TrendTf;
  anchor: string;
};

export type TrendMtfRow = { tf: TrendTf; cell: TrendCell; swings: string; channel: string | null };

export type TrendEvent = {
  tf: TrendTf;
  at: string;
  event: string;
  kind: 'SWING' | 'BOS' | 'CHOCH';
  direction: 'UP' | 'DOWN';
  level: number;
  status: KeyLabel;
};

export type TrendDetail =
  | { meta: TrendMeta; available: false; summary: TrendRow }
  | {
      meta: TrendMeta;
      available: true;
      summary: TrendRow;
      view: TrendView;
      mtf: TrendMtfRow[];
      events: TrendEvent[];
      channels: Record<TrendTf, ChannelOverlay | null>;
      last_closed: Record<TrendTf, string | null>;
    };

export type OverviewPayload = {
  meta: ScannerMeta & { data_as_of: string | null; overview_settings: Record<string, unknown> };
  counts: RegimeCounts & { analysed: number; total: number };
  mtf: Record<OverviewTf, RegimeCounts>;
  strongest: AlignmentEntry[];
  weakest: AlignmentEntry[];
  rows: OverviewRow[];
  events: StructuralEvent[];
  regime_changes: RegimeChange[];
  attention: AttentionItem[];
  opportunities: OpportunityGroup[];
};

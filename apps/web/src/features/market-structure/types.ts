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

// ----- Fractals -----

export type FractalTf = 'W' | 'D1' | 'H8' | 'H1';
export type FractalStatusKey = 'CANDIDATE' | 'DEVELOPING' | 'PROVISIONAL' | 'CONFIRMED' | 'INVALID';
export type FractalPoint = {
  kind: 'WFH' | 'WFL' | 'FH' | 'FL';
  side: 'HIGH' | 'LOW';
  price: number;
  at: string;
  status: { key: FractalStatusKey; label: string };
};

export type FractalRow = {
  symbol: string;
  base: string;
  quote: string;
  name: string;
  asset: 'Forex' | 'Commodity';
  digits: number | null;
  price: number | null;
  available: boolean;
  reason?: string;
  cells?: Record<FractalTf, FractalPoint | null>;
  latest?: FractalPoint | null;
};

export type FractalCounts = {
  total: number;
  confirmed: number;
  developing: number;
  invalid: number;
  candidates: number;
  clusters: number;
  symbols_active: number;
  analysed: number;
  symbols: number;
};

export type FractalPayload = {
  meta: ScannerMeta & { fractal_settings: Record<string, number> };
  counts: FractalCounts;
  rows: FractalRow[];
  near_cluster_atr: number;
};

export type FractalCluster = {
  side: 'HIGH' | 'LOW';
  lo: number;
  hi: number;
  touches: number;
  first_at: string;
  last_at: string;
  age_weeks: number;
  distance: number;
  distance_atr: number | null;
  near: boolean;
};

export type FractalHierarchyItem = {
  tf: FractalTf | null;
  kind: string;
  price: number;
  side: 'HIGH' | 'LOW' | null;
  status: KeyLabel | null;
  title: string;
  note: string;
};

export type FractalLifecycleStep = { key: FractalStatusKey; label: string; description: string; done: boolean; current: boolean; at: string | null };

export type FractalView = {
  available: true;
  price: number;
  closed_bar_only: boolean;
  timeframes: Record<FractalTf, { available: boolean; sides?: { high: FractalPoint | null; low: FractalPoint | null }; latest?: FractalPoint | null }>;
  hierarchy: FractalHierarchyItem[];
  details: null | {
    kind: string;
    side: 'HIGH' | 'LOW';
    label: string;
    price: number;
    tf: string;
    status: KeyLabel;
    cluster_zone: [number, number] | null;
    touches: number;
    last_touch: string;
    range_position: number | null;
    range_band: string | null;
    atr: number | null;
    validation: string;
  };
  lifecycle: FractalLifecycleStep[];
  evidence: Evidence[];
  evidence_score: number | null;
  ltf: { tf: FractalTf; structure: KeyLabel; fractal: string; fractal_status: FractalStatusKey | null; evidence: string }[];
  clusters: { resistance: FractalCluster[]; support: FractalCluster[] };
  range: { high: number; low: number; start: string; ranging: boolean } | null;
};

export type FractalChartMark = { kind: string; side: 'HIGH' | 'LOW'; price: number; at: string; status: 'CONFIRMED' | 'PENDING' | 'INVALID' };

export type FractalDetail =
  | { meta: FractalPayload['meta']; available: false; summary: FractalRow }
  | {
      meta: FractalPayload['meta'];
      available: true;
      summary: FractalRow;
      view: FractalView;
      tf: FractalTf;
      marks: FractalChartMark[];
      range: Pick<RangeCore, 'start' | 'high_zone' | 'low_zone' | 'range_high' | 'range_low' | 'midpoint'> | null;
    };

// ----- BOS / CHoCH -----

export type BosTf = 'W' | 'D1' | 'H8' | 'H1';

export type BosEvent = {
  symbol: string;
  base: string;
  quote: string;
  asset: 'Forex' | 'Commodity';
  digits: number | null;
  tf: BosTf;
  kind: 'BOS' | 'CHOCH';
  direction: 'UP' | 'DOWN';
  level: number;
  at: string;
  break_at?: string;
  label: string;
  closed: boolean;
  close: number | null;
  body_acceptance: boolean | null;
  volume_ratio: number | null;
  retest_at: string | null;
  retest_completed_at: string | null;
  failed?: boolean;
  status: KeyLabel;
  retest: KeyLabel;
};

export type BosCounts = {
  total: number;
  new_24h: number;
  bullish_bos: number;
  bearish_bos: number;
  bullish_choch: number;
  bearish_choch: number;
  awaiting: number;
  analysed: number;
  symbols: number;
};

export type BosPayload = {
  meta: ScannerMeta & { bos_settings: Record<string, number> };
  counts: BosCounts;
  events: BosEvent[];
  symbols: { symbol: string; base: string; quote: string; asset: string; digits: number | null; price: number | null; available: boolean }[];
};

export type BosLevel = { price: number; type: string; tf: string; distance: number | null };

export type BosDetailView = {
  context: {
    parent: string | null;
    parent_band: string | null;
    d1: string | null;
    phase: KeyLabel;
    last_bos: { level: number; tf: string; direction: 'UP' | 'DOWN' } | null;
    last_choch: { level: number; tf: string; direction: 'UP' | 'DOWN' } | null;
    price: number | null;
    nearest_resistance: BosLevel | null;
    nearest_support: BosLevel | null;
    bias: string;
    invalidation: number | null;
    retest: KeyLabel | null;
    since: string | null;
  };
  details: null | {
    label: string;
    kind: 'BOS' | 'CHOCH';
    direction: 'UP' | 'DOWN';
    tf: BosTf;
    level: number;
    at: string;
    break_candle: string | null;
    closed: boolean;
    close_side: string;
    body_acceptance: boolean | null;
    retest: KeyLabel;
    status: KeyLabel;
    parent_w: string | null;
    d1: string | null;
    h8: string | null;
    structure_after: string;
    volume_ratio: number | null;
    volume_confirmed: boolean;
    invalidation: number | null;
    since: string;
  };
  lifecycle: { key: string; label: string; done: boolean; current?: boolean; at: string | null }[] | null;
  evidence: { label: string; met: boolean }[] | null;
  mtf: { tf: BosTf; structure: string | null; last_event: string | null; last_direction: 'UP' | 'DOWN' | null; status: string }[];
  levels: BosLevel[];
};

export type BosDetail =
  | { meta: BosPayload['meta']; available: false; summary: BosPayload['symbols'][number] }
  | ({
      meta: BosPayload['meta'];
      available: true;
      summary: BosPayload['symbols'][number];
      tf: BosTf;
      marks: {
        events: { kind: 'BOS' | 'CHOCH'; direction: 'UP' | 'DOWN'; level: number; swing_at: string | null; break_at: string | null; failed: boolean }[];
        swings: { label: string; side: 'HIGH' | 'LOW'; price: number; at: string }[];
      };
      alignment: Alignment;
    } & BosDetailView);

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

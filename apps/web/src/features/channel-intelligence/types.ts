import type { ScannerMeta } from '../market-scanner/types';
import type { KeyLabel } from '../market-structure/types';

export type ChannelTf = 'Y' | 'YTD' | 'HY' | 'Q' | 'MN' | 'W' | 'D1' | 'H8' | 'H1';
export type EventTf = 'W' | 'D1' | 'H8' | 'H1';
export type Line = [[string, number], [string, number]];
export type ChannelLines = { upper: Line; mid: Line; lower: Line };
export type Direction = 'UP' | 'DOWN';

export type ChannelView =
  | { tf: ChannelTf; available: false }
  | {
      tf: ChannelTf;
      available: true;
      direction: KeyLabel;
      slope: number;
      slope_strength: 'Strong' | 'Moderate' | 'Weak';
      upper: number;
      mid: number;
      lower: number;
      width: number;
      width_atr: number | null;
      width_trend: 'EXPANDING' | 'CONTRACTING' | 'STABLE';
      position: number | null;
      half: string | null;
      state: KeyLabel;
      validity: KeyLabel;
      distance_upper: number;
      distance_lower: number;
      distance_upper_atr: number | null;
      distance_lower_atr: number | null;
      touches_upper: number;
      touches_lower: number;
      age: number;
      age_unit: string;
      period: number;
      atr: number;
      closed_at: string;
    };
export type LiveChannelView = Extract<ChannelView, { available: true }>;

export type Spark = { candles: { t: string; o: number; h: number; l: number; c: number }[]; upper: [number, number]; lower: [number, number]; from: number };

export type ChannelEvent = { at: string; event: string; level: number; result: string; tf: ChannelTf };

export type ChannelDetail =
  | { available: false; reason: string; views: Record<ChannelTf, ChannelView> }
  | {
      available: true;
      tf: ChannelTf;
      price: number;
      view: LiveChannelView;
      views: Record<ChannelTf, ChannelView>;
      alignment: { aligned: number; total: number; direction: string | null };
      context: {
        parent_tf: ChannelTf | null;
        parent: LiveChannelView | null;
        position_in_parent: number | null;
        next_level: number;
        next_level_role: 'Resistance' | 'Support';
        next_event: string;
        invalidation: number | null;
      };
      scenarios: { continue: number; breakout: number; reversal: number };
      stats: {
        avg_width: number;
        min_width: number;
        max_width: number;
        avg_slope: number;
        touches: number;
        touches_upper: number;
        touches_lower: number;
        breakout_attempts: number;
        successful_breakouts: number;
        false_breakouts: number;
        atr: number;
      };
      key_levels: {
        upper: number;
        upper_ext_1: number;
        upper_ext_2: number;
        mid: number;
        lower: number;
        lower_ext_1: number;
        lower_ext_2: number;
        invalidation: number | null;
        atr: number;
        to_upper: number;
        to_lower: number;
        to_upper_atr: number | null;
        to_lower_atr: number | null;
      };
      lines: ChannelLines;
      events: ChannelEvent[];
      sparks: Record<ChannelTf, Spark | null>;
    };

type Instrument = { symbol: string; base: string; quote: string; asset: 'Forex' | 'Commodity'; digits: number | null };

export type BreakoutRow = Instrument & {
  tf: EventTf;
  direction: Direction;
  label: string;
  at: string;
  level: number;
  close: number;
  confirmed: boolean;
  failed: boolean;
  status: KeyLabel;
  retest: KeyLabel;
  retest_now: number;
  result_pips: number | null;
  distance_pips: number | null;
  distance_atr: number | null;
  mfe_atr: number | null;
};

export type SetupCandidate = Instrument & {
  tf: EventTf;
  state: 'Testing' | 'Approaching';
  boundary: 'UPPER' | 'LOWER';
  position: number;
  distance_atr: number | null;
  quality: KeyLabel;
  score: number;
  expected: 'Breakout' | 'Rejection';
};

export type RetestRow = Pick<Instrument, 'symbol' | 'base' | 'quote' | 'digits'> & {
  tf: EventTf;
  direction: Direction;
  retest_now: number;
  distance_pips: number | null;
  distance_atr: number | null;
  status: KeyLabel;
  retest: KeyLabel;
  at: string;
};

export type TitRow = Instrument & {
  layer: string;
  tf: EventTf;
  setup_type: string;
  direction: 'UPTREND' | 'DOWNTREND';
  maturity: number;
  quality: number;
  status: KeyLabel;
};

export type ChannelRow = Instrument & {
  name: string;
  price: number | null;
  available: boolean;
  reason?: string;
  channels?: Record<ChannelTf, { direction: string; position: number | null; state: string } | null>;
};

export type ChannelPayload = {
  meta: ScannerMeta & { channel_settings: Record<string, unknown> };
  counts: {
    events_7d: number;
    events_24h: number;
    breakouts_7d: number;
    retest_in_progress: number;
    confirmed: number;
    failed: number;
    high_probability: number;
    tit_active: number;
    analysed: number;
    symbols: number;
  };
  rows: ChannelRow[];
  breakouts: BreakoutRow[];
  candidates: SetupCandidate[];
  retests: RetestRow[];
  stats: {
    total: number;
    bullish: number;
    bearish: number;
    confirmed: number;
    failed: number;
    retest_pending: number;
    retest_in_progress: number;
    avg_move_atr: number | null;
    success_rate: number | null;
  };
  tit: TitRow[];
};

export type BreakoutEvent = BreakoutRow & {
  bar_at: string;
  retest_at: string | null;
  retest_bar_at: string | null;
  retest_level: number | null;
  completed_at: string | null;
  failed_at: string | null;
  mfe: number;
  mfe_at: string | null;
  mfe_price: number | null;
  closes_beyond: number;
  body_beyond_atr: number | null;
};

export type BreakoutDetail =
  | { available: false; tf: EventTf; reason: string; related: { tf: EventTf; state: KeyLabel; direction: KeyLabel }[] }
  | {
      available: true;
      tf: EventTf;
      event: BreakoutEvent;
      lines: ChannelLines;
      marks: {
        breakout: { at: string; price: number };
        retest: { at: string; price: number } | null;
        continuation: { at: string; price: number } | null;
        boundary: { at: string; price: number };
      };
      details: {
        type: string;
        level: number;
        break_candle: string;
        close_side: string;
        body_acceptance: boolean;
        retest_level: number;
        retest: KeyLabel;
        retest_candle: string | null;
        follow_through_atr: number | null;
        follow_through_pips: number;
        valid_structure: boolean;
        valid_note: string;
        next_objective: number;
        invalidation: number;
      };
      lifecycle: { label: string; done: boolean; current?: boolean; at: string | null }[];
      related: { tf: EventTf; state: KeyLabel; direction: KeyLabel }[];
      takeaway: string;
    };

export type TitLayer =
  | { id: string; tf: EventTf; available: false; layer_dir: 0 }
  | {
      id: string;
      tf: EventTf;
      available: true;
      layer_dir: -1 | 0 | 1;
      trend: KeyLabel;
      state: KeyLabel;
      position: number | null;
      half: string | null;
      alignment: string;
    };

export type TitView =
  | { available: false; reason: string; layers: TitLayer[] }
  | {
      available: true;
      parent: { layer: string; tf: EventTf; direction: 'UPTREND' | 'DOWNTREND'; position: number | null; state: KeyLabel; validity: KeyLabel };
      layers: TitLayer[];
      price: number;
      state: KeyLabel;
      tit_layer?: string;
      summary: string;
      countertrend: null | {
        layer: string;
        tf: EventTf;
        type: string;
        direction: KeyLabel;
        phase: string;
        maturity: number;
        position: number | null;
        half: string | null;
        distance_lower: number;
        distance_upper: number;
        distance_lower_atr: number | null;
        distance_upper_atr: number | null;
        rejoin_level: number;
        expected_bars: [number, number] | null;
        rejoin_score: number;
        invalidation: number;
        exec_tf: EventTf;
        exec_layer: string;
      };
      setup: null | {
        type: string;
        direction: string;
        direction_label: string;
        zone: [number, number];
        objective_1: number;
        objective_1_label: string;
        objective_2: number;
        objective_2_label: string;
        invalidation: number;
        invalidation_label: string;
        ratio: number | null;
        quality: number;
        status: KeyLabel;
      };
      quality: { score: number; label: string } | null;
      next_event?: { label: string; bars: [number, number] | null };
      lifecycle: { label: string; done: boolean }[];
      takeaways: string[];
      charts?: { L1: EventTf; CT: EventTf; EXEC: EventTf };
    };

export type ChannelSymbolDetail =
  | { meta: ChannelPayload['meta']; available: false; summary: ChannelRow }
  | {
      meta: ChannelPayload['meta'];
      available: true;
      summary: ChannelRow;
      channel: ChannelDetail;
      breakout: BreakoutDetail;
      tit: TitView;
      tf_lines: Record<ChannelTf, ChannelLines | null>;
    };

export type Direction = 'Bullish' | 'Bearish' | 'Neutral';
export type AlertKind = 'BOS + BTL' | 'BOS' | 'BTL' | 'DEVELOPING' | 'MONITORING';
export type ChartTf = 'W' | 'H8' | 'H1' | 'M30';
export type KL = { key: string; label: string };

export type Candle = { t: string; o: number; h: number; l: number; c: number };
export type Point = [string, number];

export type Alert = {
  symbol: string;
  base: string;
  quote: string;
  kind: AlertKind;
  direction: Direction | null;
  priority: number;
  at: string | null;
  levels: { bos?: number; btl?: number };
  closed_bar_proof: string[];
  closed_bar: boolean;
  analysis_id: string | null;
  digits: number;
};

export type H8BosBtlPayload = {
  meta: {
    mt5_connected: boolean;
    last_cycle_at: string | null;
    stale: boolean;
    stale_reason: string | null;
    analysis_only: boolean;
    h8bb_settings: Record<string, unknown>;
  };
  counts: { scanned: number; total: number } & Record<AlertKind, number>;
  alerts: Alert[];
};

export type BreakPart = {
  kind: 'BOS' | 'BTL';
  direction: Direction;
  bar_open: string;
  at: string;
  close: number;
  level: number;
  level_now?: number;
  strength_atr: number | null;
  invalidation: number;
  swing: { t: string; price: number } | null;
  line: Point[] | null;
  proof: string;
};

export type H8Event = {
  kind: 'BOS + BTL' | 'BOS' | 'BTL';
  direction: Direction;
  at: string;
  bar_open: string;
  close: number;
  break_strength_atr: number;
  retest: [number, number];
  invalidation: number;
  retest_key: string;
  bos: BreakPart | null;
  btl: BreakPart | null;
  analysis_id: string;
};

export type Developing = { event: 'BOS' | 'BTL'; direction: Direction; level: number; basis: string; detail: string };

export type Weekly = {
  available: boolean;
  reason?: string;
  direction?: Direction;
  state?: string;
  fast?: number;
  signal?: number;
  position_pct?: number | null;
  position_label?: string | null;
  fractal_state?: string | null;
  interpretation?: string;
  active_high?: number | null;
  active_low?: number | null;
  fractals?: { t: string; price: number; kind: 'HIGH' | 'LOW'; confirmed: boolean }[];
  sch?: { t: string; fast: number; signal: number }[];
};

export type SwingLabel = { t: string; price: number; label: string; kind?: 'HIGH' | 'LOW' };

export type H8BosBtlDetail = {
  meta: H8BosBtlPayload['meta'];
  available: boolean;
  reason?: string;
  symbol: string;
  name: string;
  digits: number;
  price: number | null;
  price_at: string | null;
  summary: Alert;
  kind: AlertKind;
  direction: Direction;
  event: H8Event | null;
  developing: Developing | null;
  retest_status: KL | null;
  h8: {
    structure: string;
    direction: Direction;
    last_closed: string;
    last_close: number;
    channel: { upper: Point[]; lower: Point[]; broken: boolean } | null;
    swings: { t: string; price: number; kind: 'HIGH' | 'LOW' }[];
    pending: {
      swing_high: number | null;
      swing_low: number | null;
      support: { anchors: Point[]; level: number } | null;
      resistance: { anchors: Point[]; level: number } | null;
    };
  };
  h1: { direction: Direction; structure: string; status: KL; labels: SwingLabel[]; sequence?: SwingLabel[] };
  m30: { direction: Direction; structure: string; status: KL; markers: SwingLabel[] };
  weekly: Weekly;
  mtf: { tf: string; structure: string; direction: Direction | null; status: string | null }[];
  evidence: { tf: string; label: string; detail: string | null; confirmed: boolean | null }[];
  scenarios: { key: string; title: string; detail: string }[];
  candles: Record<ChartTf, Candle[]>;
};

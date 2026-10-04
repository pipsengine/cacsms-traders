export type KeyLabel = { key: string; label: string };

export type ScannerStatusKey = 'HIGH_INSPECTION' | 'WATCHING' | 'NEUTRAL' | 'EXCLUDED';

export type StructureEvent = KeyLabel | null;

export type Structure = KeyLabel & {
  timeframe?: string;
  swing_high?: number;
  prev_swing_high?: number;
  swing_low?: number;
  prev_swing_low?: number;
  swing_high_at?: string;
  swing_low_at?: string;
  event?: StructureEvent;
  agrees_with_strength?: boolean | null;
};

export type Channel = KeyLabel & {
  upper?: number;
  mid?: number;
  lower?: number;
  position?: number;
  slope_pct_per_bar?: number;
  direction?: 'ASCENDING' | 'DESCENDING' | 'FLAT';
  period?: number;
};

export type Volatility = KeyLabel & {
  atr?: number;
  ratio?: number;
  trend?: 'EXPANDING' | 'CONTRACTING' | 'STABLE';
  atr_change_pct?: number;
};

export type Alignment = KeyLabel & {
  aligned: number;
  total: number;
  pct: number;
  direction: 'BASE' | 'QUOTE' | 'NONE';
};

export type ScannerStrength = {
  differential: number | null;
  base_score: number | null;
  quote_score: number | null;
  relationship: KeyLabel | null;
  alignment: Alignment | null;
  base_class: KeyLabel | null;
  quote_class: KeyLabel | null;
};

export type ScoreComponents = Record<'strength' | 'structure' | 'channel' | 'volatility' | 'alignment', number | null>;

export type ScannerRow = {
  rank: number;
  symbol: string;
  base: string;
  quote: string;
  name: string;
  status: KeyLabel & { key: ScannerStatusKey };
  score: number | null;
  reasons: string[];
  excluded_reason?: string;
  price?: number;
  price_at?: string | null;
  price_live?: boolean;
  quote_error?: string | null;
  digits?: number;
  change_24h?: number | null;
  change_24h_pct?: number | null;
  day_high?: number | null;
  day_low?: number | null;
  day_range_basis?: 'CURRENT_D1' | 'LAST_CLOSED_D1';
  spread_points?: number | null;
  description?: string | null;
  strength?: ScannerStrength;
  structure?: Structure;
  channel?: Channel;
  volatility?: Volatility;
  score_components?: ScoreComponents;
  session?: string;
};

export type ScannerSettings = {
  status: { key: ScannerStatusKey; label: string; min: number }[];
  weights: Record<string, number>;
  channel_period: number;
  atr_period: number;
  [k: string]: unknown;
};

export type ScannerMeta = {
  engine_state: 'STARTING' | 'SYNCING' | 'READY' | 'MT5_DISCONNECTED' | 'ERROR';
  engine_error: string | null;
  mt5_connected: boolean;
  mt5_server: string | null;
  cycle_id: number;
  last_cycle_at: string | null;
  quotes_at: string | null;
  instruments_total: number;
  instruments_scanned: number;
  fx_pairs: number;
  strength_as_of: string | null;
  strength_live: boolean | null;
  strength_stale_reason: string | null;
  currencies: number;
  stale: boolean;
  stale_reason: string | null;
  closed_bar_analysis: boolean;
  settings: ScannerSettings;
  analysis_only: true;
};

export type ScannerCounts = Record<ScannerStatusKey, number>;

export type ScannerPayload = { meta: ScannerMeta; counts: ScannerCounts; rows: ScannerRow[] };

export type ScannerInstrument = ScannerRow & {
  structures?: (Structure & { timeframe: string })[];
  strength_timeframes?: Record<string, number> | null;
};

export type ScannerDetailPayload = { meta: ScannerMeta; instrument: ScannerInstrument };

export type Candle = { t: string; o: number; h: number; l: number; c: number };

export type CandlesPayload = { symbol: string; timeframe: string; closed_only: true; candles: Candle[] };

export type ChartTimeframe = 'M5' | 'M15' | 'H1' | 'H8' | 'D1' | 'W' | 'MN';

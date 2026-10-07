export type Direction = 'BULLISH' | 'BEARISH' | 'RANGE';
export type TimePoint = [string, number];

export type RunLog = { at: string; state: string; message: string };
export type RunSummary = {
  id: string;
  analysis_date: string;
  origin: 'LIVE' | 'REPLAY';
  state: string;
  attempts: number;
  snapshot_id: string | null;
  close_at: string;
  engine_version: string;
  symbols_total: number;
  symbols_published: number;
  symbols_failed: number;
  symbols_insufficient: number;
  qualified: number;
  started_at: string | null;
  published_at: string | null;
  monitored_at: string | null;
  evaluated_at: string | null;
  next_retry_at: string | null;
  error: string | null;
  log: RunLog[];
};

export type SessionWindow = { key: 'ASIAN' | 'LONDON' | 'NEW_YORK'; label: string; start: string; end: string };
export type Schedule = {
  now: string;
  analysis_date: string;
  close_at: string;
  next_close_at: string;
  next_run_at: string;
  seconds_to_next_run: number;
  active_session: string | null;
  sessions: SessionWindow[];
  timezone: string;
};

export type SystemAction = { key: 'WATCH' | 'WAIT' | 'PREPARE' | 'AUTHORIZE' | 'IGNORE'; label: string; detail: string };

export type OutlookRow = {
  symbol: string;
  status: string;
  qualified: boolean;
  opportunity_rank: number | null;
  opportunity_score: number | null;
  expected_direction: Direction | null;
  regime: string | null;
  confidence: number | null;
  reason: string | null;
  system_action: SystemAction | null;
  monitor_status: string | null;
  price: number | null;
  digits: number;
  late: boolean | null;
};

export type LatestPayload = {
  schedule: Schedule;
  run: RunSummary | null;
  current: RunSummary | null;
  stale: boolean;
  rows: OutlookRow[];
  opportunities: OutlookRow[];
  engine_version: string;
};

export type Evidence = {
  id: string;
  key: string;
  source: string;
  source_key: string;
  tf: string;
  role: 'trend' | 'reaction' | 'reversal' | 'breakout' | 'range';
  sign: number;
  weight: number;
  title: string;
  detail: string;
  price: number | null;
  at: string | null;
};
export type EvidenceRef = { id: string; vote: number; title: string; source: string; tf: string };

export type Level = { price: number; label: string; source: string; tf: string; basis?: string; confluence?: string[]; evidence_key: string | null };
export type Erz = {
  lo: number;
  hi: number;
  mid: number;
  basis: string;
  sources: string[];
  evidence_keys: string[];
  price_inside: boolean;
  distance_atr: number | null;
  label: string;
};
export type SeqStep = { key: string; step: number; label: string; condition: Record<string, unknown> };

export type Scenario = {
  key: string | null;
  label: string;
  direction: string | null;
  probability: number;
  summary: string;
  key_trigger?: string;
  trigger_evidence?: string | null;
  targets?: Level[];
  invalidation: { price: number | null; label: string };
  erz?: Erz;
  range?: [number, number];
  sequence?: SeqStep[];
  path: TimePoint[];
  evidence_for: EvidenceRef[];
  evidence_against: EvidenceRef[];
};

export type Hypothesis = {
  key: string;
  dir: number;
  family: string;
  label: string;
  applicable: boolean;
  excluded_reason: string | null;
  score?: number;
  probability?: number;
  evidence_for?: EvidenceRef[];
  evidence_against?: EvidenceRef[];
};

export type KeyLevelRow = {
  type: 'Support' | 'Resistance';
  price: number;
  label: string;
  tf: string;
  source: string;
  importance: 'High' | 'Medium' | 'Low';
  distance_atr: number | null;
  liquidity: boolean;
};
export type KeyZone = { zone: string; from: number; to: number; type: string; width_atr: number | null; strength: string; status: string };
export type MarkPoint = { type: string; price: number; lo?: number; hi?: number; label: string; description: string; tone: string };
export type MtfRow = {
  tf: string;
  available: boolean;
  state?: string;
  direction?: string;
  dir?: number;
  position?: number;
  zone?: string;
  lower?: number;
  upper?: number;
  validity?: string;
  with_bias?: boolean;
};

export type Annotation = {
  id: string;
  type: string;
  group: string;
  tf: string;
  label: string;
  tone: string;
  source: string;
  evidence_key: string | null;
  detail: string;
  price?: number;
  lo?: number;
  hi?: number;
  at?: string;
  from?: string | null;
  side?: string;
  status?: string;
  dir?: string;
  failed?: boolean;
  dashed?: boolean;
  points?: TimePoint[];
  lines?: { upper: [TimePoint, TimePoint]; mid: [TimePoint, TimePoint]; lower: [TimePoint, TimePoint] };
};

export type SummaryLine = { tone: 'ok' | 'warn' | 'fail'; text: string; evidence_id: string };
export type SessionPlan = SessionWindow & { badge: string; bias: string | null; plan: string };

export type MonitorStep = { key: string; step: number; label: string; done: boolean; at: string | null; unavailable?: boolean };
export type Monitoring = {
  status: string;
  observed_at: string;
  price: number | null;
  steps?: MonitorStep[];
  invalidated_at?: string | null;
  system_action?: SystemAction;
};

export type DataQuality = {
  score: number;
  status: string;
  checks: { tf: string; bars: number; last_close_at: string | null; complete: boolean; fresh: boolean; note: string }[];
};

export type Outlook = {
  outlook_id: string;
  run_id: string;
  origin: string;
  published_at: string;
  late?: boolean;
  analysis_date: string;
  snapshot_id: string;
  symbol: string;
  digits: number;
  status: string;
  reason?: string;
  price: number;
  anchor: string;
  engine_version: string;
  regime: { key: string; label: string; reason: string };
  htf_bias: { key: string; label: string; score: number };
  expected_direction: Direction;
  expected_next_move: { label: string; path: string; target_zone: string };
  phase: { title: string; subtitle: string };
  current_status: { key: string; title: string; detail: string };
  timeframe_focus: string[];
  primary_scenario: Scenario;
  alternative_scenario: Scenario;
  range_scenario: Scenario;
  scenario_conditions: { condition: string; primary: boolean; alternative: boolean; range: boolean | null }[];
  hypotheses: Hypothesis[];
  confidence: {
    primary: number;
    bullish: number;
    bearish: number;
    range: number;
    raw: { bullish: number; bearish: number; range: number };
    calibration: { method: string; raw: number; bucket: string; samples: number; hit_rate: number | null; applied: boolean; calibrated?: number };
    margin: number;
  };
  uncertainty: number;
  evidence: Evidence[];
  evidence_for: EvidenceRef[];
  evidence_against: EvidenceRef[];
  key_drivers: { id: string; title: string; detail: string; source: string; tf: string }[];
  erz: Erz;
  targets: Level[];
  invalidation: Level;
  reward_risk: number | null;
  supports: KeyLevelRow[];
  resistances: KeyLevelRow[];
  liquidity: KeyLevelRow[];
  key_levels: KeyLevelRow[];
  key_zones: KeyZone[];
  mark_points: MarkPoint[];
  channels: MtfRow[];
  fractals: { hierarchy: unknown[]; clusters: unknown };
  bos_choch: Record<string, unknown>;
  tit: Record<string, unknown>;
  trend: Record<string, unknown> | null;
  strength: { differential: number; alignment_pct: number | null; as_of: string; label?: string } | null;
  supertrend: Record<string, { available: boolean; direction: number; line: number }>;
  volatility: { atr?: number; key?: string; label?: string } | null;
  range: Record<string, unknown> | null;
  confirmation_sequence: SeqStep[];
  expected_path: TimePoint[];
  session_plan: SessionPlan[];
  smart_summary: Record<'technical' | 'structure' | 'channel' | 'context', SummaryLine[]>;
  conclusion: string;
  opportunity: { score: number; qualified: boolean; disqualifiers: string[]; components: Record<string, number | null> };
  opportunity_score: number | null;
  opportunity_rank?: number;
  qualified: boolean;
  system_action: SystemAction;
  system_action_live?: SystemAction;
  data_quality: DataQuality;
  chart_annotations: Annotation[];
  handoff: string;
  monitoring?: Monitoring | null;
};

export type SymbolPayload = { run: RunSummary; schedule: Schedule; outlook: Outlook };

export type Evaluation = {
  outcome: 'WIN' | 'LOSS' | 'NEUTRAL';
  scenario_result: string;
  direction_correct: number | null;
  target1_hit: boolean;
  target2_hit: boolean;
  invalidated: boolean;
  erz_touched: boolean;
  move_pct: number | null;
  move_atr?: number | null;
  close?: number;
  high?: number;
  low?: number;
  realised_direction?: string;
};

export type HistoryRow = {
  outlook_id: string;
  analysis_date: string;
  origin: 'LIVE' | 'REPLAY';
  status: string;
  qualified: boolean;
  direction: Direction | null;
  confidence: number | null;
  regime: string | null;
  regime_label: string | null;
  engine_version: string;
  price: number | null;
  digits: number;
  primary: { label: string; direction: string; probability: number };
  alternative: { label: string; direction: string; probability: number };
  range: { label: string; probability: number };
  erz: Erz | null;
  targets: Level[] | null;
  invalidation: Level | null;
  expected_next_move: { label: string; path: string; target_zone: string } | null;
  snapshot_id: string;
  published_at: string;
  reason: string | null;
  opportunity_score: number | null;
  late: boolean | null;
  evaluation: Evaluation | null;
};

export type Performance = {
  samples: number;
  decided: number;
  wins: number;
  losses: number;
  accuracy: number | null;
  direction_accuracy: number | null;
  avg_confidence: number | null;
  target1_rate: number | null;
  target2_rate: number | null;
  invalidation_rate: number | null;
  erz_touch_rate: number | null;
  brier: number | null;
  false_positives: number;
  false_negatives: number;
  buckets: { bucket: string; n: number; hit_rate: number | null; expected: number; avg_confidence: number | null }[];
  by_scenario: Record<string, number>;
  by_direction: Record<string, { n: number; wins: number; losses: number; accuracy: number | null }>;
};

export type HistoryPayload = {
  symbol: string;
  days: number;
  rows: HistoryRow[];
  performance: { window_days: number; since: string; all: Performance; qualified: Performance };
};

export type VCandle = { t: string; o: number; h: number; l: number; c: number; v: number };
export type MtfPayload = { symbol: string; channels: MtfRow[]; candles: Record<string, VCandle[]>; annotations: Annotation[] };

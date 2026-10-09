export type StageKey =
  | 'MARKET_DATA'
  | 'INTELLIGENCE'
  | 'SCANNER'
  | 'STRUCTURE'
  | 'CHANNEL'
  | 'OPPORTUNITY'
  | 'CONFIRMATION'
  | 'RISK'
  | 'EXECUTION'
  | 'MANAGEMENT'
  | 'LEARNING';

export type StageStatus =
  | 'RUNNING'
  | 'WAITING'
  | 'BLOCKED'
  | 'STALE'
  | 'DEGRADED'
  | 'ERROR'
  | 'IDLE'
  | 'PENDING'
  | 'SYNCHRONIZING'
  | 'OFFLINE';

// Stage metrics/detail differ per stage; the backend documents each key it writes.
export type Metrics = Record<string, unknown>;

export type Ribbon = {
  system_status: 'STARTING' | 'RUNNING' | 'STALLED' | 'HALTED' | 'ERROR';
  safety_status: 'NORMAL' | 'DEGRADED' | 'CRITICAL' | 'HALTED' | 'UNKNOWN';
  operating_mode: string;
  execution: string;
  provider: string | null;
  provider_label: string | null;
  provider_connection: 'CONNECTED' | 'SYNCHRONIZING' | 'OFFLINE' | 'DISCONNECTED';
  data_readiness?: string;
  connections_label?: string;
  strength_pairs_loaded?: number;
  strength_engine_state?: string;
  provider_heartbeat: string | null;
  account_id: string | null;
  workers_online: number;
  workers_total: number;
  server_time: string;
  last_successful_cycle: string | null;
  last_cycle_status: string | null;
  last_cycle_origin: string | null;
  next_cycle_at: string | null;
  cadence: 'ON_DEMAND' | 'WORKER';
  engine_running: boolean;
  data_as_of: string | null;
  engine_version: string;
};

export type StageSummary = {
  key: StageKey;
  number: number;
  label: string;
  color: string;
  status: StageStatus;
  current_operation: string | null;
  next_operation: string | null;
  processed: number;
  active: number;
  waiting: number;
  errors: number;
  blockers: string[];
  metrics: Metrics;
  provider?: string | null;
  last_update: string | null;
  last_success_at: string | null;
  stale: boolean;
};

export type SafetyCheck = { key: string; label: string; status: 'OK' | 'WARN' | 'CRITICAL' | 'HALT' | string; detail: string };

export type Worker = {
  worker: string;
  label: string;
  state: string;
  online: boolean;
  heartbeat_at: string | null;
  last_success_at: string | null;
  last_error: string | null;
  age_seconds: number | null;
};

export type Cycle = {
  id: string;
  origin: string;
  status: string;
  operating_mode: string;
  safety_status: string;
  provider: string | null;
  snapshot_id: string | null;
  scanner_cycle_id: string | null;
  data_as_of: string | null;
  started_at: string;
  completed_at: string | null;
  duration_ms: number | null;
  error: string | null;
  counts: Record<string, number>;
};

export type Overview = {
  ribbon: Ribbon;
  stages: StageSummary[];
  safety: { status: string; checks: SafetyCheck[]; blockers: string[]; warnings: string[]; market_open: boolean | null };
  workers: { online: number; total: number; items: Worker[] };
  cycle: Cycle | null;
  enabled: boolean;
  settings: Record<string, number>;
};

export type Transition = {
  id: string;
  entity_type: 'OPPORTUNITY' | 'CHANNEL' | string;
  entity_id: string;
  symbol: string | null;
  timeframe: string | null;
  from_stage: string | null;
  from_state: string | null;
  to_stage: string | null;
  to_state: string;
  reason_code: string;
  detail: string | null;
  provider: string | null;
  evidence_at: string;
  cycle_id: string | null;
  created_at: string;
  evidence: Record<string, unknown>;
};

export type Opportunity = {
  id: string;
  symbol: string;
  digits: number;
  direction: 'BULLISH' | 'BEARISH';
  type: string;
  type_label: string;
  tit_level: string | null;
  stage: StageKey;
  stage_label: string | null;
  stage_number: number | null;
  stage_color: string | null;
  state: string;
  status: 'ACTIVE' | 'CLOSED';
  outcome: string | null;
  parent_tf: string | null;
  trigger_tf: string | null;
  entry_lo: number | null;
  entry_hi: number | null;
  invalidation: number | null;
  target_1: number | null;
  target_2: number | null;
  current_price: number | null;
  price_at: string | null;
  confidence: number | null;
  quality: number | null;
  reward_risk: number | null;
  next_condition: string | null;
  reason_code: string | null;
  provider: string | null;
  blockers: string[];
  origin_at: string | null;
  stage_entered_at: string | null;
  evaluated_through: string | null;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
};

export type ChannelLines = Record<'upper' | 'mid' | 'lower', [[string, number], [string, number]]>;

/** Display geometry for a chart timeframe. Present for every inclusive timeframe, not only a stored lineage. */
export type SymbolChart = {
  symbol: string;
  timeframe: string;
  candles: { t: string; o: number; h: number; l: number; c: number; v?: number }[];
  channel: {
    symbol: string;
    timeframe: string;
    state: string;
    direction: string | null;
    upper: number | null;
    mid: number | null;
    lower: number | null;
    width: number | null;
    width_atr: number | null;
    touches_upper: number | null;
    touches_lower: number | null;
    age_bars: number | null;
    quality: number | null;
    digits: number;
    lines: ChannelLines | null;
  } | null;
};

export type Channel = {
  id: string;
  symbol: string;
  timeframe: string;
  status: string;
  state: string;
  direction: string | null;
  validity: string | null;
  upper: number | null;
  mid: number | null;
  lower: number | null;
  width: number | null;
  width_atr: number | null;
  atr: number | null;
  position: number | null;
  touches_upper: number | null;
  touches_lower: number | null;
  quality: number | null;
  age_bars: number | null;
  erz_lo: number | null;
  erz_hi: number | null;
  break_direction: string | null;
  break_level: number | null;
  break_at: string | null;
  retest_at: string | null;
  continuation_at: string | null;
  last_touch_at: string | null;
  last_touch_side: string | null;
  state_entered_at: string | null;
  started_at: string | null;
  last_bar_at: string | null;
  closed_at: string | null;
  provider: string | null;
  updated_at: string | null;
  digits: number;
  lines: ChannelLines | null;
  erz_band: { lower: [string, number][]; upper: [string, number][] } | null;
  ref: string | null;
};

export type AlertItem = {
  id: string;
  event_type: string;
  symbol: string;
  timeframe: string | null;
  direction: string | null;
  status: string;
  status_reason: string | null;
  event_time: string | null;
  detected_at: string;
  sent_at: string | null;
  level: number | null;
};

export type ChannelQueueItem = {
  channel_id: string;
  symbol: string;
  timeframe: string;
  state: string;
  task: string;
  next_at: string | null;
  status: 'Due' | 'Pending';
};

export type StageDetail = {
  key: StageKey;
  number: number;
  label: string;
  color: string;
  available: boolean;
  status: StageStatus;
  current_operation: string | null;
  next_operation: string | null;
  processed: number;
  active: number;
  waiting: number;
  errors: number;
  metrics: Metrics;
  blockers: string[];
  detail: Record<string, unknown>;
  provider: string | null;
  last_update: string | null;
  last_success_at: string | null;
  last_successful_cycle: string | null;
  next_cycle_at: string | null;
  filters: { symbol: string | null; timeframe: string | null; provider: string | null };
  provider_mismatch?: boolean;
  symbols: string[];
  detections: Transition[];
  channels?: Channel[];
  alerts?: { items: AlertItem[]; today: Record<string, number> };
  lifecycle_states?: string[];
  opportunities?: Opportunity[];
};

export type OpportunitySummary = {
  total: number;
  created_today: number;
  high_potential: number;
  high_potential_min_confidence: number;
  awaiting_conditions: number;
  ready_for_risk: number;
  authorised: number;
  invalidated: number;
  ranking_note: string;
};

export type OpportunitiesResponse = {
  rows: Opportunity[];
  counts: { active: number; by_stage: Record<string, number>; by_type: Record<string, number> };
  types: Record<string, string>;
  summary: OpportunitySummary;
};

export type HistoryResponse = { opportunity: Opportunity & { evidence: Record<string, unknown> }; transitions: Transition[] };

export type ChannelChart = {
  channel: Channel;
  candles: { t: string; o: number; h: number; l: number; c: number; v: number }[];
  events: Transition[];
};

export type StageFilters = { symbol: string; timeframe: string; provider: string };

export type PortfolioAccount = {
  id: string;
  name: string | null;
  number: string | null;
  broker: string | null;
  server: string | null;
  environment: string | null;
  currency: string;
  balance: number | null;
  equity: number | null;
  margin: number | null;
  free_margin: number | null;
  leverage: string | null;
  floating_pnl: number | null;
  floating_pnl_basis: string;
  margin_used_pct: number | null;
  free_margin_pct: number | null;
  last_synced_at: string | null;
  connection_status: string | null;
  stale: boolean;
  source: string;
};

export type PortfolioView = {
  account: PortfolioAccount | null;
  limits: {
    max_open_positions: number | null;
    max_total_risk_pct: number | null;
    max_trade_risk_pct: number | null;
    max_daily_loss_pct: number | null;
    max_total_loss_pct: number | null;
    profit_target_pct: number | null;
    weekend_holding_allowed: boolean | null;
    max_concurrent: number;
    max_currency_exposure: number;
    min_reward_risk: number;
    min_confidence: number;
  };
  capacity: { used: number; limit: number; available: number | null; used_pct: number | null; basis: string };
  exposure: {
    basis: string;
    currencies: { currency: string; net_plans: number; share_pct: number }[];
    most_exposed: string | null;
    least_exposed: string | null;
    plans: number;
  };
  campaigns: { type: string; label: string; active_plans: number; shadow_plans: number; slot_share_pct: number | null; status: string; dollar_allocation: null }[];
  distribution: { type: string; label: string; plans: number; share_pct: number }[];
  decisions: {
    id: string;
    opportunity_id: string | null;
    at: string | null;
    symbol: string | null;
    direction: string | null;
    type: string | null;
    type_label: string | null;
    tit_level: string | null;
    state: string;
    reason_code: string | null;
    detail: string | null;
    rule: string | null;
    reward_risk: number | null;
    confidence: number | null;
    currency: string | null;
    position_size: null;
    stop_distance: null;
    position_size_note: string;
    shadow: boolean;
    broker_order: null;
  }[];
  decision_counts: Record<string, number>;
  outcomes: {
    closed_30d: number;
    resolved: number;
    hit_rate: number | null;
    avg_r: number | null;
    counts: Record<string, number>;
    profit_factor: null;
    sharpe: null;
    total_return_pct: null;
    max_drawdown_pct: null;
    daily_drawdown_pct: null;
    basis: string;
    by_type: Record<string, { closed: number; target_1: number; stopped: number }>;
  };
  equity_history: { points: { t: string | null; equity: number }[]; note: string };
  unavailable: string[];
  execution: string;
  execution_note: string;
};

export type ExecutionEvent = {
  id: string;
  at: string | null;
  symbol: string | null;
  direction: string | null;
  type: string | null;
  type_label: string | null;
  from_state: string | null;
  to_state: string | null;
  reason_code: string | null;
  detail: string | null;
  reference_price: number | null;
  record_class: 'SIMULATED';
  result: string;
  broker_order_id: null;
  volume: null;
  fill_price: null;
  slippage: null;
  latency_ms: null;
};

export type ShadowPlan = {
  id: string;
  symbol: string | null;
  direction: string | null;
  type: string | null;
  type_label: string | null;
  state: string | null;
  entry_lo: number | null;
  entry_hi: number | null;
  entry_reference: number | null;
  invalidation: number | null;
  target_1: number | null;
  target_2: number | null;
  current_price: number | null;
  price_at: string | null;
  price_status: 'SIMULATED' | 'STALE';
  unrealized_r: number | null;
  reward_risk: number | null;
  confidence: number | null;
  since: string | null;
  volume: null;
  broker_order_id: null;
  record_class: 'SIMULATED';
  order_status: 'NOT_SUBMITTED';
};

export type ExecutionBook = {
  mode: string;
  broker_submission: 'BLOCKED';
  execution_note: string;
  provider: string | null;
  last_cycle_at: string | null;
  broker: {
    orders_submitted: 0;
    fills: 0;
    rejections: 0;
    pending_orders: 0;
    open_positions: 0;
    basis: string;
  };
  shadow: {
    open_plans: number;
    blocked_today: number;
    blocked_30d: number;
    target_1: number;
    stopped: number;
    unresolved: number;
    basis: string;
  };
  plans: ShadowPlan[];
  events: ExecutionEvent[];
  daily: { day: string; blocked: number; resolved: number }[];
  unavailable: string[];
  r_basis: string;
};

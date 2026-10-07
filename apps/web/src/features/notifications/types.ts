export type AlertType = 'CHANNEL_BREAK' | 'CHANNEL_TOUCH' | 'BREAK_RETEST_CONTINUATION' | 'TIT_DETECTED' | 'AI_OUTLOOK_PUBLISHED';

export type AlertSettings = {
  email_enabled: boolean;
  alert_types: Record<AlertType, boolean>;
  timeframes: string[];
  symbols: string[];
  xauusd_enabled: boolean;
  touch_rearm_bars: number;
  cooldown_minutes: number;
  max_event_age_bars: number;
  max_attempts: number;
  updated_by: string | null;
  updated_at: string | null;
};

export type Recipient = {
  id: string;
  email: string;
  name: string | null;
  enabled: boolean;
  alert_types: AlertType[];
  created_at: string;
  updated_at: string;
};

export type SmtpTransport = {
  enabled: boolean;
  host: string;
  port: number;
  security: 'starttls' | 'ssl' | 'none';
  username: string;
  from_email: string;
  from_name: string;
  password_configured: boolean;
  password_source: 'database' | 'environment' | null;
  ready: boolean;
  problems: string[];
  vault_available: boolean;
  vault_error: string | null;
  env_defaults: Omit<SmtpTransport, 'password_configured' | 'password_source' | 'ready' | 'problems' | 'vault_available' | 'vault_error' | 'env_defaults' | 'overrides'>;
  overrides: string[];
};

export type TestResult = {
  status: 'SENT' | 'FAILED';
  at: string;
  error: string | null;
  error_kind: string | null;
  recipients?: string[];
};

export type SmtpHealth = {
  last_success_at?: string | null;
  last_failure_at?: string | null;
  last_error?: string | null;
  last_error_kind?: string | null;
  last_test?: TestResult | null;
};

export type NotificationStats = {
  last_sent_at: string | null;
  failed_total: number;
  failed_recent: number;
  sent_recent: number;
  pending: number;
  events_recent: number;
  suppressed_recent: number;
};

export type EmailOverview = {
  tenant_id: string;
  settings: AlertSettings;
  recipients: Recipient[];
  smtp: SmtpTransport;
  health: SmtpHealth;
  stats: NotificationStats;
  retry_minutes: number[];
  alert_types: { key: AlertType; label: string }[];
  timeframes: string[];
  symbols: string[];
  statuses: string[];
  can_manage: boolean;
  can_manage_smtp: boolean;
  analysis_only: boolean;
};

export type Delivery = {
  recipient_email: string;
  status: string;
  attempt_count: number;
  sent_at: string | null;
  failure_reason: string | null;
  next_attempt_at: string | null;
};

export type AlertEvent = {
  id: string;
  event_type: AlertType;
  symbol: string;
  timeframe: string;
  direction: string | null;
  provider: string;
  event_time: string;
  detected_at: string;
  price: number | null;
  level: number | null;
  tit_level: string | null;
  status: string;
  status_reason: string | null;
  attempt_count: number;
  sent_at: string | null;
  failure_reason: string | null;
  metadata: Record<string, unknown>;
  deliveries: Delivery[];
};

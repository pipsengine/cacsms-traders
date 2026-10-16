export type PropRules = {
  daily_loss_pct: number;
  max_loss_pct: number;
  drawdown_method?: string;
  daily_reference?: string;
  reset_timezone?: string;
  max_positions?: number;
  max_lot?: number;
  floating_loss_pct?: number;
  news_block_minutes?: number;
  weekend_holding?: boolean;
  automation_permitted?: boolean;
  permitted_strategies?: string[];
  profit_target_pct?: number;
  slippage_buffer_pct?: number;
  emergency_close?: boolean;
};

export type PropAccountRow = {
  id: string;
  firm: string;
  external_id: string;
  environment: string;
  lifecycle: string;
  phase: string;
  balance: number | null;
  equity: number | null;
  daily_pnl: number | null;
  daily_drawdown_pct: number | null;
  max_drawdown_pct: number | null;
  daily_loss_pct: number | null;
  max_loss_pct: number | null;
  profit_target_pct: number | null;
  progress_pct: number | null;
  days_left: number | null;
  status: string;
  protection: string | null;
  automation_confirmed: boolean;
  credential_configured: boolean;
};

export type PropOverview = {
  summary: {
    accounts: number;
    firms: number;
    evaluation: number;
    funded: number;
    equity: number | null;
    open_pnl: number | null;
    in_profit: number;
    compliant: boolean | null;
  };
  accounts: PropAccountRow[];
  firms: Array<{ id: string; name: string; version: number | null; rule_version_id: string | null; rules: PropRules }>;
};

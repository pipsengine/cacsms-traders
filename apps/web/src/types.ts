export type { Page } from './lib/routes';
import type { Page } from './lib/routes';
export type Health={
 application:string;api:string;database:string;
 market_data?:{active_provider:string|null;provider_status:string;market_data_ready?:boolean};
 mt5:{
  status:string;session_status?:string;adapter:string;message:string;
  terminal?:string;terminal_configured?:boolean;
  heartbeat_at?:string|null;last_connected_at?:string|null;last_error?:string|null;
  execution?:string;execution_enabled?:boolean;market_data_connected?:boolean;
 };
};
export type Summary={tenants:number;users:number;accounts:number;connections:number;mode:string};
export type Tenant={id:string;name:string;slug:string;status:string;reporting_currency:string;timezone:string};
export type AuthUser={
 id:string;username:string;display_name:string;email?:string;first_name?:string;last_name?:string;
 timezone?:string;preferred_currency?:string;is_platform_admin?:number;is_system_protected?:number;
 memberships:{tenant_id:string;tenant_name:string;role_name?:string}[];
};
export type TenantUser={
 id:string;username:string;email?:string;display_name:string;role_name?:string;timezone?:string;status:string;last_login_at?:string;
};
export type TradingAccount={
 id:string;account_name:string;account_number?:string;broker?:string;server?:string;
 environment:'DEMO'|'LIVE'|'PROP_FIRM';account_currency:string;balance:number;equity:number;
 free_margin?:number;margin?:number;last_synced_at?:string|null;
 connection_status:string;trading_enabled:number;autonomous_trading_enabled:number;
};
export type AuditEvent={
 id:string;action:string;entity_type?:string;entity_id?:string;created_at:string;user_id?:string;
};
export type Mt5LocalSettings={
 terminal_path?:string;login_type?:string;auto_reconnect?:boolean;heartbeat_interval_seconds?:number;
 session_status?:string;last_connected_at?:string|null;
};
export type Mt5Lifecycle={
 gateway_phase:string;
 market_sync_phase:string;
 overall_phase:string;
};
export type Mt5IntelligenceMeta={
 engine_state?:string;
 pairs_loaded?:number;
 pairs_total?:number;
 missing_pairs?:string[];
 symbols_resolved?:number;
 provider_status?:string;
 market_data_ready?:boolean;
 engine_error?:string|null;
 last_calculated_at?:string|null;
 closed_bar_status?:string;
 failed_candle_requests?:{symbol?:string;timeframe?:string;error_code?:string}[];
};
export type ConnectionsPayload={
 gateway:Health['mt5'] & {status:string;adapter:string;message:string} & Partial<Mt5Lifecycle>;
 settings?:Mt5LocalSettings;
 lifecycle?:Mt5Lifecycle;
 intelligence?:Mt5IntelligenceMeta|null;
 diagnostics?:{
  python_package:string;version?:string|null;hint?:string|null;
  terminal_launch_mode?:'WINDOWS_GATEWAY'|'WINDOWS_GATEWAY_REQUIRED';terminal_launch_supported?:boolean;bridge_connected?:boolean;
  terminal_auto_detect_path?:string|null;terminal_auto_detect_source?:string|null;
  terminal_candidates?:string[];terminal_running_processes?:string[];database_path?:string;
  terminal_auto_saved?:{path?:string;source?:string;persisted?:boolean};
  terminal_account?:{
    available?:boolean;login?:string;server?:string;name?:string;company?:string;
    currency?:string;trade_mode?:string;leverage?:number;error?:string;
  }|null;
  terminal_account_hint?:string;
 };
 connections:{
  id:string;account_name:string;account_number?:string;environment:string;adapter_type:string;status:string;
  terminal_path?:string;server_name?:string;account_server?:string;broker?:string;account_currency?:string;
 }[];
};

export type AppRouteState = { page: Page; tab?: string };

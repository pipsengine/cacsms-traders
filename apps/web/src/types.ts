export type Page='overview'|'tenants'|'users'|'accounts'|'connections'|'strength-matrix'|'system'|'audit'|'profile';
export type Health={application:string;api:string;database:string;mt5:{status:string;adapter:string;message:string}};
export type Summary={tenants:number;users:number;accounts:number;connections:number;mode:string};
export type Tenant={id:string;name:string;slug:string;status:string;reporting_currency:string;timezone:string};
export type AuthUser={
 id:string;username:string;display_name:string;email?:string;first_name?:string;last_name?:string;
 timezone?:string;preferred_currency?:string;is_platform_admin?:number;
 memberships:{tenant_id:string;tenant_name:string;role_name?:string}[];
};
export type TenantUser={
 id:string;username:string;email?:string;display_name:string;role_name?:string;timezone?:string;status:string;last_login_at?:string;
};
export type TradingAccount={
 id:string;account_name:string;account_number?:string;broker?:string;server?:string;
 environment:'DEMO'|'LIVE'|'PROP_FIRM';account_currency:string;balance:number;equity:number;
 connection_status:string;trading_enabled:number;autonomous_trading_enabled:number;
};
export type AuditEvent={
 id:string;action:string;entity_type?:string;entity_id?:string;created_at:string;user_id?:string;
};
export type ConnectionsPayload={
 gateway:{status:string;adapter:string;message:string};
 connections:{id:string;account_name:string;environment:string;adapter_type:string;status:string;terminal_path?:string;server_name?:string}[];
};

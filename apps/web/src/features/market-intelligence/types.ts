export type RelationshipState='DIVERGENCE'|'EQUILIBRIUM'|'CONVERGENCE'|'ROTATION'|'TRANSITIONING'|'UNCERTAIN';
export type InspectionPriority='CRITICAL'|'HIGH'|'NORMAL'|'LOW';
export interface StrengthRow{currency:string;timeframe:string;as_of:string;value:number;slope:number;velocity:number;acceleration:number;persistence:number;confidence:number;sample_count:number;quality:string}
export interface RelationshipRow{pair:string;timeframe:string;as_of:string;base_value:number;quote_value:number;gap:number;abs_gap:number;gap_velocity:number;gap_acceleration:number;persistence:number;state:RelationshipState;confidence:number;inspection_priority:InspectionPriority;reason_codes:string}
export interface QualityRow{symbol:string;timeframe:string;state:string;last_closed_at?:string;age_seconds?:number;missing_bars:number;reason?:string}

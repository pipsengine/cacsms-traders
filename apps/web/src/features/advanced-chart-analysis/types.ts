export type Candle={time:number;open:number;high:number;low:number;close:number;volume:number;closed:boolean};
export type Drawing={id:string;symbol:string;timeframe:string;kind:'horizontal'|'trendline'|'rectangle'|'text'|'fibonacci'|'channel';points:{time:number;price:number}[];color:string;label?:string};
export type Overlay={id:string;kind:'level'|'zone'|'event';price:number;price2?:number;label:string;color:string;source:string;confirmed:boolean};
export type Analysis={id:string;symbol:string;timeframe:string;title:string;notes:string;created_at:string};
export type Workspace={symbol:string;timeframe:string;indicators:string[];layers:string[];drawings:Drawing[];updated_at?:string|null;expected_updated_at?:string|null};
export type Quote={symbol:string;bid:number|null;ask:number|null;updated_at:string|null;stale:boolean;change_pct?:number|null};

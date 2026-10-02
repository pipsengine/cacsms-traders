import React from'react';import{CheckCircle2,AlertTriangle,Info}from'lucide-react';
export function PageHeader({title,subtitle,action}:{title:string;subtitle:string;action?:React.ReactNode}){return <div className="page-head"><div><h1>{title}</h1><p>{subtitle}</p></div>{action}</div>}
export function Card({children,className=''}:{children:React.ReactNode;className?:string}){return <section className={'card '+className}>{children}</section>}
export function Status({value}:{value:string}){const k=['ACTIVE','HEALTHY','CONNECTED','READY','DEMO_AUTONOMOUS'].includes(value)?'success':['DISCONNECTED','PAUSED','SHADOW','ANALYSIS_ONLY'].includes(value)?'neutral':['ERROR','EMERGENCY_STOP','SUSPENDED'].includes(value)?'danger':'warning';return <span className={'status '+k}><i/>{value.replaceAll('_',' ')}</span>}
export function Empty({title,text}:{title:string;text:string}){return <div className="empty"><Info size={22}/><b>{title}</b><p>{text}</p></div>}
export function Notice({title,text,tone='info'}:{title:string;text:string;tone?:'info'|'warning'}){return <div className={'notice '+tone}>{tone==='warning'?<AlertTriangle/>:<CheckCircle2/>}<div><b>{title}</b><span>{text}</span></div></div>}

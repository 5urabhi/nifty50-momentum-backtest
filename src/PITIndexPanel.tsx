import {useCallback, useEffect, useState} from 'react'
import {AlertTriangle, ArrowDownToLine, CalendarDays,
  Check, ChevronDown, Clock3, Database, FileClock, Info, LoaderCircle,
  RefreshCw, ShieldCheck} from 'lucide-react'

export type PITMode = 'nifty50_pit' | 'banknifty_pit'
export type MembershipPlan = {
  index_id:PITMode;index_name:string;asof_date:string;asof_members:string[]
  from_date:string;to_date:string;start_members:string[];end_members:string[]
  union_members:string[];union_count:number;start_count:number;end_count:number
  changes:Array<{effective_date:string;symbol:string;action:string;source:string;source_url:string}>
  change_count:number;resolved_count:number;unresolved_count:number
  unresolved:Array<{symbol:string;reason:string}>
  covered_through:string;first_date:string;source_url:string;source_commit:string
  official_corrections:Array<{symbol:string;corrected_effective:string;official_source:string}>
  warnings:string[]
}
type MembershipStatus = {
  available:boolean;first_date?:string;covered_through?:string;synced_utc?:string
  source?:string;source_csv?:string;source_commit?:string;limitations?:string[]
  corrections?:Array<{symbol:string;corrected_effective:string;official_source:string}>
  message?:string
}
type JobStatus = {id:string;status:string;error?:string}
type Props = {
  mode:PITMode;fromDate:string;toDate:string
  onToDate:(s:string)=>void;onPlan:(plan:MembershipPlan|null)=>void
  onSyncBusy:(busy:boolean)=>void
}
async function get<T>(path:string, init?:RequestInit):Promise<T>{
  const result=await fetch('/api'+path,init)
  if(!result.ok){
    let detail:unknown
    try{detail=(await result.json() as {detail:unknown}).detail}catch{/* no body */}
    throw new Error(typeof detail==='string'?detail:result.status+' '+result.statusText)
  }
  return result.json() as Promise<T>
}
function following(day:string){
  const d=new Date(day+'T12:00:00Z')
  d.setUTCDate(d.getUTCDate()+1)
  return d.toISOString().slice(0,10)
}
function previous(day:string){
  const d=new Date(day+'T12:00:00Z')
  d.setUTCDate(d.getUTCDate()-1)
  return d.toISOString().slice(0,10)
}
const readable=(day:string)=>new Date(day+'T12:00:00Z').toLocaleDateString('en-GB',{day:'2-digit',month:'short',year:'numeric'})

function exportCsv(name:string, rows:string[][]){
  // Export user-reviewable CSV instead of inventing any index membership.
  const escaped=rows.map(row=>row.map(value=>'"'+String(value).replaceAll('"','""')+'"').join(',')).join('\r\n')+'\r\n'
  const url=URL.createObjectURL(new Blob(['\uFEFF'+escaped],{type:'text/csv;charset=utf-8'}))
  const a=document.createElement('a')
  a.href=url;a.download=name;document.body.appendChild(a);a.click();a.remove()
  window.setTimeout(()=>URL.revokeObjectURL(url),1000)
}

export default function PITIndexPanel({mode,fromDate,toDate,onToDate,onPlan,onSyncBusy}:Props){
  const [status,setStatus]=useState<MembershipStatus|null>(null)
  const [asOf,setAsOf]=useState(fromDate)
  const [plan,setPlan]=useState<MembershipPlan|null>(null)
  const [loading,setLoading]=useState(false)
  const [syncId,setSyncId]=useState('')
  const [issue,setIssue]=useState('')
  const [showChanges,setShowChanges]=useState(false)
  const [showAll,setShowAll]=useState(false)
  const [showUnion,setShowUnion]=useState(false)
  const [showMissing,setShowMissing]=useState(true)
  const refresh=useCallback(async()=>{
    const next=await get<MembershipStatus>('/indices/status')
    setStatus(next)
    return next
  },[])
  useEffect(()=>{
    void refresh().catch(e=>setIssue(e instanceof Error?e.message:String(e)))
  },[refresh])
  useEffect(()=>{setAsOf(fromDate)},[fromDate,mode])
  // Preview the source-covered portion even when the requested end date is
  // newer. Do NOT authorize downloads with a silently shortened period:
  // only send a valid plan to the parent when the entire range is covered.
  const supportedEnd=status?.covered_through ? following(status.covered_through) : ''
  const endOutsideCoverage=Boolean(status?.available&&supportedEnd&&toDate>supportedEnd)
  useEffect(()=>{
    if(!status?.available||!supportedEnd){
      setPlan(null);onPlan(null)
      return
    }
    const previewEnd=toDate<supportedEnd?toDate:supportedEnd
    if(fromDate>=previewEnd){
      setPlan(null);onPlan(null);setIssue('')
      return
    }
    const previewAsOf=asOf<fromDate?fromDate:asOf>=previewEnd?previous(previewEnd):asOf
    const controller=new AbortController()
    setPlan(null);onPlan(null)
    setLoading(true);setIssue('')
    const params=new URLSearchParams({
      index_id:mode,from_date:fromDate,to_date:previewEnd,as_of_date:previewAsOf,
    })
    void get<MembershipPlan>('/indices/preview?'+params, {signal:controller.signal}).then(p=>{
      if(!controller.signal.aborted){
        setPlan(p)
        onPlan(toDate>previewEnd?null:p)
      }
    }).catch(e=>{
      if(!controller.signal.aborted){setPlan(null);onPlan(null);setIssue(e instanceof Error?e.message:String(e))}
    }).finally(()=>{if(!controller.signal.aborted)setLoading(false)})
    return()=>controller.abort()
  },[mode,fromDate,toDate,asOf,status?.available,status?.covered_through,status?.source_commit,onPlan,supportedEnd])
  useEffect(()=>{
    if(!syncId)return
    onSyncBusy(true)
    let active=true
    const timer=window.setInterval(()=>{
      void get<JobStatus>('/jobs/'+syncId).then(async j=>{
        if(!active||!['complete','error'].includes(j.status))return
        window.clearInterval(timer);setSyncId('');onSyncBusy(false)
        if(j.status==='error'){setIssue(j.error||'Historical membership sync failed');return}
        try{await refresh()}catch(e){setIssue(e instanceof Error?e.message:String(e))}
      }).catch(e=>{if(active){window.clearInterval(timer);setSyncId('');onSyncBusy(false);setIssue(e instanceof Error?e.message:String(e))}})
    },1500)
    return()=>{active=false;window.clearInterval(timer)}
  },[syncId,refresh,onSyncBusy])
  const sync=async()=>{
    setIssue('')
    try{
      const response=await get<{job_id:string}>('/indices/sync',{method:'POST'})
      setSyncId(response.job_id);onSyncBusy(true)
    }catch(e){setIssue(e instanceof Error?e.message:String(e))}
  }
  const name=mode==='nifty50_pit'?'NIFTY 50':'BANK NIFTY'
  const memberList=plan?.asof_members||[]
  return <div className="dh-pit-panel">
    <div className="dh-pit-source">
      <div><div className="dh-pit-source-icon"><FileClock size={20}/></div><div>
        <strong>{name} — Historical constituents</strong>
        <small>{status?.available?'Point-in-time intervals synced from independently reconstructed NSE announcements':
          'Historical index database not yet synced'}</small></div></div>
      <button type="button" className="dh-small-btn" disabled={!!syncId} onClick={()=>void sync()}>
        {syncId?<LoaderCircle size={14} className="dh-spin"/>:<RefreshCw size={14}/>}
        {syncId?'Syncing history':'Sync / update history'}
      </button>
    </div>
    {status?.available&&<div className="dh-pit-coverage">
      <span><Check size={13}/> Earliest: {readable(status.first_date||'2014-01-01')}</span>
      <span><Clock3 size={13}/> Source coverage through: {readable(status.covered_through||'2014-01-01')}</span>
      <span><ShieldCheck size={13}/> Reconstructed, source-pinned</span>
    </div>}
    {endOutsideCoverage&&
      <div className="dh-pit-alert"><AlertTriangle size={18}/><div>
        <strong>Your end date is newer than the historical membership source.</strong>
        <p>Selected: {readable(fromDate)} to {readable(previous(toDate))}.
          Membership evidence is available only through {readable(status!.covered_through!)}.
          Below is a preview of the documented portion; the original download range
          is unchanged and a full-range download remains disabled until we have
          evidence for the missing dates.</p>
        <button type="button" className="dh-small-btn" onClick={()=>onToDate(supportedEnd)}>
          Explicitly use documented end date ({supportedEnd})
        </button></div></div>}
    {!status?.available&&<div className="dh-pit-intro"><Database size={25}/>
      <strong>One-time historical membership sync</strong><p>This downloads a public CC0 point-in-time constituent history reconstructed from NSE notices. Dhan supplies market prices separately.</p>
      <button className="dh-primary" disabled={!!syncId} onClick={()=>void sync()}>
        <ArrowDownToLine size={15}/> {syncId?'Syncing records…':'Load NIFTY constituent history'}
      </button></div>}
    {issue&&<div className="dh-pit-alert"><AlertTriangle size={17}/><p>{issue}</p></div>}
    {loading&&<div className="dh-pit-loading"><LoaderCircle size={17} className="dh-spin"/> Reconstructing membership across the selected dates…</div>}
    {plan&&<>
      {endOutsideCoverage&&<p className="dh-hint">PREVIEW ONLY · Historical index membership through {plan.to_date} (exclusive). Missing remainder is not included in this selection.</p>}
      <div className="dh-pit-counts">
        <div><strong>{plan.start_count}</strong><span>At start</span></div>
        <div><strong>{plan.end_count}</strong><span>At end</span></div>
        <div><strong>{plan.union_count}</strong><span>Distinct stocks in period</span></div>
        <div><strong>{plan.change_count}</strong><span>Add/remove events</span></div>
      </div>
      <div className="dh-pit-chip-head">
        <strong>Every stock belonging to {name} at any point in this period ({plan.union_count})</strong>
        <div className="dh-pit-head-actions">
          <button onClick={()=>exportCsv(
            mode+'_'+fromDate+'_'+plan.to_date+'_historical_union.csv',
            [['index','from_inclusive','to_exclusive','symbol','membership_source_commit'],
             ...plan.union_members.map(symbol=>[plan.index_name,fromDate,plan.to_date,symbol,plan.source_commit])]
          )}><ArrowDownToLine size={13}/> Export union CSV</button>
          <button onClick={()=>setShowUnion(v=>!v)}>{showUnion?'Hide list':'Show list'} <ChevronDown size={14}/></button>
        </div>
      </div>
      {showUnion&&<div className="dh-pit-chips">{plan.union_members.map(symbol=><span key={symbol}>{symbol}</span>)}</div>}
      <div className="dh-pit-asof">
        <div><div><CalendarDays size={16}/><strong>Who was in {name} on this date?</strong></div>
          <small>Membership follows exact inclusion and exclusion effective dates.</small></div>
        <label><span>As of</span><input type="date" value={asOf} min={fromDate} max={previous(plan.to_date)}
          onChange={e=>setAsOf(e.target.value)} aria-label="Historical index membership as-of date"/></label>
      </div>
      <div className="dh-pit-chip-head"><strong>{plan.asof_members.length} constituents on {readable(plan.asof_date)}</strong>
        <div className="dh-pit-head-actions">
          <button onClick={()=>exportCsv(
            mode+'_'+plan.asof_date+'_constituents.csv',
            [['index','asof_date','symbol','membership_source_commit'],
             ...plan.asof_members.map(symbol=>[plan.index_name,plan.asof_date,symbol,plan.source_commit])]
          )}><ArrowDownToLine size={13}/> Export this date</button>
          <button onClick={()=>setShowAll(v=>!v)}>{showAll?'Show fewer':'Show all'} <ChevronDown size={14}/></button>
        </div></div>
      <div className="dh-pit-chips">{memberList.slice(0,showAll?memberList.length:24).map(s=><span key={s}>{s}</span>)}
        {!showAll&&memberList.length>24&&<span className="dh-pit-more">+{memberList.length-24} more</span>}</div>
      <div className="dh-pit-chip-head"><strong>Constituent changes in selected period</strong>
        <button onClick={()=>setShowChanges(v=>!v)}>{showChanges?'Hide':'Show'} {plan.change_count} changes <ChevronDown size={14}/></button></div>
      {showChanges&&<div className="dh-pit-events">{plan.changes.length?plan.changes.map((change,i)=>
        <div key={i}><span>{readable(change.effective_date)}</span><strong>{change.symbol}</strong>
          <span className={'dh-pit-action '+change.action}>{change.action.toUpperCase()}</span>
          {change.source_url?<a href={change.source_url} target="_blank" rel="noreferrer">Source ↗</a>:
            <small>{change.source}</small>}</div>):<p>No effective membership changes in this range.</p>}</div>}
      <div className="dh-pit-resolve"><div><span className="dh-led"/><strong>{plan.resolved_count} matched Dhan securities</strong></div>
        <div className={plan.unresolved_count?'issue':''}><span className="dh-led"/><strong>{plan.unresolved_count} missing/ambiguous Security IDs</strong></div></div>
      {plan.unresolved_count>0&&<div className="dh-pit-unresolved">
        <div><AlertTriangle size={17}/><strong>Historical members not found in the current Dhan master</strong>
          <button onClick={()=>exportCsv(
            mode+'_'+fromDate+'_'+plan.to_date+'_unresolved_dhan_ids.csv',
            [['index','from_inclusive','to_exclusive','symbol','unresolved_reason'],
             ...plan.unresolved.map(item=>[plan.index_name,fromDate,plan.to_date,item.symbol,item.reason])]
          )}><ArrowDownToLine size={13}/> Export gaps</button>
          <button onClick={()=>setShowMissing(v=>!v)}>{showMissing?'Hide':'View'}</button></div>
        <p>These may be old, renamed, or delisted listings. The app will not invent mappings. Downloading only available stocks will leave a documented historical-price gap.</p>
        {showMissing&&<div>{plan.unresolved.map(u=><span key={u.symbol} title={u.reason}>{u.symbol}</span>)}</div>}</div>}
      <div className="dh-pit-disclaimer"><Info size={16}/><p>Index membership is an independently reconstructed historical dataset, not an NSE-certified feed. Market prices are requested from Dhan separately. A correct historical universe also needs delisting prices, corporate actions, and a matching total-return benchmark before final backtest claims.</p></div>
    </>}
  </div>
}

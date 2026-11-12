import {useCallback, useEffect, useMemo, useState} from 'react'
import {
  Activity, ArrowDownToLine, ArrowRight, BarChart3, Beaker, BookOpen, Check,
  CheckCircle2, ChevronRight, CircleAlert, Clock3, Database, FileArchive,
  FileText, FlaskConical, Gauge, Layers3, LineChart, LoaderCircle,
  LockKeyhole, Menu, Play, RefreshCw, Settings2, ShieldAlert,
  ShieldCheck, Sigma, SlidersHorizontal, TrendingUp, Upload,
  Wallet, X
} from 'lucide-react'
import './workstation.css'
import DhanDataManager from './DhanDataManager'
import ModelLaboratory from './ModelLaboratory'
import ResearchGuide from './ResearchGuide'

type Dict = Record<string, unknown>
type Dataset = {id:string; label:string; kind:string; ready:boolean; monthly_price_observations?:number; missing:string[]; files:string[]; has_prices:boolean; has_daily_prices?:boolean; has_daily_ohlcv?:boolean; source_interval_minutes?:number|null; daily_session_count?:number; benchmark_kind?:string; benchmark_is_total_return?:boolean; independently_verified?:boolean; has_fundamentals:boolean; has_sectors:boolean; basis:string}
type Run = {id:string; name:string; dataset_id?:string; dataset_kind:string; created_utc?:string; metrics_by_split:Record<string,Dict>; coverage:Dict; status:string; first_price_date?:string; last_price_date?:string}
type Job = {id:string; kind:string; status:'queued'|'running'|'complete'|'error'; error?:string; result?:unknown}
type Detail = {id:string;meta:{config:Dict; metrics_by_split:Record<string,Dict>; coverage:Dict; limitations:string[]; first_price_date:string;last_price_date:string; generated_utc:string};source:Dict;returns:Dict[];latest_weights:{name:string;weight:number}[];rank_ic:Dict[];factor_exposures:Dict[];concentration:Dict[];rolling:Dict[];cost_sensitivity:Dict[];robustness:Dict[];methodologies:Dict[];audit:Dict;data_quality:Dict;artifacts:string[]}
type Health = {ok:boolean; mode:string; framework:string; read_only_market_data:boolean; broker_orders_enabled:boolean; dhan_token_configured:boolean; datasets:number;completed_runs:number}
type DhanStatus = {token_configured:boolean;instrument_master_available:boolean;instrument_master_bytes:number;read_only:boolean}
type RunConfig = {
  name:string;factor_weights:Record<string,number>;top_n:number;weighting:string;
  max_weight:number;rebalance_every:number;cost_bps:number;execution_lag:number;
  momentum_formation:number;momentum_skip:number;volatility_lookback:number;
  validation_start:string;final_test_start:string;sector_cap:number|null
}
const defaultConfig:RunConfig = {name:'quant_research_v1', factor_weights:{momentum:1,low_volatility:0,value:0,quality:0,size:0},top_n:10,weighting:'equal',max_weight:.2,rebalance_every:3,cost_bps:10,execution_lag:1,momentum_formation:12,momentum_skip:1,volatility_lookback:12,validation_start:'',final_test_start:'',sector_cap:null}
type Tab = 'overview'|'data'|'dhan'|'research'|'factors'|'construction'|'comparisons'|'mathematics'|'rolling'|'models'|'risk'|'robustness'|'visual'|'reports'|'history'|'settings'|'guide'
type NavItem = {id:Tab;label:string;icon:typeof Activity}
const sections:{label:string;items:NavItem[]}[]=[
 {label:'COMMAND CENTER',items:[{id:'overview',label:'Overview',icon:Gauge},{id:'history',label:'Saved Runs',icon:Clock3}]},
 {label:'DATA OPERATIONS',items:[{id:'data',label:'Data Manager',icon:Database},{id:'dhan',label:'Dhan Market Data',icon:Wallet}]},
 {label:'RESEARCH DESK',items:[{id:'research',label:'Index Research',icon:FlaskConical},{id:'factors',label:'Factor Laboratory',icon:Layers3},{id:'construction',label:'Index Construction',icon:SlidersHorizontal},{id:'comparisons',label:'Index Comparisons',icon:BarChart3}]},
 {label:'MODEL & RISK LAB',items:[{id:'mathematics',label:'Advanced Mathematics',icon:Sigma},{id:'rolling',label:'Rolling Validation',icon:LineChart},{id:'models',label:'Quantitative Models',icon:Beaker},{id:'risk',label:'Risk Attribution',icon:ShieldAlert},{id:'robustness',label:'Robustness',icon:Activity},{id:'visual',label:'Visual Validation',icon:TrendingUp}]},
 {label:'OUTPUT',items:[{id:'reports',label:'Research Reports',icon:FileText},{id:'guide',label:'User Guide & Documentation',icon:BookOpen},{id:'settings',label:'Workstation Settings',icon:Settings2}]},
]
const titles:Record<Tab,string>={overview:'Research command center',data:'Data manager',dhan:'DhanHQ market-data terminal',research:'Index research engine',factors:'Factor laboratory',construction:'Index construction',comparisons:'Index comparisons',mathematics:'Advanced mathematics',rolling:'Rolling validation',models:'Quantitative models',risk:'Risk attribution',robustness:'Robustness & sensitivity',visual:'Visual validation',reports:'Research reports',history:'Saved research runs',settings:'Workstation settings',guide:'How to use QuantLab'}
const factors=[['momentum','Momentum'],['low_volatility','Low volatility'],['value','Value'],['quality','Quality'],['size','Size']] as const
const number=(v:unknown,d=2)=>typeof v==='number' && Number.isFinite(v) ? v.toLocaleString('en-US',{maximumFractionDigits:d,minimumFractionDigits:d}) : '—'
const percent=(v:unknown,d=2)=>typeof v==='number' && Number.isFinite(v) ? (v*100).toFixed(d)+'%' : '—'
const label=(s:string)=>s.replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase())
const date=(s?:string)=>s ? new Date(s).toLocaleString(undefined,{month:'short',day:'numeric',year:'numeric'}) : '—'
function errorMessage(error:unknown){return error instanceof Error?error.message:String(error)}
async function request<T>(url:string, options?:RequestInit):Promise<T>{
  let response:Response
  try {response=await fetch('/api'+url,options)}catch{throw new Error('Cannot reach the Python research engine. Start the workstation using bash run.sh.')}
  if(!response.ok){let payload:Dict={};try{payload=await response.json()}catch{/* empty */}
    const detail=payload.detail
    throw new Error(typeof detail==='string'?detail:response.status+' '+response.statusText)
  }
  return await response.json() as T
}
function post<T>(url:string,body:unknown){return request<T>(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})}
function Tag({children,tone='neutral'}:{children:React.ReactNode;tone?:'neutral'|'good'|'warn'|'bad'|'blue'}){
  return <span className={'ws-tag '+tone}>{children}</span>
}
function Card({title,children,extra,className=''}:{title?:string;children:React.ReactNode;extra?:React.ReactNode;className?:string}){
  return <section className={'ws-card '+className}>{title&&<div className="ws-cardhead"><h3>{title}</h3>{extra}</div>}{children}</section>
}
function Empty({title,children,onAction,action}:{title:string;children?:React.ReactNode;onAction?:()=>void;action?:string}){
  return <div className="ws-empty"><Database size={26} strokeWidth={1.5}/><strong>{title}</strong><p>{children}</p>{onAction&&<button className="ws-button" type="button" onClick={onAction}>{action||'Open data manager'} <ArrowRight size={14}/></button>}</div>
}
function Metric({label:caption,value,caption:note,highlight}:{label:string;value:string;caption?:string;highlight?:boolean}){
  return <div className={'ws-metric '+(highlight?'highlight':'')}><span>{caption}</span><strong>{value}</strong><small>{note}</small></div>
}
function Table({rows,max=15}:{rows:Dict[];max?:number}){
  if(!rows.length)return <div className="ws-table-empty">No saved observations for this panel. Run an experiment first.</div>
  const keys=Object.keys(rows[0]).slice(0,11)
  return <div className="ws-table-scroll"><table><thead><tr>{keys.map(k=><th key={k}>{label(k)}</th>)}</tr></thead><tbody>{rows.slice(0,max).map((row,i)=><tr key={i}>{keys.map(k=><td key={k} title={String(row[k]??'')}>{typeof row[k]==='number'?number(row[k],4):String(row[k]??'—')}</td>)}</tr>)}</tbody></table></div>
}
function EquityChart({rows,caption='Strategy vs benchmark',height=270}:{rows:Dict[];caption?:string;height?:number}){
  const points=useMemo(()=>{
    let a=1,b=1
    return rows.map((r,i)=>{const sa=Number(r.strategy_net), sb=Number(r.benchmark)
      if(Number.isFinite(sa)&&sa>-1)a*=1+sa
      if(Number.isFinite(sb)&&sb>-1)b*=1+sb
      return {x:i, strategy:a, benchmark:b,date:String(r.date??'')}
    })
  },[rows])
  if(points.length<2)return <Empty title="Awaiting return series">The chart is built from saved Python run results, never placeholder performance data.</Empty>
  const all=points.flatMap(p=>[p.strategy,p.benchmark]).filter(Number.isFinite)
  const low=Math.min(...all),high=Math.max(...all),range=Math.max(.001,high-low)
  const path=(key:'strategy'|'benchmark')=>points.map((p,i)=>{
    const x=46+(i/(points.length-1))*894
    const y=240-((p[key]-low)/range)*206
    return (i===0?'M':'L')+x.toFixed(2)+' '+y.toFixed(2)
  }).join(' ')
  return <div className="ws-chart"><div className="ws-chartheader"><span>{caption}</span><div><i className="ws-dot mint"/> Strategy <i className="ws-dot gold"/> Benchmark</div></div>
    <svg viewBox="0 0 980 282" preserveAspectRatio="none" style={{height}} role="img" aria-label="Cumulative wealth chart computed from saved net monthly strategy returns and benchmark returns">
      {[0,.25,.5,.75,1].map(v=><g key={v}><line x1="46" x2="940" y1={240-v*206} y2={240-v*206} stroke="#253143" strokeDasharray="3 7"/><text x="8" y={244-v*206} fill="#8396a9" fontSize="12">{number(low+v*range,1)}x</text></g>)}
      <path d={path('benchmark')} stroke="#e3b675" fill="none" strokeWidth="2.4" vectorEffect="non-scaling-stroke"/>
      <path d={path('strategy')} stroke="#64dbc2" fill="none" strokeWidth="3" vectorEffect="non-scaling-stroke"/>
      <text x="46" y="269" fill="#8295aa" fontSize="12">{points[0].date.slice(0,10)}</text>
      <text x="830" y="269" fill="#8295aa" fontSize="12">{points[points.length-1].date.slice(0,10)}</text>
    </svg>
    <p className="ws-caption">Normalized to 1.00 at the start of the saved return series. Descriptive research only; not proof of investability.</p>
  </div>
}
function BarRows({rows,valueKey='weight',nameKey='name'}:{rows:Dict[];valueKey?:string;nameKey?:string}){
  if(!rows.length)return <Empty title="No exposure data">Select a completed research run to inspect portfolio exposures.</Empty>
  const top=rows.slice(0,14); const max=Math.max(...top.map(r=>Math.abs(Number(r[valueKey]||0))),.00001)
  return <div className="ws-bars">{top.map((r,i)=><div className="ws-bar-row" key={i}><span title={String(r[nameKey])}>{String(r[nameKey]??'—')}</span><div><i style={{width:(Math.abs(Number(r[valueKey]||0))/max*100)+'%'}}/></div><strong>{percent(Number(r[valueKey]))}</strong></div>)}</div>
}
function NumberInput({label:caption,value,onChange,min,max,step=1}:{label:string;value:number;onChange:(n:number)=>void;min?:number;max?:number;step?:number}){
  return <label className="ws-field"><span>{caption}</span><input type="number" value={value} onChange={e=>onChange(Number(e.target.value))} min={min} max={max} step={step}/></label>
}
function Field({label:caption,value,onChange,placeholder='',type='text'}:{label:string;value:string;onChange:(s:string)=>void;placeholder?:string;type?:string}){
  return <label className="ws-field"><span>{caption}</span><input type={type} value={value} placeholder={placeholder} onChange={e=>onChange(e.target.value)}/></label>
}
function Select({label:caption,value,options,onChange}:{label:string;value:string;options:{value:string;label:string}[];onChange:(v:string)=>void}){
  return <label className="ws-field"><span>{caption}</span><select value={value} onChange={e=>onChange(e.target.value)}>{options.map(opt=><option key={opt.value} value={opt.value}>{opt.label}</option>)}</select></label>
}
const weighted=(metric:Dict|undefined,key:string)=>metric?.[key]
function App(){
  const [tab,setTab]=useState<Tab>('overview')
  const [menu,setMenu]=useState(false)
  const [health,setHealth]=useState<Health|null>(null)
  const [datasets,setDatasets]=useState<Dataset[]>([])
  const [selectedDataset,setSelectedDataset]=useState('')
  const [runs,setRuns]=useState<Run[]>([])
  const [selectedRun,setSelectedRun]=useState('')
  const [detail,setDetail]=useState<Detail|null>(null)
  const [config,setConfig]=useState<RunConfig>(defaultConfig)
  const [job,setJob]=useState<Job|null>(null)
  const [busy,setBusy]=useState(false)
  const [notice,setNotice]=useState<{text:string;error:boolean}|null>(null)
  const [auditResult,setAuditResult]=useState<Dict|null>(null)
  const [dhan,setDhan]=useState<DhanStatus|null>(null)
  const dataset=datasets.find(d=>d.id===selectedDataset)
  const selected=runs.find(r=>r.id===selectedRun)
  const metrics=detail?.meta.metrics_by_split??selected?.metrics_by_split??{}
  const split=Object.entries(metrics).at(-1)
  const metric=split?.[1]
  const monthlyCount=dataset?.monthly_price_observations??0
  const requiredWarmup=Math.max(
    (config.factor_weights.momentum||0)>0?config.momentum_formation+config.momentum_skip:0,
    (config.factor_weights.low_volatility||0)>0 || ['inverse_volatility','minimum_variance','risk_parity'].includes(config.weighting)
      ?config.volatility_lookback:0
  )
  const availableTestMonths=Math.max(0,monthlyCount-requiredWarmup-config.execution_lag)
  const notify=(text:string,error=false)=>setNotice({text,error})
  const refresh=useCallback(async()=>{
    try {
      const [h, ds, rr, dh]=await Promise.all([
        request<Health>('/health'),request<{datasets:Dataset[]}>('/datasets'),
        request<{runs:Run[]}>('/runs'),request<DhanStatus>('/dhan/status')
      ])
      setHealth(h);setDatasets(ds.datasets);setRuns(rr.runs);setDhan(dh)
      setSelectedDataset(s=>{
        const existing=ds.datasets.find(d=>d.id===s)
        if(existing&&existing.kind!=='synthetic')return s
        const prepared=ds.datasets.find(d=>d.kind==='dhan'&&d.has_prices)
        return prepared?.id||(existing?.id)||ds.datasets.find(d=>d.ready)?.id||ds.datasets[0]?.id||''
      })
      setSelectedRun(s=>rr.runs.some(r=>r.id===s)?s:rr.runs[0]?.id||'')
    }catch(e){notify(errorMessage(e),true)}
  },[])
  useEffect(()=>{void refresh()},[refresh])
  useEffect(()=>{
    if(!selectedRun){setDetail(null);return}
    let active=true
    request<Detail>('/runs/'+encodeURIComponent(selectedRun)).then(d=>{if(active)setDetail(d)}).catch(e=>{if(active){setDetail(null);notify(errorMessage(e),true)}})
    return()=>{active=false}
  },[selectedRun])
  useEffect(()=>{
    if(!job||!['queued','running'].includes(job.status))return
    const timer=setTimeout(()=>{
      request<Job>('/jobs/'+job.id).then(j=>{
        setJob(j)
        if(j.status==='complete'){
          notify(j.kind==='experiment'?'Research run completed; saved to history.':'Operation completed.')
          void refresh()
          if(j.kind==='experiment' && typeof j.result==='string'){setSelectedRun(j.result);setTab('overview')}
        }
        if(j.status==='error')notify(j.error||'Job failed',true)
      }).catch(e=>notify(errorMessage(e),true))
    },1400)
    return()=>clearTimeout(timer)
  },[job,refresh])
  const execute=async<T,>(f:()=>Promise<T>,callback?:(value:T)=>void)=>{
    setBusy(true)
    try {const value=await f();callback?.(value)}catch(e){notify(errorMessage(e),true)}finally{setBusy(false)}
  }
  const begin=(id:Tab)=>{setTab(id);setMenu(false);window.scrollTo(0,0)}
  const startRun=()=>execute(()=>post<{job_id:string;status:Job['status']}>('/experiments',{...config,dataset_id:selectedDataset}),r=>{setJob({id:r.job_id,kind:'experiment',status:'queued'});notify('Python research job queued.')})
  const synthetic=()=>execute(()=>post<Dataset>('/datasets/synthetic',{}),r=>{void refresh();setSelectedDataset(r.id);notify('Synthetic fixture created. This is not historical market evidence.')})
  const upload=async(file:File)=>{
    await execute(async()=>{
      const form=new FormData();form.append('file',file)
      return request<Dataset>('/datasets/import',{method:'POST',body:form})
    },r=>{void refresh();setSelectedDataset(r.id);notify('Dataset imported for internal validation; provenance remains unverified.')})
  }
  const downloadReport=()=>execute(()=>post<{job_id:string}>('/runs/'+selectedRun+'/reports',{}),r=>{setJob({id:r.job_id,kind:'reports',status:'queued'});notify('Report export queued.')})
  const runPicker=<select aria-label="Select completed experiment" className="ws-select" value={selectedRun} onChange={e=>setSelectedRun(e.target.value)}>{runs.length===0?<option value="">No runs yet</option>:runs.map(r=><option key={r.id} value={r.id}>{r.name} · {r.id}</option>)}</select>
  const dataPicker=<select className="ws-select" aria-label="Select research dataset" value={selectedDataset} onChange={e=>{setSelectedDataset(e.target.value)}}><option value="">Choose dataset</option>{datasets.map(d=><option key={d.id} value={d.id}>{d.label}{d.ready?'':' (incomplete)'}</option>)}</select>
  const withRun=(content:React.ReactNode)=><>{runs.length===0?<Empty title="No research run selected" onAction={()=>begin('research')} action="Run an experiment">All charts are generated from Python research outputs, not hardcoded sample performance.</Empty>:<>{runPicker}{content}</>}</>
  const classification=<Tag tone={detail?.source.dataset_kind==='synthetic'?'warn':'blue'}>{detail?.source.dataset_kind==='synthetic'?'SYNTHETIC DATA — DEMONSTRATION':detail?'USER DATA · NOT INDEPENDENTLY AUDITED':'NO RESEARCH RUN'}</Tag>
  const chart=detail?<EquityChart rows={detail.returns}/>:null
  const panel=(key: keyof Detail,description:string)=>withRun(<Card title={description}><Table rows={(detail?.[key] as Dict[]|undefined)??[]} max={20}/></Card>)
  return <div className="ws-shell">
    <aside className={'ws-sidebar '+(menu?'open':'')}>
      <div className="ws-brand"><span className="ws-brand-mark"><Activity size={23}/></span><div><strong>QUANT<span>LAB</span></strong><small>RESEARCH WORKSTATION</small></div><button type="button" className="ws-mobile-close" onClick={()=>setMenu(false)}><X size={19}/></button></div>
      <div className="ws-env"><span className={'ws-status-dot '+(health?.ok?'':'offline')}/><div><strong>{health?.ok?'LOCAL ENGINE CONNECTED':'ENGINE DISCONNECTED'}</strong><small>127.0.0.1 · NO BROKER EXECUTION</small></div></div>
      <nav>{sections.map(group=><div className="ws-nav-group" key={group.label}><span className="ws-nav-label">{group.label}</span>{group.items.map(item=><button type="button" key={item.id} onClick={()=>begin(item.id)} className={'ws-nav-item '+(tab===item.id?'active':'')}><item.icon size={17} strokeWidth={1.9}/>{item.label}{tab===item.id&&<span className="ws-nav-select"/>}</button>)}</div>)}</nav>
      <div className="ws-sidefoot"><LockKeyhole size={15}/><div><strong>PRIVATE / LOCAL FIRST</strong><small>Credentials never sent to browser</small></div></div>
    </aside>
    {menu&&<button className="ws-backdrop" onClick={()=>setMenu(false)} aria-label="Close navigation"/>}
    <div className="ws-main">
      <header className="ws-topbar"><div className="ws-top-left"><button type="button" className="ws-menu" onClick={()=>setMenu(true)} aria-label="Open navigation"><Menu size={19}/></button><span className="ws-breadcrumb">WORKSTATION</span><ChevronRight size={14}/><strong>{titles[tab]}</strong></div><div className="ws-top-right">{job&&['queued','running'].includes(job.status)&&<Tag tone="blue"><LoaderCircle size={13} className="ws-spin"/> {label(job.kind)} running</Tag>}<Tag tone={health?.ok?'good':'bad'}>{health?.ok?'ENGINE ONLINE':'OFFLINE'}</Tag><button title="Refresh from backend" aria-label="Refresh data" className="ws-icon" onClick={()=>void refresh()}><RefreshCw size={16}/></button></div></header>
      <main className="ws-content">
        <div className="ws-titlebar"><div><div className="ws-overline">QUANTITATIVE EQUITY INDEX & FACTOR RESEARCH</div><h1>{titles[tab]}</h1><p>Local Python research engine · React/Vite desktop-style interface · Explicit source provenance</p></div><div className="ws-title-actions"><button type="button" className="ws-button secondary" onClick={()=>begin('guide')}><BookOpen size={15}/> Guide</button><button type="button" className="ws-button secondary" onClick={()=>begin('data')}><Database size={15}/> Data</button><button type="button" className="ws-button primary" onClick={()=>begin('research')}><Play size={14}/> New experiment</button></div></div>
        {notice&&<div role="status" className={'ws-notice '+(notice.error?'error':'')}><span>{notice.error?<CircleAlert size={17}/>:<CheckCircle2 size={17}/>}</span>{notice.text}<button onClick={()=>setNotice(null)} aria-label="Dismiss"><X size={16}/></button></div>}
        {tab==='overview'&&<>
          <div className="ws-overview-banner"><div><Tag tone="blue">RESEARCH CONTROL DESK / MODEL LAB V1</Tag><h2>One workstation.<br/><em>Every model, traceable.</em></h2><p>Keep datasets, factor experiments, risk calculations and generated evidence in one reproducible local research environment.</p><div className="ws-banner-actions"><button className="ws-button primary" onClick={()=>begin('research')}><Play size={16}/> Run research</button><button className="ws-button secondary" onClick={()=>begin('dhan')}><Database size={16}/> Connect market data</button></div></div><div className="ws-banner-graphic"><div className="ws-orbit one"/><div className="ws-orbit two"/><div className="ws-orbit three"/><span className="ws-center-glow"><Activity size={45}/></span><span className="ws-orbit-label a">MOMENTUM</span><span className="ws-orbit-label b">RISK</span><span className="ws-orbit-label c">FACTOR</span></div></div>
          <div className="ws-metrics-grid"><Metric label="Available datasets" value={String(datasets.length)} caption={datasets.filter(d=>d.ready).length+' ready for research'}/><Metric label="Completed runs" value={String(runs.length)} caption="Stored locally on disk"/><Metric label="DhanHQ data access" value={dhan?.token_configured?'SET':'NOT SET'} caption="Read-only market data"/><Metric label="Python computation" value={health?.ok?'ONLINE':'OFFLINE'} caption="127.0.0.1:8765" highlight/></div>
          <div className="ws-grid two-thirds"><Card title="Portfolio research performance" extra={classification}>{chart??<Empty title="No historical run selected" onAction={()=>begin('research')} action="Configure experiment">Run the research engine to generate actual saved series and metrics.</Empty>}</Card><Card title="Latest research snapshot">{detail?<><div className="ws-overview-stat"><span>Strategy CAGR</span><strong>{percent(weighted(metric,'strategy_cagr'))}</strong></div><div className="ws-overview-stat"><span>Max drawdown</span><strong>{percent(weighted(metric,'max_drawdown'))}</strong></div><div className="ws-overview-stat"><span>Tracking error</span><strong>{percent(weighted(metric,'tracking_error'))}</strong></div><div className="ws-overview-stat"><span>Sample window</span><strong>{detail.meta.first_price_date?.slice(0,7)}–{detail.meta.last_price_date?.slice(0,7)}</strong></div><button className="ws-textlink" onClick={()=>begin('history')}>Inspect full run <ArrowRight size={15}/></button></>:<Empty title="Nothing to report">No metrics will appear until a Python experiment completes.</Empty>}</Card></div>
          <div className="ws-grid halves"><Card title="Research datasets" extra={<button className="ws-textlink" onClick={()=>begin('data')}>Manage <ArrowRight size={13}/></button>}><div className="ws-item-list">{datasets.slice(0,5).map(d=><button className="ws-dataset-row" key={d.id} onClick={()=>{setSelectedDataset(d.id);begin('data')}}><Database size={17}/><span><strong>{d.label}</strong><small>{d.basis}</small></span><Tag tone={d.ready?'good':'warn'}>{d.ready?'READY':'INCOMPLETE'}</Tag></button>)}{datasets.length===0&&<p className="ws-caption">No datasets found.</p>}</div></Card><Card title="Recent experiments" extra={<button className="ws-textlink" onClick={()=>begin('history')}>View history <ArrowRight size={13}/></button>}><div className="ws-item-list">{runs.slice(0,5).map(r=><button className="ws-dataset-row" key={r.id} onClick={()=>{setSelectedRun(r.id);begin('history')}}><Clock3 size={17}/><span><strong>{r.name}</strong><small>{r.id} · {date(r.created_utc)}</small></span><Tag tone={r.dataset_kind==='synthetic'?'warn':'blue'}>{r.dataset_kind}</Tag></button>)}{runs.length===0&&<p className="ws-caption">No completed runs yet.</p>}</div></Card></div>
        </>}
        {tab==='data'&&<>
          <div className="ws-grid halves"><Card title="Select research dataset" extra={dataPicker}><p className="ws-caption">Completed Dhan downloads remain stored locally. To register the 1-minute NIFTY download here, open Dhan Market Data → Download history → select the completed 51-stock batch → Prepare research dataset from 1-minute candles. QuantLab aggregates existing candles without downloading again. This does not independently certify benchmarks or adjusted returns.</p><div className="ws-actions"><button className="ws-button" disabled={busy} onClick={synthetic}><Beaker size={15}/> Create synthetic test dataset</button><label className={'ws-button secondary '+(busy?'disabled':'')}><Upload size={15}/> Import research ZIP<input hidden type="file" accept=".zip" disabled={busy} onChange={e=>{const f=e.target.files?.[0];if(f)void upload(f);e.target.value=''}}/></label></div><p className="ws-caption">ZIP requires prices.csv, membership.csv and benchmark.csv; optionally fundamentals.csv, sectors.csv and corporate_actions.csv. Import does not certify the data.</p></Card><Card title="Selected dataset readiness">{dataset?<><div className="ws-selected-dataset"><strong>{dataset.label}</strong><Tag tone={dataset.ready?'good':'warn'}>{dataset.ready?'FILES COMPLETE':'MISSING INPUTS'}</Tag></div>
          {dataset.benchmark_kind==='price_index_spot_only'&&<div className="ws-warning">
            <p>PRICE-INDEX BENCHMARK ONLY — Dhan NIFTY spot data does not include reinvested dividends. Files may be structurally complete for exploratory comparisons, but this is NOT an independently verified total-return benchmark or research certification. Stock splits, dividends and corporate actions still require review.</p>
          </div>}<p className="ws-caption">{dataset.basis}</p><div className="ws-checklist">{['prices.csv','daily_prices.csv','membership.csv','benchmark.csv','fundamentals.csv','sectors.csv'].map(name=><div key={name}>{dataset.files.includes(name)?<Check size={16}/>:<CircleAlert size={16}/>}<span>{name}</span><small>{dataset.files.includes(name)?'PRESENT':'NOT SUPPLIED'}</small></div>)}</div><div className="ws-actions"><button className="ws-button secondary" disabled={!dataset.ready||busy} onClick={()=>execute(()=>request<Dict>('/datasets/'+dataset.id+'/audit'),r=>{notify('Internal consistency audit completed; external validation remains required.');setAuditResult(r)})}>Run data audit</button><button className="ws-button primary" onClick={()=>begin('research')}>Use in research <ArrowRight size={14}/></button></div></>:<Empty title="Choose a dataset">Upload verified input files or create a synthetic software demonstration.</Empty>}</Card></div>
          {auditResult&&<Card title="Internal consistency audit"><div className="ws-data-audit">{Object.entries(auditResult).filter(([k])=>k!=='warnings').map(([k,v])=><div key={k}><span>{label(k)}</span><strong>{typeof v==='object'?JSON.stringify(v):String(v)}</strong></div>)}</div>{Array.isArray(auditResult.warnings)&&<div className="ws-warning">{auditResult.warnings.map((w,i)=><p key={i}>• {String(w)}</p>)}</div>}</Card>}
          <Card title="Imported dataset library"><Table rows={datasets.map(d=>({name:d.label,kind:d.kind,ready:d.ready,benchmark:d.benchmark_kind==='price_index_spot_only'?'PRICE INDEX (not TRI)':d.benchmark_kind||'missing',daily_prices:d.has_daily_prices?'yes':'no',source_resolution:d.source_interval_minutes===null?'daily':d.source_interval_minutes?d.source_interval_minutes+' min':'unreported',missing:d.missing.join(', ')||'none',basis:d.basis}))}/></Card>
        </>}
        {tab==='dhan'&&<DhanDataManager onDataChanged={refresh}/>}
        {tab==='research'&&<>
          <div className="ws-grid two-thirds"><Card title="Experiment configuration" extra={<Tag tone="blue">BACKED BY PYTHON</Tag>}><div className="ws-setup-row"><span>Source dataset</span>{dataPicker}<Tag tone={dataset?.ready?'good':'warn'}>{dataset?.ready?'READY':'NEEDS INPUTS'}</Tag></div><div className="ws-form-grid"><Field label="Experiment name" value={config.name} onChange={v=>setConfig({...config,name:v})}/><Select label="Portfolio weighting" value={config.weighting} onChange={v=>setConfig({...config,weighting:v})} options={['equal','score','inverse_volatility','minimum_variance','risk_parity'].map(v=>({value:v,label:label(v)}))}/><NumberInput label="Constituents (top N)" value={config.top_n} min={2} max={300} onChange={v=>setConfig({...config,top_n:v})}/><NumberInput label="Maximum holding weight" value={config.max_weight} min={.01} max={1} step={.01} onChange={v=>setConfig({...config,max_weight:v})}/><NumberInput label="Rebalance frequency (months)" value={config.rebalance_every} min={1} max={12} onChange={v=>setConfig({...config,rebalance_every:v})}/><NumberInput label="Transaction costs (bps)" value={config.cost_bps} min={0} max={500} step={5} onChange={v=>setConfig({...config,cost_bps:v})}/><Select label="Execution lag" value={String(config.execution_lag)} onChange={v=>setConfig({...config,execution_lag:Number(v)})} options={[{value:'1',label:'One month (conservative)'},{value:'0',label:'Same-close idealization'}]}/><NumberInput label="Formation months" value={config.momentum_formation} min={2} max={60} onChange={v=>setConfig({...config,momentum_formation:v})}/><NumberInput label="Months to skip" value={config.momentum_skip} min={0} max={12} onChange={v=>setConfig({...config,momentum_skip:v})}/><NumberInput label="Volatility lookback (months)" value={config.volatility_lookback} min={3} max={60} onChange={v=>setConfig({...config,volatility_lookback:v})}/><Field label="Validation start (optional)" type="date" value={config.validation_start} onChange={v=>setConfig({...config,validation_start:v})}/><Field label="Frozen test start (optional)" type="date" value={config.final_test_start} onChange={v=>setConfig({...config,final_test_start:v})}/></div><label className="ws-checkbox"><input type="checkbox" checked={config.sector_cap!==null} onChange={e=>setConfig({...config,sector_cap:e.target.checked ? 0.4 : null})}/> Apply historical sector concentration cap</label>{config.sector_cap!==null&&<NumberInput label="Sector allocation cap" value={config.sector_cap} min={.1} max={1} step={.05} onChange={v=>setConfig({...config,sector_cap:v})}/>}{dataset?.has_prices&&monthlyCount>0&&availableTestMonths<12&&
              <div className="ws-rule" role="status"><CircleAlert size={16}/>
                <div><strong>Limited statistical window: {monthlyCount} price observations</strong>
                  <p>After approximately {requiredWarmup} months of signal history and {config.execution_lag} month(s) of execution lag, only up to {availableTestMonths} eligible months remain before other eligibility gates. CAGR, drawdown or inference may be undefined. Short-sample runs are exploratory, not resume-ready performance claims.</p>
                  {monthlyCount>4&&<button type="button" className="ws-textlink"
                    onClick={()=>setConfig(c=>({...c,momentum_formation:3,momentum_skip:1,volatility_lookback:3,rebalance_every:1}))}>
                    Apply explicit short-sample demonstration settings <ArrowRight size={13}/></button>}
                </div>
              </div>}
              <div className="ws-actions"><button className="ws-button primary" disabled={!dataset?.ready||busy||!!job&&['queued','running'].includes(job.status)} onClick={startRun}><Play size={15}/> Run Python backtest</button><span className="ws-caption">Uses saved datasets with explicit provenance; writes result artifacts to disk.</span></div></Card>
          <Card title="Factor allocation"><p className="ws-caption">Select a factor and adjust its relative contribution to the composite score.</p><div className="ws-sliders">{factors.map(([key,name])=><label className="ws-factor" key={key}><div><span>{name}</span><strong>{number(config.factor_weights[key],1)}</strong></div><input type="range" min="0" max="1" step=".1" value={config.factor_weights[key]??0} onChange={e=>setConfig({...config,factor_weights:{...config.factor_weights,[key]:Number(e.target.value)}})}/></label>)}</div><div className="ws-rule"><ShieldCheck size={16}/> A backtest cannot prove historical correctness when constituent histories, adjusted returns, and benchmark evidence are missing.</div></Card></div>
          {job&&<Card title="Current job"><div className="ws-job-row"><Tag tone={job.status==='error'?'bad':job.status==='complete'?'good':'blue'}>{job.status.toUpperCase()}</Tag><span>{job.kind}</span><small>{job.error||job.id}</small></div></Card>}
        </>}
        {tab==='history'&&<>{withRun(<div className="ws-grid four"><Metric label="Strategy CAGR" value={percent(weighted(metric,'strategy_cagr'))} caption={split?.[0]||'No result'}/><Metric label="Benchmark CAGR" value={percent(weighted(metric,'benchmark_cagr'))}/><Metric label="Information ratio" value={number(weighted(metric,'information_ratio'))}/><Metric label="Max drawdown" value={percent(weighted(metric,'max_drawdown'))}/></div>)}{detail&&<><Card title="Run performance" extra={classification}>{chart}</Card><div className="ws-grid halves"><Card title="Latest portfolio weights"><BarRows rows={detail.latest_weights}/></Card><Card title="Run manifest"><div className="ws-data-audit">{Object.entries(detail.meta.config).map(([k,v])=><div key={k}><span>{label(k)}</span><strong>{typeof v==='object'?JSON.stringify(v):String(v??'—')}</strong></div>)}</div></Card></div></>}</>}
        {tab==='factors'&&<>{withRun(<div className="ws-grid halves"><Card title="Factor rank information coefficient"><Table rows={detail?.rank_ic||[]}/></Card><Card title="Portfolio factor exposures"><Table rows={detail?.factor_exposures||[]}/></Card></div>)}</>}
        {tab==='construction'&&<>{withRun(<div className="ws-grid halves"><Card title="Current allocation"><BarRows rows={detail?.latest_weights||[]}/></Card><Card title="Concentration history"><Table rows={detail?.concentration||[]}/></Card></div>)}</>}
        {tab==='comparisons'&&<>{panel('methodologies','Methodology comparison outputs')}{panel('cost_sensitivity','Transaction cost sensitivity')}</>}
        {tab==='rolling'&&<>{panel('rolling','Rolling relative return and tracking metrics')}</>}
        {tab==='risk'&&<>{panel('concentration','Risk concentration over time')}{panel('rolling','Rolling relative risk metrics')}</>}
        {tab==='robustness'&&<>{panel('robustness','Parameter sensitivity and robustness grid')}</>}
        {tab==='visual'&&<>{withRun(<Card title="Cumulative strategy / benchmark path" extra={classification}>{chart}</Card>)}{panel('rank_ic','Cross-sectional factor validation')}</>}
        {(tab==='mathematics'||tab==='models')&&<ModelLaboratory
          section={tab} datasets={datasets} selectedDataset={selectedDataset}
          onSelectDataset={setSelectedDataset} onOpenGuide={()=>begin('guide')} onDataChanged={refresh}/>}
        {tab==='guide'&&<ResearchGuide onNavigate={route=>begin(route as Tab)}/>}
        {tab==='reports'&&<>{withRun(<Card title="Generate reproducible research report"><p className="ws-caption">Generate an offline HTML report and PDF draft from selected saved Python run artifacts. Synthetic demonstrations are explicitly labeled.</p><div className="ws-actions"><button className="ws-button primary" disabled={!selectedRun||busy} onClick={downloadReport}><FileText size={15}/> Build HTML + PDF</button></div><div className="ws-artifact-list">{(detail?.artifacts||[]).map(name=><a key={name} href={'/api/runs/'+encodeURIComponent(selectedRun)+'/files/'+encodeURIComponent(name)} download><FileArchive size={16}/><span>{name}</span><ArrowDownToLine size={14}/></a>)}</div></Card>)}</>}
        {tab==='settings'&&<div className="ws-grid halves"><Card title="Backend and privacy"><div className="ws-data-audit"><div><span>API address</span><strong>127.0.0.1:8765</strong></div><div><span>Frontend address</span><strong>127.0.0.1:5173</strong></div><div><span>Data directory</span><strong>data/ (Git-ignored)</strong></div><div><span>Run artifacts</span><strong>results/workstation_runs/</strong></div><div><span>Authentication</span><strong>Loopback-only; not for public exposure</strong></div><div><span>Broker trading</span><strong>DISABLED</strong></div><div><span>Dhan token</span><strong>{health?.dhan_token_configured?'CONFIGURED (HIDDEN)':'MISSING'}</strong></div></div></Card><Card title="Integrity controls"><div className="ws-rule"><ShieldCheck size={18}/> Local data import, explicit dataset status, safe path allowlists, no broker order operations, no credential output, and no historical-performance fabrication.</div><p className="ws-caption">This is a local research environment, not an authenticated public server. Do not expose port 8765 on a network or deploy it as-is.</p><button className="ws-button secondary" onClick={()=>void refresh()}><RefreshCw size={16}/> Refresh engine status</button></Card></div>}
        <footer className="ws-footer"><span>QUANTLAB / RESEARCH WORKSTATION</span><span>LOCAL ENGINE · HISTORICAL CLAIMS REQUIRE EXTERNAL VALIDATION</span><span>© PERSONAL RESEARCH</span></footer>
      </main>
    </div>
  </div>
}
export default App

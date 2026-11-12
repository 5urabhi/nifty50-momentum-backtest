import {useCallback, useEffect, useMemo, useState} from 'react'
import {
  ArrowDownToLine, ArrowRight, Check, CheckCircle2, ChevronLeft, ChevronRight,
  CircleAlert, Clock3, Database, FileSpreadsheet, History, Layers3,
  LoaderCircle, LockKeyhole, Pause, Play, RefreshCw, Search,
  ShieldCheck, UploadCloud, X
} from 'lucide-react'
import PITIndexPanel, {type MembershipPlan, type PITMode} from './PITIndexPanel'
import './dhan-workspace.css'

type SelectionMode = 'selected' | 'all_nse' | 'all_bse' | 'watchlist' | PITMode
type CatalogItem = {
  id:string;symbol:string;display_name:string;security_id:string;
  exchange_segment:string;instrument:string;series:string;isin:string;regular_eq:boolean
}
type CatalogPage = {
  items:CatalogItem[];total:number;page:number;per_page:number;
  has_more:boolean;disclaimer:string
}
type BatchSummary = {
  id:string;status:string;created_utc:string;updated_utc?:string;selection:SelectionMode;
  interval:number|null;from_date:string;to_date:string;total:number;processed:number;
  counts:Record<string,number>;current_symbol:string|null;prepared_dataset_id?:string|null;
  errors:number;warning:string
  historical_index_name?:string|null;historical_union_count?:number
  historical_unresolved?:Array<{symbol:string;reason:string}>
}
type BatchDetails = BatchSummary & {
  items:Array<CatalogItem & {status:string;rows:number;rows_added:number;error?:string|null}>
  page:number;per_page:number;filtered_total:number
}
type Job = {job_id:string;batch?:BatchSummary}
type TaskStatus = {id:string;kind:string;status:string;error?:string;result?:Record<string,unknown>}
type DhanStatus = {token_configured:boolean;instrument_master_available:boolean;read_only:boolean}

const fmt=(n:number)=>n.toLocaleString()
const statusText=(s:string)=>s.replaceAll('_',' ')
const today=()=>dateValue(new Date())
function dateValue(d:Date){
  return new Date(d.getTime()-d.getTimezoneOffset()*60_000).toISOString().slice(0,10)
}
function yearAgo(){
  const d=new Date();d.setFullYear(d.getFullYear()-1)
  return dateValue(d)
}
async function api<T>(path:string,options?:RequestInit):Promise<T>{
  let response:Response
  try{response=await fetch('/api'+path,options)}
  catch{throw new Error('Python data engine is disconnected. Start with bash run.sh.')}
  if(!response.ok){
    let detail:unknown
    try{detail=(await response.json() as {detail:unknown}).detail}catch{/* no JSON */}
    throw new Error(typeof detail==='string'?detail:'Request failed ('+response.status+')')
  }
  return response.json() as Promise<T>
}
function post<T>(path:string,data:object={}){return api<T>(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})}
function Pill({children,tone='muted'}:{children:React.ReactNode;tone?:'good'|'warning'|'muted'|'blue'}){
  return <span className={'dh-pill '+tone}>{children}</span>
}
function Section({title,aside,children}:{title:string;aside?:React.ReactNode;children:React.ReactNode}){
  return <section className="dh-panel"><header><h3>{title}</h3>{aside}</header>{children}</section>
}
function interpretMode(mode:SelectionMode){
  return {selected:'Handpicked stocks',all_nse:'All NSE cash equities (EQ series)',
    all_bse:'All BSE cash equities',watchlist:'My ticker list',
    nifty50_pit:'NIFTY 50 · Historical members',banknifty_pit:'BANK NIFTY · Historical members'}[mode]
}
const options:Array<{mode:SelectionMode;title:string;description:string;icon:typeof Database}>=[
  {mode:'selected',title:'Choose stocks',description:'Search and add any combination of securities',icon:Search},
  {mode:'all_nse',title:'All NSE stocks',description:'Every current NSE EQ-series equity in the Dhan catalog',icon:Layers3},
  {mode:'all_bse',title:'All BSE stocks',description:'Current BSE cash-market equities in the Dhan catalog',icon:Database},
  {mode:'watchlist',title:'Paste a ticker list',description:'Import symbols from CSV or paste them directly',icon:FileSpreadsheet},
  {mode:'nifty50_pit',title:'NIFTY 50 · Historical',description:'Stocks belonging to the index at each date, including past removals',icon:History},
  {mode:'banknifty_pit',title:'BANK NIFTY · Historical',description:'Date-accurate banking index constituents, not just today’s banks',icon:Clock3},
]

export default function DhanDataManager({onDataChanged}:{onDataChanged:()=>void}){
  const [connection,setConnection]=useState<DhanStatus|null>(null)
  const [mode,setMode]=useState<SelectionMode>('selected')
  const [exchange,setExchange]=useState<'NSE'|'BSE'>('NSE')
  const [query,setQuery]=useState('')
  const [page,setPage]=useState(1)
  const [regularOnly,setRegularOnly]=useState(true)
  const [catalog,setCatalog]=useState<CatalogPage|null>(null)
  const [catalogBusy,setCatalogBusy]=useState(false)
  const [counts,setCounts]=useState({NSE:0,BSE:0})
  const [selected,setSelected]=useState<Record<string,CatalogItem>>({})
  const [watchlist,setWatchlist]=useState('')
  const [fromDate,setFromDate]=useState(yearAgo)
  const [toDate,setToDate]=useState(today)
  const [interval,setInterval]=useState('daily')
  const [acknowledged,setAcknowledged]=useState(false)
  const [acknowledgedGaps,setAcknowledgedGaps]=useState(false)
  const [pitPlan,setPitPlan]=useState<MembershipPlan|null>(null)
  const [pitSyncBusy,setPitSyncBusy]=useState(false)
  const [batches,setBatches]=useState<BatchSummary[]>([])
  const [batchId,setBatchId]=useState('')
  const [details,setDetails]=useState<BatchDetails|null>(null)
  const [statusFilter,setStatusFilter]=useState('all')
  const [detailPage,setDetailPage]=useState(1)
  const [working,setWorking]=useState(false)
  const [task,setTask]=useState<{id:string;kind:string}|null>(null)
  const [notice,setNotice]=useState<{text:string;error:boolean}|null>(null)
  const [preview,setPreview]=useState<{symbol:string;rows:Record<string,unknown>[]} | null>(null)
  const [previewLoading,setPreviewLoading]=useState(false)

  const tell=(text:string,error=false)=>setNotice({text,error})
  const loadConnection=useCallback(async()=>{
    const value=await api<DhanStatus>('/dhan/status')
    setConnection(value)
    return value
  },[])
  const loadBatches=useCallback(async()=>{
    const data=await api<{batches:BatchSummary[]}>('/dhan/batches')
    setBatches(data.batches)
    setBatchId(old=>old||data.batches[0]?.id||'')
  },[])
  const loadCounts=useCallback(async()=>{
    const [nse,bse]=await Promise.all([
      api<CatalogPage>('/dhan/catalog?exchange=NSE&per_page=1'),
      api<CatalogPage>('/dhan/catalog?exchange=BSE&per_page=1'),
    ])
    setCounts({NSE:nse.total,BSE:bse.total})
  },[])
  useEffect(()=>{
    let cancelled=false
    void Promise.all([loadConnection(),loadBatches()]).then(([status])=>{
      if(status.instrument_master_available&&!cancelled)void loadCounts().catch(e=>tell(String(e),true))
    }).catch(e=>{if(!cancelled)tell(e instanceof Error?e.message:String(e),true)})
    return()=>{cancelled=true}
  },[loadBatches,loadConnection,loadCounts])
  useEffect(()=>{
    if(!connection?.instrument_master_available){setCatalog(null);return}
    let cancelled=false
    setCatalogBusy(true)
    const timer=window.setTimeout(()=>{
      const params=new URLSearchParams({exchange,page:String(page),per_page:'50',
        query,regular_only:String(regularOnly)})
      void api<CatalogPage>('/dhan/catalog?'+params).then(r=>{
        if(!cancelled)setCatalog(r)
      }).catch(e=>{if(!cancelled){setCatalog(null);tell(e instanceof Error?e.message:String(e),true)}})
      .finally(()=>{if(!cancelled)setCatalogBusy(false)})
    },260)
    return()=>{cancelled=true;window.clearTimeout(timer)}
  },[connection?.instrument_master_available,exchange,query,page,regularOnly])

  const refreshDetails=useCallback(async(id:string)=>{
    const args=new URLSearchParams({page:String(detailPage),per_page:'40',status:statusFilter})
    const r=await api<BatchDetails>('/dhan/batches/'+id+'?'+args)
    setDetails(r)
    setBatches(old=>old.map(item=>item.id===r.id?{...item,...r}:item))
    return r
  },[detailPage,statusFilter])
  useEffect(()=>{
    if(!batchId){setDetails(null);return}
    let active=true
    const update=()=>{void refreshDetails(batchId).catch(e=>{if(active)tell(e instanceof Error?e.message:String(e),true)})}
    update()
    const timer=window.setInterval(update,1900)
    return()=>{active=false;window.clearInterval(timer)}
  },[batchId,refreshDetails])
  useEffect(()=>{
    if(!task)return
    let disposed=false
    const timer=window.setInterval(()=>{
      void api<TaskStatus>('/jobs/'+task.id).then(r=>{
        if(disposed||!['complete','error'].includes(r.status))return
        setTask(null)
        if(r.status==='error')tell(r.error||'Data operation failed',true)
        else {
          tell(task.kind==='master'?'Instrument master refreshed.':
            task.kind==='prepare'?'Monthly price matrix prepared and added to Data Manager.':
            'Download operation finished; see per-stock statuses below.')
          void loadConnection().then(status=>{if(status.instrument_master_available)void loadCounts()})
          void loadBatches()
          if(batchId)void refreshDetails(batchId)
          if(task.kind==='prepare')onDataChanged()
        }
      }).catch(e=>{if(!disposed)tell(e instanceof Error?e.message:String(e),true)})
    },1900)
    return()=>{disposed=true;window.clearInterval(timer)}
  },[task,batchId,loadBatches,loadConnection,loadCounts,refreshDetails,onDataChanged])

  const run=async<T,>(operation:()=>Promise<T>,onSuccess:(v:T)=>void)=>{
    setWorking(true)
    try{onSuccess(await operation())}
    catch(e){tell(e instanceof Error?e.message:String(e),true)}
    finally{setWorking(false)}
  }
  const refreshMaster=()=>void run(()=>post<{job_id:string}>('/dhan/instruments/refresh'),result=>{
    setTask({id:result.job_id,kind:'master'})
    tell('Refreshing the official instrument list in Python.')
  })
  const selectMode=(next:SelectionMode)=>{
    setMode(next);setAcknowledged(false);setAcknowledgedGaps(false);setPitPlan(null);setPreview(null)
    if(next==='all_nse')setExchange('NSE')
    if(next==='all_bse')setExchange('BSE')
  }
  const toggleStock=(item:CatalogItem)=>{
    setSelected(old=>{
      const copy={...old}
      if(copy[item.id])delete copy[item.id]
      else copy[item.id]=item
      return copy
    })
  }
  const visible=catalog?.items||[]
  const visibleSelected=visible.length>0&&visible.every(item=>!!selected[item.id])
  const toggleVisible=()=>{
    setSelected(old=>{
      const copy={...old}
      if(visibleSelected)visible.forEach(item=>delete copy[item.id])
      else visible.forEach(item=>{copy[item.id]=item})
      return copy
    })
  }
  const cleanedSymbols=useMemo(()=>{
    return Array.from(new Set(watchlist.split(/[,;\s]+/).map(x=>x.trim().toUpperCase())
      .filter(x=>x&&x!=='SYMBOL'&&x!=='TICKER')))
  },[watchlist])
  const pitMode=mode==='nifty50_pit'||mode==='banknifty_pit'
  const selectionCount=pitMode?(pitPlan?.union_count||0):mode==='all_nse'?counts.NSE:mode==='all_bse'?counts.BSE:
    mode==='selected'?Object.keys(selected).length:cleanedSymbols.length
  const downloadCount=pitMode?(pitPlan?.resolved_count||0):selectionCount
  const dateDays=(Date.parse(toDate)-Date.parse(fromDate))/86400000
  const daily=interval==='daily'
  const estimatedRequests=downloadCount*Math.ceil(Math.max(0,dateDays)/(daily?365:90))
  const tooManyIntraday=!daily&&downloadCount>100
  const invalidDates=!Number.isFinite(dateDays)||dateDays<=0
  const startDisabled=!connection?.token_configured||!connection?.instrument_master_available||
    downloadCount===0||working||Boolean(task)||pitSyncBusy||invalidDates||tooManyIntraday||
    (downloadCount>100&&!acknowledged)||
    (pitMode&&(!pitPlan||(pitPlan.unresolved_count>0&&!acknowledgedGaps)))
  const startBatch=()=>void run(()=>post<Job>('/dhan/batches',{
    selection:mode,ids:mode==='selected'?Object.keys(selected):[],
    tickers:mode==='watchlist'?cleanedSymbols:[],
    from_date:fromDate,to_date:toDate,
    interval:daily?null:Number(interval),acknowledged_bulk:acknowledged,
    acknowledged_gaps:pitMode&&acknowledgedGaps,
  }),result=>{
    const id=result.batch?.id
    if(id){setBatchId(id);setStatusFilter('all');setDetailPage(1)}
    setTask({id:result.job_id,kind:'batch'})
    tell('Batch started. The workstation saves each completed instrument and can resume later.')
    void loadBatches()
  })
  const resume=()=>{if(!batchId)return;void run(()=>post<Job>('/dhan/batches/'+batchId+'/resume'),r=>{
    setTask({id:r.job_id,kind:'batch'});tell('Resuming the pending and failed instruments.')
  })}
  const cancel=()=>{if(!batchId)return;void run(()=>post('/dhan/batches/'+batchId+'/cancel'),()=>{
    tell('Stop requested. The current Dhan request can finish before the queue pauses.')
  })}
  const prepare=()=>{if(!batchId)return;void run(()=>post<{job_id:string}>('/dhan/batches/'+batchId+'/prepare'),r=>{
    setTask({id:r.job_id,kind:'prepare'});tell('Building an unadjusted monthly price matrix from completed symbols.')
  })}
  const acceptFile=async(file:File)=>{
    if(file.size>1024*1024){tell('Ticker CSV is too large (1 MiB max).',true);return}
    try{
      const content=await file.text()
      const symbols=content.split(/\r?\n/).map(line=>line.split(',')[0].replaceAll('"','').trim())
        .filter((word,i)=>!!word&&(i!==0||!['symbol','ticker'].includes(word.toLowerCase())))
      setWatchlist(symbols.join('\n'));selectMode('watchlist')
      tell('Loaded '+fmt(symbols.length)+' tickers. Exact Dhan master mappings will be checked before downloading.')
    }catch{tell('Cannot read the selected watchlist file.',true)}
  }
  const previewRow=(item:CatalogItem)=>{
    setPreviewLoading(true)
    void api<{rows:Record<string,unknown>[];symbol:string}>('/dhan/history?instrument_id='+encodeURIComponent(item.id)
      +'&interval='+encodeURIComponent(String(details?.interval??'daily'))+'&limit=140')
      .then(setPreview).catch(e=>tell(e instanceof Error?e.message:String(e),true))
      .finally(()=>setPreviewLoading(false))
  }
  const currentActive=['running','queued'].includes(details?.status||'')
  const couldResume=Boolean(details)&&!currentActive
  const countsCompleted=(details?.counts.complete||0)+(details?.counts.cached||0)
  const progress=details?.total?Math.round((details.processed/details.total)*100):0

  return <div className="dh-workspace">
    <div className="dh-hero"><div><Pill tone="blue">DATA ACQUISITION · DHANHQ V2</Pill>
      <h2>Download an entire market.<br/><em>With its real historical membership.</em></h2>
      <p>Select individual stocks, an entire NSE/BSE cash market, or historically accurate NIFTY 50 and BANK NIFTY constituent groups. The selected dates determine which companies belong.</p>
    </div><div className="dh-hero-stats"><div><strong>{counts.NSE?fmt(counts.NSE):'—'}</strong><span>NSE EQ-series instruments</span></div><div><strong>{fmt(batches.length)}</strong><span>Saved download batches</span></div></div></div>

    <div className="dh-connect">
      <div><span className={'dh-led '+(connection?.token_configured?'':'off')}/><LockKeyhole size={17}/>
        <div><strong>{connection?.token_configured?'Dhan API connected':'Dhan API token missing'}</strong><small>{connection?.token_configured?'Secret is held by Python only':'Set DHAN_ACCESS_TOKEN in project-root .env'}</small></div></div>
      <div><span className={'dh-led '+(connection?.instrument_master_available?'':'off')}/><Database size={17}/>
        <div><strong>{connection?.instrument_master_available?'Instrument master available':'Instrument master missing'}</strong><small>Current Dhan security ID catalog</small></div></div>
      <button className="dh-small-btn" type="button" disabled={working||Boolean(task)} onClick={refreshMaster}>
        {task?.kind==='master'?<LoaderCircle size={15} className="dh-spin"/>:<RefreshCw size={15}/>}
        Refresh instrument catalog
      </button>
    </div>

    {notice&&<div className={'dh-notice '+(notice.error?'error':'')} role="status">
      {notice.error?<CircleAlert size={17}/>:<CheckCircle2 size={17}/>}<span>{notice.text}</span>
      <button onClick={()=>setNotice(null)} aria-label="Dismiss notice"><X size={15}/></button>
    </div>}

    <div className="dh-stage"><span>01</span><div><h3>Choose your universe</h3><p>No Security IDs to copy. Every selection is resolved against Dhan's official catalog.</p></div></div>
    <div className="dh-mode-grid">{options.map(item=><button type="button" key={item.mode} className={'dh-mode '+(mode===item.mode?'active':'')} onClick={()=>selectMode(item.mode)}>
      <span className="dh-mode-icon"><item.icon size={20}/></span><strong>{item.title}</strong><small>{item.description}</small>
      {mode===item.mode&&<span className="dh-mode-selected"><Check size={13}/></span>}</button>)}</div>

    <div className="dh-grid">
      <Section title={pitMode?'Historical index membership':mode==='watchlist'?'Your ticker list':'Find and select stocks'} aside={<Pill tone="blue">{pitMode?'Union: '+fmt(selectionCount):fmt(selectionCount)+' in selection'}</Pill>}>
        {pitMode?<PITIndexPanel mode={mode as PITMode} fromDate={fromDate} toDate={toDate} onToDate={setToDate} onPlan={setPitPlan} onSyncBusy={setPitSyncBusy}/>:mode==='watchlist'?<div className="dh-paste">
          <p>Paste exact NSE tickers, separated by commas or lines. Or upload a CSV with symbols in the first column.</p>
          <textarea rows={11} spellCheck={false} value={watchlist} onChange={e=>setWatchlist(e.target.value)}
            placeholder={'RELIANCE\nTCS\nINFY\nHDFCBANK\nICICIBANK'} aria-label="NSE ticker list"/>
          <label className="dh-small-btn"><UploadCloud size={15}/> Import watchlist CSV
            <input type="file" hidden accept=".csv,.txt" onChange={e=>{const file=e.target.files?.[0];if(file)void acceptFile(file);e.target.value=''}}/>
          </label><p className="dh-hint">No guessed symbol matches: ambiguous or unknown names are rejected with an explanation.</p>
        </div>:<>
          {mode!=='selected'&&<div className="dh-all-notice"><Layers3 size={20}/><div><strong>{mode==='all_nse'?'NSE':'BSE'} equity universe is selected</strong>
            <p>{fmt(selectionCount)} currently listed cash-market equity instruments from Dhan's master. The search table is for inspection only—no need to select each stock.</p></div></div>}
          <div className="dh-searchbar"><Search size={17}/><input aria-label="Search ticker or company" value={query} onChange={e=>{setQuery(e.target.value);setPage(1)}} placeholder="Search ticker, company, Security ID or ISIN…"/>
            {query&&<button aria-label="Clear search" onClick={()=>{setQuery('');setPage(1)}}><X size={15}/></button>}
            <select aria-label="Exchange" value={exchange} onChange={e=>{setExchange(e.target.value as 'NSE'|'BSE');setPage(1)}}><option value="NSE">NSE</option><option value="BSE">BSE</option></select></div>
          <div className="dh-filter"><label><input type="checkbox" checked={regularOnly} onChange={e=>{setRegularOnly(e.target.checked);setPage(1)}}/> Regular EQ series only</label><span>{catalogBusy?'Searching…':catalog?fmt(catalog.total)+' matches':'No catalog loaded'}</span></div>
          <div className="dh-list">
            {mode==='selected'&&visible.length>0&&<button className="dh-select-page" onClick={toggleVisible}>
              <span className={'dh-box '+(visibleSelected?'checked':'')}>{visibleSelected&&<Check size={12}/>}</span>
              {visibleSelected?'Remove all visible':'Add all visible'} ({visible.length})
            </button>}
            {!connection?.instrument_master_available?<div className="dh-list-empty">Refresh the Dhan instrument catalog to browse securities.</div>:
              visible.length===0?<div className="dh-list-empty">No matching stocks. Try a different name or exchange.</div>:
              visible.map(item=><button type="button" className={'dh-instrument '+(selected[item.id]?'chosen':'')} key={item.id} onClick={()=>{if(mode!=='selected')selectMode('selected');toggleStock(item)}}>
                <span className={'dh-box '+(selected[item.id]?'checked':'')}>{selected[item.id]&&<Check size={12}/>}</span>
                <span className="dh-instrument-main"><strong>{item.symbol}</strong><small title={item.display_name}>{item.display_name}</small></span>
                <span className="dh-instrument-meta"><small>{item.exchange_segment}</small><small>{item.series}</small></span>
                <span className="dh-instrument-id">{item.security_id}</span>
              </button>)}
          </div>
          {catalog&&<div className="dh-pages"><button disabled={page<=1} onClick={()=>setPage(v=>v-1)}><ChevronLeft size={16}/> Previous</button>
            <span>Page {page} of {Math.max(1,Math.ceil(catalog.total/catalog.per_page))}</span>
            <button disabled={!catalog.has_more} onClick={()=>setPage(v=>v+1)}>Next <ChevronRight size={16}/></button></div>}
        </>}
      </Section>

      <Section title="Download settings" aside={<Pill tone="good"><ShieldCheck size={13}/> Read-only historical data</Pill>}>
        <div className="dh-settings">
          <div className="dh-picked-head"><span>Selected universe</span><strong>{interpretMode(mode)}</strong></div>
          <div className="dh-selection-count"><strong>{fmt(downloadCount)}</strong><span>{pitMode?'Dhan-mapped historical stocks': 'instruments'}</span></div>
          {pitMode&&pitPlan&&<p className="dh-hint">{fmt(pitPlan.union_count)} distinct index constituents during this period; {fmt(pitPlan.resolved_count)} have unambiguous current Dhan IDs. The downloaded set is their historical union, not today’s constituents.</p>}
          {mode==='selected'&&<div className="dh-selected-pills">
            {Object.values(selected).slice(0,18).map(item=><button key={item.id} onClick={()=>toggleStock(item)} title={'Remove '+item.symbol}>{item.symbol}<X size={12}/></button>)}
            {Object.keys(selected).length>18&&<span>+{Object.keys(selected).length-18} more</span>}
            {Object.keys(selected).length===0&&<p>No stocks selected. Click an instrument on the left.</p>}
          </div>}
          <div className="dh-settings-fields"><label><span>From · inclusive</span><input type="date" value={fromDate} onChange={e=>setFromDate(e.target.value)}/></label>
            <label><span>To · exclusive</span><input type="date" value={toDate} onChange={e=>setToDate(e.target.value)}/></label>
            <label className="dh-full"><span>Candle resolution</span><select value={interval} onChange={e=>setInterval(e.target.value)}>
              <option value="daily">Daily OHLCV · best for bulk research</option>
              <option value="60">60-minute candles</option>
              <option value="15">15-minute candles</option>
              <option value="5">5-minute candles</option>
              <option value="1">1-minute candles</option>
            </select></label></div>
          <div className="dh-estimate"><div><span>Estimated API calls</span><strong>{Number.isFinite(estimatedRequests)?'≈ '+fmt(estimatedRequests):'—'}</strong></div>
            <small>Rough minimum before retries; actual calls depend on date windows and cached coverage. Dhan applies its own limits.</small></div>
          {tooManyIntraday&&<p className="dh-error-note">Intraday batches are limited to 100 instruments. Use daily candles for full-market downloads.</p>}
          {invalidDates&&<p className="dh-error-note">The end date must be later than the start date.</p>}
          {downloadCount>100&&<label className="dh-confirm"><input type="checkbox" checked={acknowledged} onChange={e=>setAcknowledged(e.target.checked)}/>
            <span>I understand this will request historical data for {fmt(downloadCount)} instruments. This may be a long-running operation and use my Dhan API allowance.</span></label>}
          {pitMode&&pitPlan?.unresolved_count? <label className="dh-confirm"><input type="checkbox" checked={acknowledgedGaps} onChange={e=>setAcknowledgedGaps(e.target.checked)}/>
            <span>Download the {fmt(pitPlan.resolved_count)} mapped stocks even though {fmt(pitPlan.unresolved_count)} historical constituents cannot be resolved in the current Dhan catalog. Mark the resulting historical-price dataset INCOMPLETE.</span></label>:null}
          <button className="dh-primary" type="button" disabled={startDisabled} onClick={startBatch}>
            {working?<LoaderCircle size={17} className="dh-spin"/>:<ArrowDownToLine size={18}/>}
            Download {downloadCount?fmt(downloadCount)+(pitMode?' historical constituents':' instruments'):'selected stocks'}
            <ArrowRight size={17}/></button>
          <p className="dh-hint">Files are stored locally by Dhan Security ID. Repeated date ranges reuse verified cached candles; no orders are placed.</p>
        </div>
      </Section>
    </div>

    <div className="dh-stage"><span>02</span><div><h3>Download queue & progress</h3><p>Review each instrument's status, pause between requests, and resume failed or interrupted batches.</p></div></div>
    <Section title="Download history" aside={<button className="dh-small-btn" type="button" onClick={()=>void loadBatches()}><RefreshCw size={14}/> Refresh</button>}>
      {batches.length>0?<div className="dh-library">
        {batches.slice(0,14).map(b=><button type="button" key={b.id} className={'dh-batch-row '+(batchId===b.id?'active':'')} onClick={()=>{setBatchId(b.id);setDetailPage(1);setStatusFilter('all');setPreview(null)}}>
          <span className="dh-batch-icon"><History size={17}/></span>
          <span className="dh-batch-name"><strong>{interpretMode(b.selection)}</strong><small>{b.from_date} → {b.to_date} · {b.interval===null?'Daily':b.interval+' min'}</small></span>
          <span className="dh-batch-numbers">{fmt(b.processed)} / {fmt(b.total)}</span>
          <Pill tone={b.status==='completed'?'good':b.status==='running'?'blue':'warning'}>{statusText(b.status)}</Pill>
          <ChevronRight size={16}/>
        </button>)}
      </div>:<div className="dh-empty"><Clock3 size={27}/><strong>No download batches yet</strong><p>Choose a universe and start downloading. The results will appear here and remain available after a restart.</p></div>}
      {details&&<div className="dh-batch-detail">
        <div className="dh-batch-title"><div><strong>Batch {details.id.slice(-8)}</strong><span> · {interpretMode(details.selection)} · {fmt(details.total)} instruments</span></div>
          <Pill tone={details.status==='completed'?'good':currentActive?'blue':'warning'}>{statusText(details.status)}</Pill></div>
        <div className="dh-meter"><span style={{width:progress+'%'}}/></div>
        <div className="dh-progress-label"><span>{progress}% processed {details.current_symbol?'· Now: '+details.current_symbol:''}</span>
          <span>{fmt(details.processed)} / {fmt(details.total)}</span></div>
        <div className="dh-progress-cards">{[
          ['Downloaded',details.counts.complete||0],['Cached',details.counts.cached||0],
          ['No data',details.counts.no_data||0],['Failed',details.counts.failed||0],
        ].map(([name,value])=><div key={name}><strong>{fmt(Number(value))}</strong><span>{name}</span></div>)}</div>
        <div className="dh-queue-actions">
          {currentActive?<button className="dh-small-btn" onClick={cancel}><Pause size={15}/> Pause after current request</button>:
            couldResume&&<button className="dh-small-btn" disabled={working||Boolean(task)} onClick={resume}><Play size={15}/> Resume / retry remaining</button>}
          {details.interval===null&&countsCompleted>0&&!details.prepared_dataset_id&&
            <button className="dh-small-btn primary" disabled={working||Boolean(task)||currentActive} onClick={prepare}><FileSpreadsheet size={16}/> Prepare monthly price matrix</button>}
          {details.prepared_dataset_id&&<Pill tone="good">Prepared dataset: {details.prepared_dataset_id}</Pill>}
          {details.historical_index_name&&<div className="dh-pit-in-batch"><strong>{details.historical_index_name} · dated membership</strong><span>Universe: {details.historical_union_count} unique symbols · {details.historical_unresolved?.length||0} have no Dhan ID. Preparing daily candles writes membership.csv from saved effective-date intervals; a compatible benchmark remains required.</span></div>}
        </div>
        <div className="dh-detail-toolbar"><span>Per-stock results</span>
          <select aria-label="Filter download result status" value={statusFilter} onChange={e=>{setStatusFilter(e.target.value);setDetailPage(1)}}>
            <option value="all">All statuses</option><option value="complete">Downloaded</option>
            <option value="cached">Cached</option><option value="failed">Failed</option>
            <option value="no_data">No data</option><option value="pending">Pending</option>
          </select></div>
        <div className="dh-result-table"><table><thead><tr><th>Symbol</th><th>Security ID</th><th>Status</th><th>Rows</th><th>Details</th></tr></thead><tbody>
          {details.items.map(item=><tr key={item.id}><td><strong>{item.symbol}</strong><small>{item.exchange_segment}</small></td><td>{item.security_id}</td>
            <td><Pill tone={['complete','cached'].includes(item.status)?'good':item.status==='failed'?'warning':'muted'}>{statusText(item.status)}</Pill></td>
            <td>{fmt(item.rows||0)}</td><td>{item.error?<span className="dh-error-note" title={item.error}>{item.error}</span>:
              ['complete','cached'].includes(item.status)?<button className="dh-view" onClick={()=>previewRow(item)}>Preview candles</button>:'—'}</td></tr>)}
        </tbody></table></div>
        <div className="dh-pages"><button disabled={detailPage<=1} onClick={()=>setDetailPage(v=>v-1)}><ChevronLeft size={15}/> Previous</button>
          <span>{fmt(details.filtered_total)} instruments · Page {detailPage}</span>
          <button disabled={detailPage*details.per_page>=details.filtered_total} onClick={()=>setDetailPage(v=>v+1)}>Next <ChevronRight size={15}/></button></div>
        {previewLoading&&<p className="dh-hint">Loading cached candle preview…</p>}
        {preview&&<div className="dh-preview"><div><strong>{preview.symbol} · last {preview.rows.length} candles</strong><button aria-label="Close preview" onClick={()=>setPreview(null)}><X size={15}/></button></div>
          <div className="dh-result-table"><table><thead><tr><th>Timestamp</th><th>Open</th><th>High</th><th>Low</th><th>Close</th><th>Volume</th></tr></thead><tbody>{preview.rows.slice(-30).reverse().map((row,i)=><tr key={i}>{['datetime','open','high','low','close','volume'].map(key=><td key={key}>{String(row[key]??'—')}</td>)}</tr>)}</tbody></table></div>
        </div>}
      </div>}
    </Section>
    <div className="dh-footnote"><ShieldCheck size={18}/><p><strong>Research integrity:</strong> Historical NIFTY memberships are reconstructed from dated NSE notices with recorded source versions. Unresolved delisted/renamed instruments and missing OHLCV are reported, never silently replaced. Price history is not dividend-reinvested total return data; completed index backtests still require benchmark and corporate-action verification.</p></div>
  </div>
}

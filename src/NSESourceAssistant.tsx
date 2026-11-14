import {useEffect,useState} from 'react'
import {CheckCircle2,Database,ExternalLink,RefreshCw,Search,ShieldAlert,Upload} from 'lucide-react'
import './nse-source-assistant.css'

type Task='corporate_actions'|'stock_history'|'symbol_search'|'index_history'
type Capability={configured:boolean;connection:string;tasks:{id:Task;name:string;purpose:string}[];
  note:string;research_data_write_allowed:boolean}
type Lookup={status:'available'|'provider_unavailable';task:Task;provider:string;
  message?:string;data?:unknown;corporate_actions_context?:unknown;
  warnings?:string[];research_data_updated:boolean;no_events_verified:boolean;
  checked_utc?:string;suggested_next_step?:string}
type Receipt={status:string;receipt:{id:string;directory:string;files:{name:string;original_sha256:string}[];
  weightage_csv_candidates:number;warning:string};tri_preserved:boolean;research_data_updated:boolean;
  next_action:string}
type Props={datasetId?:string;suggestedSymbol?:string;onOpenDhan?:()=>void;onOpenData?:()=>void}

async function api<T>(path:string,body?:unknown):Promise<T>{
  let response:Response
  try{response=await fetch('/api/workspace/nse-sources/'+path,{
    method:body===undefined?'GET':'POST',credentials:'same-origin',
    headers:body===undefined?undefined:{'Content-Type':'application/json'},
    body:body===undefined?undefined:JSON.stringify(body)})}
  catch{throw new Error('QuantLab local source service is offline. Open the app normally to start it.')}
  if(!response.ok){
    let message='NSE source request failed (HTTP '+response.status+')'
    try{const data=await response.json() as {detail?:string};if(data.detail)message=data.detail}catch{}
    throw new Error(message)
  }
  return await response.json() as T
}

function formatDate(date:Date){return date.toISOString().slice(0,10)}
const today=formatDate(new Date())
const yearAgo=formatDate(new Date(Date.now()-365*24*60*60*1000))
const TASKS:{id:Task;name:string;description:string}[]=[
  {id:'corporate_actions',name:'Corporate actions',description:'Look up dated dividends, splits and bonuses'},
  {id:'stock_history',name:'Stock prices',description:'Check up to 3 months of raw OHLCV and corporate actions'},
  {id:'symbol_search',name:'Find a stock',description:'Discover a current NSE ticker'},
  {id:'index_history',name:'Index context',description:'Inspect index prices — not NIFTY TRI'},
]

export default function NSESourceAssistant({datasetId,suggestedSymbol='',onOpenDhan,onOpenData}:Props){
  const [capabilities,setCapabilities]=useState<Capability|null>(null)
  const [task,setTask]=useState<Task>('corporate_actions')
  const [symbol,setSymbol]=useState('')
  const [term,setTerm]=useState('')
  const [indexName,setIndexName]=useState('Nifty 50')
  const [fromDate,setFromDate]=useState(yearAgo)
  const [toDate,setToDate]=useState(today)
  const [months,setMonths]=useState('3')
  const [busy,setBusy]=useState<'query'|'check'|'intake'|null>(null)
  const [connection,setConnection]=useState<'not_checked'|'connected'|'unavailable'>('not_checked')
  const [checkDetail,setCheckDetail]=useState('')
  const [result,setResult]=useState<Lookup|null>(null)
  const [error,setError]=useState('')
  const [files,setFiles]=useState<File[]>([])
  const [receipt,setReceipt]=useState<Receipt|null>(null)

  useEffect(()=>{
    let active=true
    void api<Capability>('capabilities').then(value=>{if(active)setCapabilities(value)})
      .catch(e=>{if(active)setError(e instanceof Error?e.message:String(e))})
    return()=>{active=false}
  },[])
  useEffect(()=>{
    if(suggestedSymbol&&/^[A-Z][A-Z0-9&._-]{0,24}$/i.test(suggestedSymbol)){
      setSymbol(suggestedSymbol.toUpperCase())
    }
  },[suggestedSymbol,datasetId])
  useEffect(()=>{setResult(null);setError('')},[task,datasetId])

  const check=async()=>{
    setBusy('check');setError('')
    try{
      const response=await api<{status:'connected'|'unavailable';note:string}>('check',{})
      setConnection(response.status);setCheckDetail(response.note)
    }catch(e){setConnection('unavailable');setError(e instanceof Error?e.message:String(e))}
    finally{setBusy(null)}
  }

  const lookup=async()=>{
    if(busy)return
    setBusy('query');setError('');setResult(null)
    const parameters:Record<string,string|number>={
      task,symbol:symbol.trim().toUpperCase(),query:term.trim(),
      index_name:indexName.trim(),from_date:fromDate,to_date:toDate,
      end_date:toDate,months:Number(months),
    }
    try{
      const output=await api<Lookup>('query',parameters)
      setResult(output)
      if(output.status==='provider_unavailable')setConnection('unavailable')
      else setConnection('connected')
    }catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setBusy(null)}
  }

  const intake=async()=>{
    if(!files.length||busy)return
    setBusy('intake');setError('');setReceipt(null)
    try{
      const form=new FormData()
      files.forEach(file=>form.append('files',file))
      const response=await fetch('/api/workspace/nse-sources/intake',{
        method:'POST',credentials:'same-origin',body:form})
      if(!response.ok){
        let detail='Source file could not be prepared (HTTP '+response.status+')'
        try{const body=await response.json() as {detail?:string};if(body.detail)detail=body.detail}catch{}
        throw new Error(detail)
      }
      setReceipt(await response.json() as Receipt)
      setFiles([])
    }catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setBusy(null)}
  }

  return <section className="nse-source-assistant" aria-label="NSE Source Assistant">
    <header className="nse-header">
      <div><span className="nse-eyebrow">OFFICIAL NSE MCP · INTEGRATED</span>
        <h3>NSE Source Assistant</h3>
        <p>Look up a source in QuantLab. No terminal, API key or website scraper required.
          QuantLab chooses the official MCP tool for your request.</p></div>
      <button type="button" disabled={busy!==null} onClick={()=>void check()}>
        <RefreshCw size={14}/> {busy==='check'?'Checking…':'Check connection'}</button>
    </header>
    <div className="nse-connection" aria-live="polite">
      <span className={'nse-status '+connection}>
        {connection==='connected'?<CheckCircle2 size={14}/>:<ShieldAlert size={14}/>}
        {connection==='connected'?'NSE MCP reachable':connection==='unavailable'
          ?'NSE source currently unavailable':'NSE MCP · available to check'}</span>
      {checkDetail&&<span>{checkDetail}</span>}
      {capabilities&&!capabilities.research_data_write_allowed&&
        <small>Informational results only · Existing TRI and research data stay unchanged</small>}
    </div>
    <div className="nse-context" role="note">
      {datasetId?'Current research dataset: '+datasetId+'. ':'No research dataset selected. '}
      {suggestedSymbol?'A missing-data source suggests checking '+suggestedSymbol+'. ':''}
      Price-history observations for backtesting still use your authorized Dhan feed.
      Official NSE index price levels never replace TRI.
    </div>
    <div className="nse-task-tabs" role="tablist" aria-label="Choose NSE source check">
      {TASKS.map(item=><button key={item.id} type="button" role="tab"
        aria-selected={task===item.id} className={task===item.id?'active':''}
        onClick={()=>setTask(item.id)}>{item.name}</button>)}
    </div>
    <p className="nse-task-description">{TASKS.find(t=>t.id===task)?.description}</p>
    <div className="nse-form">
      {(task==='corporate_actions'||task==='stock_history')&&
        <label>Stock symbol<input aria-label="NSE stock symbol" value={symbol}
          placeholder="RELIANCE" maxLength={25} onChange={e=>setSymbol(e.target.value.toUpperCase())}/></label>}
      {task==='symbol_search'&&
        <label>Company name or symbol<input aria-label="Search NSE symbols" value={term}
          placeholder="TATA" maxLength={50} onChange={e=>setTerm(e.target.value)}/></label>}
      {task==='index_history'&&
        <label>Index name<input aria-label="NSE index name" value={indexName}
          maxLength={60} onChange={e=>setIndexName(e.target.value)}/></label>}
      {task==='corporate_actions'&&
        <label>From<input aria-label="Corporate actions from" type="date" value={fromDate}
          max={toDate} onChange={e=>setFromDate(e.target.value)}/></label>}
      {task!=='symbol_search'&&
        <label>{task==='corporate_actions'?'To':'End date'}
          <input aria-label="NSE lookup end date" type="date" value={toDate}
            onChange={e=>setToDate(e.target.value)}/></label>}
      {(task==='stock_history'||task==='index_history')&&
        <label>Months to inspect<select aria-label="NSE history months" value={months}
          onChange={e=>setMonths(e.target.value)}>
          {(task==='stock_history'?[1,2,3]:[1,3,6,12]).map(month=>
            <option key={month} value={month}>{month} month{month!==1?'s':''}</option>)}
        </select></label>}
    </div>
    <div className="nse-buttons">
      <button className="nse-primary" type="button" disabled={busy!==null||
        (task==='symbol_search'?!term.trim():task==='index_history'?!indexName.trim():!symbol.trim())}
        onClick={()=>void lookup()}>
        <Search size={15}/>{busy==='query'?'Checking NSE…':'Check NSE source'}</button>
      {onOpenDhan&&<button type="button" onClick={onOpenDhan}>
        <Database size={14}/> Research prices: Dhan</button>}
    </div>
    {error&&<p className="nse-error" role="alert"><ShieldAlert size={15}/>{error}</p>}
    {result?.status==='provider_unavailable'&&
      <div className="nse-error" role="alert">
        <ShieldAlert size={17}/><div><strong>NSE could not provide this source</strong>
          <p>{result.message}</p>
          <p>This does <strong>not</strong> mean there are zero corporate actions
            or that the dataset is complete. Use an original report or retry later.</p>
          <button type="button" disabled={busy!==null} onClick={()=>void lookup()}>Retry source check</button>
        </div>
      </div>}
    {result?.status==='available'&&
      <div className="nse-success" role="status">
        <CheckCircle2 size={17}/><div><strong>Informational NSE response received</strong>
          {result.warnings?.map((warning,i)=><p key={i} className="nse-warning">{warning}</p>)}
          <p>No model input, benchmark, or saved TRI was changed.</p>
          <details><summary>Inspect original source response</summary>
            <pre>{JSON.stringify({data:result.data,
              corporate_actions_context:result.corporate_actions_context},null,2).slice(0,25000)}</pre>
          </details></div>
      </div>}
    <div className="nse-import" aria-label="Prepare authorized original NSE files">
      <h4>Prepare NSE reports inside QuantLab</h4>
      <p>Choose authorized NSE/NSE Indices CSV, ZIP, XLSX or PDF files.
        QuantLab safely unpacks CSVs, records their hashes, and creates a
        dated-manifest template where appropriate. No scripts or manual extraction.</p>
      <label className="nse-upload-label">
        Choose downloaded source files<input aria-label="Select NSE source files"
          type="file" multiple accept=".csv,.zip,.xlsx,.xls,.pdf"
          onChange={e=>setFiles(Array.from(e.target.files||[]))}/>
      </label>
      <div className="nse-buttons">
        <button type="button" disabled={!files.length||busy!==null} onClick={()=>void intake()}>
          <Upload size={15}/>{busy==='intake'?'Preparing files…':
            'Prepare '+(files.length||'')+' source file'+(files.length===1?'':'s')}</button>
        {onOpenData&&<button type="button" onClick={onOpenData}>
          <Database size={14}/> Data Library</button>}
      </div>
      {receipt&&<div className="nse-receipt" role="status">
        <CheckCircle2 size={16}/><div><strong>Original files safely prepared</strong>
          <p>Receipt {receipt.receipt.id} · {receipt.receipt.files.length} original file(s)
            · {receipt.receipt.weightage_csv_candidates} possible index-weight CSV(s).</p>
          <p>These files are local and unverified. Confirm the real publication
            dates before applying them to a research dataset. TRI is preserved.</p>
          <details><summary>View source checksums</summary>
            <ul>{receipt.receipt.files.map(file=>
              <li key={file.name}>{file.name}: <code>{file.original_sha256}</code></li>)}</ul>
          </details></div>
      </div>}
    </div>
    <p className="nse-footnote">NSE MCP results are informational and may be temporarily unavailable.
      Index price levels are not TRI. QuantLab never treats an unavailable response as zero events,
      invents historical observations, performs broker orders, or bypasses data licenses.
      <a href="https://www.nseindia.com/nse-mcp" target="_blank" rel="noopener noreferrer">
        NSE MCP documentation <ExternalLink size={12}/></a>
    </p>
  </section>
}

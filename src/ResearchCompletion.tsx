import {useEffect,useState} from 'react'
import {BookOpen,Database,Download,FlaskConical,LoaderCircle,Play,
  RefreshCw,Save,ShieldAlert,ShieldCheck} from 'lucide-react'
import ResearchPlot,{type ResearchPlotData} from './ResearchPlots'

type Dataset={id:string;label:string;has_prices:boolean}
type RecordItem={id:string;kind:string;title:string;payload:Record<string,unknown>;trashed:boolean}
type Job={job_id:string;status:string}
type EvidenceRow={category:string;label:string;criterion:string;status:string;
  evidence_present:boolean;source_references:{source_url?:string;as_of?:string;stale:boolean}[]}
type Audit={dataset_id:string;dataset:string;source_sha256:string|null;
  evidence:EvidenceRow[];documented_categories:number;missing_categories:string[];
  ready_for_descriptive_prices:boolean;historical_investability_certified:boolean;
  prospective_trading_certified:boolean;warning:string}
type Plan={dataset_id:string;available:boolean;reason?:string;
  instrument_column?:string;symbol?:string;from_date?:string;
  to_date_exclusive?:string;cached_sample_sessions?:number;
  source_sha256?:string;note?:string}
type Probe={status:string;stale?:boolean;compared_sessions?:number;
  mismatched_sessions?:number;checked_utc?:string;warning?:string}
type Ready={asset:string;ready:boolean;observed_prices:number;usable_lagged_samples:number;
  minimum_samples:number;preferred_samples:number;missing_minimum:number;
  missing_preferred:number;warning:string}
type Study={kind:string;method:string;asset:string;plot:ResearchPlotData;
  train_observations:number;test_observations:number;holdout_total_return_net:number;
  passive_total_return_price_only:number;last_training_label_date:string;
  first_test_decision_date:string;warning:string}
type Props={datasets:Dataset[];selectedDataset:string;onSelectDataset:(v:string)=>void;
  records:RecordItem[];onOpenDhan:()=>void;
  onStartJob:(job:Job,label:string)=>void;onChanged:()=>void}

async function api<T>(route:string,body?:object):Promise<T>{
  const r=await fetch('/api/workspace/'+route,body?
    {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:
    {method:'GET'})
  if(!r.ok){
    const payload=await r.json().catch(()=>({detail:'Research engine request failed'})) as {detail?:string}
    throw new Error(payload.detail||'Research engine request failed')
  }
  return r.json() as Promise<T>
}
function Panel({title,children}:{title:string;children:React.ReactNode}){
  return <section className="rw-box"><header className="rw-box-head"><h3>{title}</h3></header>{children}</section>
}
function Cell({title,value}:{title:string;value:string|number}){
  return <div><small>{title}</small><strong>{value}</strong></div>
}
function ExportJson({name,data}:{name:string;data:object}){
  const send=()=>{
    const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}))
    const a=document.createElement('a');a.href=url;a.download=name;document.body.appendChild(a)
    a.click();a.remove();window.setTimeout(()=>URL.revokeObjectURL(url),800)
  }
  return <button onClick={send}><Download size={14}/> Export evidence JSON</button>
}
export default function ResearchCompletion({datasets,selectedDataset,onSelectDataset,
  records,onOpenDhan,onStartJob,onChanged}:Props){
  const [tab,setTab]=useState<'evidence'|'live'|'learning'>('evidence')
  const [audit,setAudit]=useState<Audit|null>(null)
  const [plan,setPlan]=useState<Plan|null>(null)
  const [previous,setPrevious]=useState<Probe|null>(null)
  const [columns,setColumns]=useState<string[]>([])
  const [asset,setAsset]=useState('')
  const [ready,setReady]=useState<Ready|null>(null)
  const [category,setCategory]=useState('membership')
  const [sourceUrl,setSourceUrl]=useState('')
  const [asOf,setAsOf]=useState('')
  const [note,setNote]=useState('')
  const [model,setModel]=useState('ridge')
  const [fraction,setFraction]=useState('0.70')
  const [cost,setCost]=useState('8')
  const [seed,setSeed]=useState('2026')
  const [selectedStudy,setSelectedStudy]=useState('')
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')
  const [message,setMessage]=useState('')
  useEffect(()=>{
    let mounted=true
    setAudit(null);setPlan(null);setPrevious(null);setColumns([]);setAsset('');setReady(null)
    if(!selectedDataset)return
    const source=encodeURIComponent(selectedDataset)
    void Promise.all([
      api<Audit>('integrity/'+source),
      api<Plan>('dhan-live/plan?dataset_id='+source),
      api<Probe>('dhan-live/previous?dataset_id='+source),
      api<{columns:string[]}>('plot-builder/columns/'+source),
    ]).then(([e,p,v,c])=>{
      if(!mounted)return
      setAudit(e);setPlan(p);setPrevious(v)
      setColumns(c.columns)
      setAsset(c.columns[0]||'')
    }).catch(e=>{if(mounted)setError(e instanceof Error?e.message:String(e))})
    return()=>{mounted=false}
  },[selectedDataset])
  useEffect(()=>{
    let mounted=true
    setReady(null)
    if(selectedDataset&&asset){
      void api<Ready>('learning/readiness?dataset_id='+encodeURIComponent(selectedDataset)+
        '&asset='+encodeURIComponent(asset))
        .then(v=>{if(mounted)setReady(v)})
        .catch(e=>{if(mounted)setError(e instanceof Error?e.message:String(e))})
    }
    return()=>{mounted=false}
  },[selectedDataset,asset])
  const reload=async()=>{
    if(!selectedDataset)return
    setBusy(true);setError('')
    try{
      const source=encodeURIComponent(selectedDataset)
      const [e,p,v]=await Promise.all([
        api<Audit>('integrity/'+source),
        api<Plan>('dhan-live/plan?dataset_id='+source),
        api<Probe>('dhan-live/previous?dataset_id='+source),
      ])
      setAudit(e);setPlan(p);setPrevious(v)
      setMessage('Evidence recalculated against the currently saved price checksum.')
    }catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setBusy(false)}
  }
  const submit=async()=>{
    setBusy(true);setError('')
    try{
      const result=await api<{review_status:string}>('integrity/'+encodeURIComponent(selectedDataset)+
        '/sources',{category,source_url:sourceUrl,as_of:asOf,explanation:note})
      setMessage('Evidence reference recorded as '+result.review_status+' — NOT certified.')
      setSourceUrl('');setNote('');await reload()
    }catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setBusy(false)}
  }
  const probe=async()=>{
    if(!plan?.available||!plan.instrument_column)return
    if(!window.confirm('Make ONE read-only historical-data request to Dhan for '+plan.symbol+
      '? This compares previously cached prices and does NOT append or submit orders.'))return
    setBusy(true);setError('')
    try{
      const job=await api<Job>('dhan-live/probe',{
        dataset_id:selectedDataset,column:plan.instrument_column,confirm:true,
      })
      onStartJob(job,'Dhan read-only verification')
      setMessage('Verification queued. See Jobs for the result; use Refresh to inspect recorded evidence.')
    }catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setBusy(false)}
  }
  const learning=async()=>{
    if(!ready?.ready)return
    if(!window.confirm('Run a chronological '+model+' research study on '+asset+
      '? Backtest has a one-session execution delay and is NOT live trading.'))return
    setBusy(true);setError('')
    try{
      const job=await api<Job>('learning/run',{dataset_id:selectedDataset,
        asset,method:model,train_fraction:Number(fraction),
        cost_bps:Number(cost),seed:Number(seed),confirm:true})
      onStartJob(job,'CPU research · '+model)
      setMessage('Research started. When the saved study finishes, its plot and full return CSV appear here.')
      onChanged()
    }catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setBusy(false)}
  }
  const studies=records.filter(x=>x.kind==='study'&&!x.trashed&&
    x.payload.kind==='learning_holdout')
  const study=studies.find(x=>x.id===selectedStudy)||
    (studies.length?studies[0]:null)
  const payload=study?.payload as unknown as Study|undefined
  return <div className="rw-stack">
    <div className="rw-segments">
      {([['evidence','Evidence & Certification'],['live','Live Dhan Check'],
        ['learning','ML / RL Holdout']] as const).map(([id,label])=>
        <button key={id} className={tab===id?'active':''} onClick={()=>setTab(id)}>
          {id==='evidence'?<ShieldCheck size={14}/>:id==='live'?<Database size={14}/>:<FlaskConical size={14}/>}
          {label}</button>)}
    </div>
    <Panel title="Choose the source of observed prices">
      <p className="rw-help">This review reads the existing canonical price views. It never creates replacement NIFTY or BANK NIFTY datasets, alters held prices, or treats missing evidence as zero.</p>
      <div className="rw-form-grid">
        <label className="rw-field"><span>Observed dataset</span>
          <select value={selectedDataset} onChange={e=>onSelectDataset(e.target.value)}>
            <option value="">Select observed data</option>
            {datasets.filter(x=>x.has_prices).map(d=><option key={d.id} value={d.id}>{d.label}</option>)}
          </select></label>
        <div className="rw-inline-actions">
          <button disabled={!selectedDataset||busy} onClick={()=>void reload()}>
            <RefreshCw size={14}/> Refresh source evidence</button>
          <button onClick={onOpenDhan}><Database size={14}/> Shared Dhan downloader</button>
        </div>
      </div>
      {error&&<p role="alert" className="rw-error">{error}</p>}
      {message&&<p role="status" className="rw-note">{message}</p>}
    </Panel>
    {tab==='evidence'&&<div className="rw-stack">
      <Panel title="Research-data evidence register">
        {audit?<><div className="rw-stats">
          <Cell title="Evidence categories with source indicators" value={audit.documented_categories+' / '+audit.evidence.length}/>
          <Cell title="Descriptive observed prices" value={audit.ready_for_descriptive_prices?'Available':'Missing'}/>
          <Cell title="Historical investability certified" value="NO"/>
          <Cell title="Prospective execution certified" value="NO"/>
        </div>
        <p className="rw-help">Price checksum: {audit.source_sha256||'No source file'} · source IDs refer to the selected dataset only.</p>
        <div className="rw-scroll"><table><thead><tr>
          <th>Evidence category</th><th>Status</th><th>What is required</th><th>Submitted sources</th>
          </tr></thead><tbody>{audit.evidence.map(x=><tr key={x.category}>
            <td>{x.label}</td><td><strong>{x.status.replaceAll('_',' ')}</strong></td>
            <td>{x.criterion}</td><td>{x.source_references.length?x.source_references.map((r,i)=>
              <div key={i}>{r.source_url&&<a href={r.source_url} rel="noreferrer" target="_blank">Source {i+1}</a>}
                {r.stale?' · Source data changed; re-review':''}</div>):'Not submitted'}</td>
          </tr>)}</tbody></table></div>
        <p className="rw-caution"><ShieldAlert size={15}/> {audit.warning}</p>
        <ExportJson name={'quantlab_evidence_'+audit.dataset_id+'.json'} data={audit}/>
        </>:<p className="rw-help">Select a dataset to inspect observed source integrity and missing research evidence.</p>}
      </Panel>
      <Panel title="Attach a dated, independently identifiable source">
        <p className="rw-help">This is an evidence link, not an approval switch. Submissions remain explicitly unverified and are invalidated when the underlying price checksum changes.</p>
        <div className="rw-form-grid">
          <label className="rw-field"><span>Research evidence category</span>
            <select value={category} onChange={e=>setCategory(e.target.value)}>
              {['prices','membership','actions','benchmark','delistings','fundamentals','costs','execution'].map(x=>
                <option key={x} value={x}>{x.replaceAll('_',' ')}</option>)}</select></label>
          <label className="rw-field"><span>Published or available as-of date</span>
            <input type="date" value={asOf} onChange={e=>setAsOf(e.target.value)}/></label>
          <label className="rw-field"><span>Public HTTPS evidence source URL (no query tokens)</span>
            <input type="url" value={sourceUrl} onChange={e=>setSourceUrl(e.target.value)}
              placeholder="https://..."/></label>
          <label className="rw-field"><span>Review note (no secrets)</span>
            <input value={note} onChange={e=>setNote(e.target.value)}/></label>
        </div>
        <button className="rw-primary" disabled={busy||!selectedDataset||!asOf||!sourceUrl}
          onClick={()=>void submit()}><Save size={15}/> Record unverified source reference</button>
      </Panel>
    </div>}
    {tab==='live'&&<Panel title="Read-only Dhan candle reconciliation">
      <p className="rw-help">Verify one sampled local Dhan equity against the current vendor historical endpoint. The token stays inside the local Python environment. No orders, no export of account details, no new price store, and no automatic retries.</p>
      {plan?.available?<><div className="rw-stats">
        <Cell title="Mapped instrument" value={plan.symbol||'Unknown'}/>
        <Cell title="Cached sessions sampled" value={plan.cached_sample_sessions||0}/>
        <Cell title="From" value={plan.from_date||'Unknown'}/>
        <Cell title="Through (exclusive)" value={plan.to_date_exclusive||'Unknown'}/>
      </div>
      <p className="rw-help">The comparison checks exact instrument ID, overlapping dates and price tolerance. A single matching sample does not prove dividends, point-in-time membership or historical completeness.</p>
      <button className="rw-primary" disabled={busy} onClick={()=>void probe()}>
        <Play size={15}/> Confirm one live Dhan sample comparison</button>
      </>:<p className="rw-caution">{plan?.reason||'Choose a daily Dhan dataset with stored instrument provenance.'}</p>}
      {previous&&previous.status!=='not_run'&&<div className="rw-insight">
        <strong>Last live vendor probe: {previous.status.replaceAll('_',' ')}</strong>
        <p>{previous.compared_sessions||0} compared sessions;
          {previous.mismatched_sessions||0} mismatches.
          {previous.stale?' Source changed since that probe; reverify.':''}</p>
        <small>{previous.checked_utc}</small>
        <p>{previous.warning}</p>
        <ExportJson name="quantlab_dhan_probe.json" data={previous}/>
      </div>}
    </Panel>}
    {tab==='learning'&&<div className="rw-stack">
      <Panel title="Chronological ML / RL research · no broker orders">
        <p className="rw-help">Ridge, Random Forest and Histogram Gradient Boosting use training-only model fits. A bounded tabular Q-learning policy learns a long/cash strategy. Training labels are embargoed before test decisions, signals are executed one session later, and trading costs are explicit. This is not PPO/SAC or a production trading bot.</p>
        <div className="rw-form-grid">
          <label className="rw-field"><span>Observed daily asset column</span><select value={asset}
            onChange={e=>setAsset(e.target.value)}>{columns.map(x=>
              <option value={x} key={x}>{x}</option>)}</select></label>
          <label className="rw-field"><span>Research method</span><select value={model}
            onChange={e=>setModel(e.target.value)}>
              {['ridge','random_forest','hist_gradient_boosting','tabular_q'].map(v=>
                <option key={v} value={v}>{v.replaceAll('_',' ')}</option>)}</select></label>
          <label className="rw-field"><span>Training fraction (0.60–0.85)</span>
            <input type="number" min="0.60" max="0.85" step=".05" value={fraction}
              onChange={e=>setFraction(e.target.value)}/></label>
          <label className="rw-field"><span>Cost per position change (bps)</span>
            <input type="number" min="0" max="250" value={cost}
              onChange={e=>setCost(e.target.value)}/></label>
          <label className="rw-field"><span>Random seed</span>
            <input type="number" value={seed} onChange={e=>setSeed(e.target.value)}/></label>
        </div>
        {ready&&<><div className="rw-stats">
          <Cell title="Usable lagged samples" value={ready.usable_lagged_samples}/>
          <Cell title="Minimum needed" value={ready.minimum_samples}/>
          <Cell title="Preferred (+20%)" value={ready.preferred_samples}/>
          <Cell title="Additional to preferred" value={ready.missing_preferred}/>
        </div>
          <p className={ready.ready?'rw-note':'rw-caution'}>{ready.ready?
            'Minimum training+holdout requirement satisfied; prefer the 20% extra sample buffer.':
            'Insufficient observed daily sessions; use the shared Dhan downloader before training.'}</p>
          <p className="rw-help">{ready.warning}</p>
        </>}
        <button className="rw-primary" disabled={busy||!ready?.ready} onClick={()=>void learning()}>
          {busy?<LoaderCircle size={15}/>:<Play size={15}/>} Confirm & run chronological research</button>
      </Panel>
      <Panel title="Saved learning studies & complete holdout returns">
        <label className="rw-field"><span>Previously saved learning study</span><select
          value={study?.id||''} onChange={e=>setSelectedStudy(e.target.value)}>
          {!studies.length&&<option value="">No saved studies yet</option>}
          {studies.map(x=><option key={x.id} value={x.id}>{x.title}</option>)}
        </select></label>
        {study&&payload?<><div className="rw-stats">
          <Cell title="Training observations" value={payload.train_observations}/>
          <Cell title="Holdout observations" value={payload.test_observations}/>
          <Cell title="Strategy net price return" value={(100*payload.holdout_total_return_net).toFixed(2)+'%'}/>
          <Cell title="Passive price return" value={(100*payload.passive_total_return_price_only).toFixed(2)+'%'}/>
        </div>
          <p className="rw-help">Last training label {payload.last_training_label_date} ·
            First untouched test decision {payload.first_test_decision_date}</p>
          <ResearchPlot plot={payload.plot}/>
          <a className="rw-download-link" href={'/api/workspace/studies/'+study.id+'/returns.csv'} download>
            <Download size={15}/> Download every chronological holdout return</a>
          <p className="rw-caution">{payload.warning}</p>
        </>:<p className="rw-help">Completed studies appear here after a job is saved. Go to Jobs to review progress or errors.</p>}
      </Panel>
    </div>}
  </div>
}

import {useCallback,useEffect,useState} from 'react'
import {ArrowRight,CheckCircle2,Database,Download,FileCheck2,LockKeyhole,
  Play,RefreshCw,ShieldAlert,ShieldCheck,X} from 'lucide-react'
import './historical-validation.css'

type Config={name:string;factor_weights:Record<string,number>;top_n:number;
  weighting:string;max_weight:number;rebalance_every:number;cost_bps:number;
  execution_lag:number;momentum_formation:number;momentum_skip:number;
  volatility_lookback:number;validation_start:string;final_test_start:string;
  sector_cap:number|null}
type Check={name:string;status:'pass'|'review'|'blocked'|'not_applicable';
  detail:string;next_action:string}
type Audit={dataset_id:string;dataset_kind:string;status:string;
  structural_run_ready:boolean;independent_source_certified:boolean;
  publication_certified:boolean;checks:Check[];source_hashes:Record<string,string>;
  missing_source_actions:{name:string;status:string;action:string}[];
  timing:{months_before_validation:number|null;months_in_final_test:number|null;
    months_in_validation?:number|null;preferred_train_months:number;minimum_test_months:number};
  warning:string}
type SourceAction={category:string;status:string;target:string;flow:string;
  official_source_url:string;why:string;next_action:string}
type SourceWorklist={readiness:Audit;source_kind:string;warning:string;
  summary:{price_months:number|null;price_securities:number|null;
    missing_entire_months:number|null;missing_eligible_prices:number|null;
    missing_eligible_forward_returns:number|null;unresolved_historical_symbols:number|null;
    benchmark_alignment:string;prevalidation_months:number|null;
    preferred_prevalidation_months_with_20pct_buffer:number;
    prevalidation_shortfall_to_buffer:number|null;final_test_forward_returns:number|null;
    required_final_test_forward_returns:number;independent_original_source_certified:boolean};
  actions:SourceAction[];missing_security_month_count:number;
  missing_security_month_preview:{date:string;ticker:string;problem:string}[];
  missing_calendar_months:string[];unresolved_symbols:string[];
  coverage_warnings:string[];exact_gap_calculation_available:boolean}
type Frozen={id:string;sha256:string;dataset_id:string;state:string;
  validation_start:string;final_test_start:string;registered_utc:string;
  independent_source_certified:boolean;publication_certified:boolean;warning:string}
type Props={datasetId:string;config:Config;hasDailyPrices:boolean;onOpenData:()=>void;
  onOpenDhan:()=>void;onDataCreated:(datasetId:string)=>void;onJobQueued:(jobId:string)=>void}
async function call<T>(path:string,body?:unknown):Promise<T>{
  let response:Response
  try{response=await fetch('/api'+path,{credentials:'same-origin',
    ...(body?{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(body)}:{})})}
  catch{throw new Error('Local Python research API is offline. Start QuantLab using bash run.sh.')}
  if(!response.ok){let detail='HTTP '+response.status
    try{const json=await response.json() as {detail?:string}
      if(typeof json.detail==='string')detail=json.detail}catch{}
    throw new Error(detail)}
  return await response.json() as T
}
function exportJson(name:string,data:unknown){
  const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'})
  const address=URL.createObjectURL(blob)
  const a=document.createElement('a');a.href=address;a.download=name
  document.body.appendChild(a);a.click();a.remove()
  window.setTimeout(()=>URL.revokeObjectURL(address),1000)
}
export default function HistoricalValidationPanel({datasetId,config,hasDailyPrices,onOpenData,
  onOpenDhan,onDataCreated,onJobQueued}:Props){
  const [report,setReport]=useState<Audit|null>(null)
  const [worklist,setWorklist]=useState<SourceWorklist|null>(null)
  const [frozen,setFrozen]=useState<Frozen|null>(null)
  const [busy,setBusy]=useState<'audit'|'freeze'|'execute'|'actions'|null>(null)
  const [actionFile,setActionFile]=useState<File|null>(null)
  const [priceBasis,setPriceBasis]=useState('split_bonus_adjusted')
  const [acknowledged,setAcknowledged]=useState(false)
  const [error,setError]=useState('')
  const [info,setInfo]=useState('')
  const clear=()=>{setReport(null);setWorklist(null);setFrozen(null);setError('');setInfo('')}
  useEffect(clear,[datasetId,config])
  const audit=useCallback(async()=>{
    if(!datasetId)return
    setBusy('audit');setError('')
    try{
      const query=new URLSearchParams()
      if(config.validation_start)query.set('validation_start',config.validation_start)
      if(config.final_test_start)query.set('final_test_start',config.final_test_start)
      query.set('factors',Object.entries(config.factor_weights)
        .filter(([_,weight])=>weight>0).map(([name])=>name).join(','))
      const value=await call<SourceWorklist>('/workspace/historical-sources/'+
        encodeURIComponent(datasetId)+'?'+query)
      setReport(value.readiness);setWorklist(value)
    }catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setBusy(null)}
  },[datasetId,config])
  useEffect(()=>{
    if(!datasetId)return
    const timer=window.setTimeout(()=>{void audit()},350)
    return()=>window.clearTimeout(timer)
  },[audit,datasetId])
  const importActions=async()=>{
    if(!actionFile||!datasetId||!hasDailyPrices||!acknowledged)return
    setBusy('actions');setError('')
    try{
      const form=new FormData()
      form.append('file',actionFile)
      form.append('price_basis',priceBasis)
      form.append('acknowledge_unverified','true')
      const response=await fetch('/api/datasets/'+encodeURIComponent(datasetId)+'/add-actions',{
        method:'POST',credentials:'same-origin',body:form})
      if(!response.ok){let error='HTTP '+response.status
        try{const data=await response.json() as {detail?:string}
          if(data.detail)error=data.detail}catch{}
        throw new Error(error)}
      const output=await response.json() as {dataset_id:string;warning:string}
      setInfo('New total-return research dataset: '+output.dataset_id+'. '+output.warning)
      setActionFile(null);setAcknowledged(false)
      onDataCreated(output.dataset_id)
    }catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setBusy(null)}
  }
  const freeze=async()=>{
    setBusy('freeze');setError('')
    try{
      const record=await call<Frozen>('/workspace/frozen/create',{
        ...config,dataset_id:datasetId,
        validation_start:config.validation_start||null,
        final_test_start:config.final_test_start||null})
      setFrozen(record);setInfo('Frozen protocol saved. This is a one-use software lock, not independent source verification.')
    }catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setBusy(null)}
  }
  const execute=async()=>{
    if(!frozen||!window.confirm('Consume this single-use frozen protocol? The final-test run cannot be repeated under the same protocol.'))return
    setBusy('execute');setError('')
    try{
      const started=await call<{job_id:string}>('/workspace/frozen/'+
        encodeURIComponent(frozen.id)+'/execute',{confirm:true})
      setFrozen({...frozen,state:'consumed'})
      setInfo('Frozen Python experiment queued. Review the resulting receipt and evidence audit before reporting results.')
      onJobQueued(started.job_id)
    }catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setBusy(null)}
  }
  const sourceParams=new URLSearchParams()
  if(config.validation_start)sourceParams.set('validation_start',config.validation_start)
  if(config.final_test_start)sourceParams.set('final_test_start',config.final_test_start)
  sourceParams.set('factors',Object.entries(config.factor_weights)
    .filter(([_,weight])=>weight>0).map(([name])=>name).join(','))
  const zipUrl='/api/workspace/historical-sources/'+
    encodeURIComponent(datasetId)+'/worklist.zip?'+sourceParams.toString()
  const statusText=(n:number|null|undefined)=>n===null||n===undefined?'Not audited':n.toLocaleString()
  return <section className="hv-root" aria-label="Historical source and frozen final-test validation">
    <div className="hv-heading"><div><span className="hv-kicker"><ShieldCheck size={14}/> HISTORICAL EVIDENCE WORKFLOW</span>
      <h2>Original sources → independent review → frozen test</h2>
      <p>Every step is source-aware. A complete spreadsheet, source URL, or checksum is not market-data certification.</p></div>
      <button disabled={!datasetId||busy!==null} onClick={()=>void audit()}>
        <RefreshCw size={15}/> Recheck dataset</button></div>
    <div className="hv-steps">
      <article><b>01</b><div><strong>Collect originals</strong><p>Historical prices, PIT constituents, ex-date actions, official TRI and publication vintages.</p>
        <div className="hv-buttons"><button onClick={onOpenDhan}><Download size={13}/> Dhan historical downloader</button>
          <button onClick={onOpenData}><Database size={13}/> Dataset & TRI import</button></div></div></article>
      <article><b>02</b><div><strong>Audit completeness & consistency</strong><p>Matched calendars, source checksums, announced index entries/exits, actual dividends, delistings and historical windows.</p></div></article>
      <article><b>03</b><div><strong>Freeze one final test</strong><p>Lock the exact dataset and parameters BEFORE evaluation; consume the protocol once.</p></div></article>
    </div>
    <div className="hv-action-form"><div><span className="hv-kicker">01B / PRICE ADJUSTMENT</span>
      <h3>Create event-adjusted total-return dataset</h3>
      <p>Upload real source-cited ex-date actions from issuer/exchange records. QuantLab builds a separate
        dividend-reinvested wealth series from the dataset's original daily closes.
        No stock event or delisting recovery is assumed when missing.</p></div>
      <div className="hv-action-grid">
        <label>Reviewed action ledger CSV<input type="file" accept=".csv,text/csv"
          disabled={!hasDailyPrices||!datasetId||busy!==null} onChange={e=>setActionFile(e.target.files?.[0]||null)}/></label>
        <label>Original daily price basis<select value={priceBasis}
          onChange={e=>setPriceBasis(e.target.value)} disabled={busy!==null}>
          <option value="split_bonus_adjusted">Split/bonus adjusted (Dhan daily closes)</option>
          <option value="raw_unadjusted">Raw, unadjusted prices (verified source only)</option>
        </select></label>
      </div>
      <label className="hv-ack"><input type="checkbox" checked={acknowledged}
        onChange={e=>setAcknowledged(e.target.checked)}/>
        I understand that the imported action ledger and coverage are NOT independently certified.</label>
      <button disabled={!datasetId||!hasDailyPrices||!actionFile||!acknowledged||busy!==null}
        onClick={()=>void importActions()}><FileCheck2 size={15}/>
        {busy==='actions'?'Preparing source-aware wealth indices…':'Build new version — keep original unchanged'}</button>
      {!hasDailyPrices&&<p className="hv-muted">This dataset lacks daily_prices.csv. Prepare daily Dhan
        history first; monthly closes cannot determine ex-date dividends or delisting payoffs.</p>}
    </div>
    {!datasetId&&<p className="hv-error">Select a dataset in Experiment Configuration to inspect its original evidence.</p>}
    {busy==='audit'&&<p className="hv-loading" role="status">Inspecting archived research inputs and provenance…</p>}
    {error&&<p className="hv-error" role="alert"><ShieldAlert size={15}/>{error}
      <button onClick={()=>setError('')} aria-label="Dismiss historical validation error"><X size={14}/></button></p>}
    {info&&<p className="hv-notice" role="status">{info}</p>}
    {report&&<><div className="hv-summary">
      <div><small>SOFTWARE READINESS</small><strong className={report.structural_run_ready?'ok':'bad'}>
        {report.structural_run_ready?'Chronological study runnable':'Historical study incomplete'}</strong></div>
      <div><small>ORIGINAL-SOURCE CERTIFICATION</small><strong className="bad">Not independently audited</strong></div>
      <div><small>PREVALIDATION MONTHS</small><strong>{report.timing.months_before_validation??'—'} / {report.timing.preferred_train_months} preferred</strong></div>
      <div><small>FINAL TEST MONTHS</small><strong>{report.timing.months_in_final_test??'—'} / {report.timing.minimum_test_months} required</strong></div>
    </div>
    {worklist&&<section className="hv-source-worklist" aria-label="Original-source missing-data worklist">
      <div className="hv-audit-title">
        <div><span className="hv-kicker">SOURCE ACQUISITION · NOT AUTO-CERTIFIED</span>
          <h3>Exact missing history and evidence to collect</h3></div>
        <a className="hv-download-link" href={zipUrl} download>
          <Download size={15}/> Export missing-source ZIP</a>
      </div>
      <p>Only authentic issuer or authorized provider records can close these gaps.
        A source URL or checksum cannot prove a historical return or authorize redistribution.</p>
      <div className="hv-evidence-stats">
        <div><small>Stock price months</small><strong>{statusText(worklist.summary.price_months)}</strong></div>
        <div><small>Entire calendar months missing</small><strong>{statusText(worklist.summary.missing_entire_months)}</strong></div>
        <div><small>Eligible close gaps</small><strong>{statusText(worklist.summary.missing_eligible_prices)}</strong></div>
        <div><small>Following-month return gaps</small><strong>{statusText(worklist.summary.missing_eligible_forward_returns)}</strong></div>
        <div><small>Historical symbol identities unresolved</small><strong>{statusText(worklist.summary.unresolved_historical_symbols)}</strong></div>
        <div><small>Training history · preferred +20%</small><strong>
          {statusText(worklist.summary.prevalidation_months)} /
          {' '}{worklist.summary.preferred_prevalidation_months_with_20pct_buffer} months
        </strong></div>
        <div><small>Extra training months needed</small><strong>{statusText(worklist.summary.prevalidation_shortfall_to_buffer)}</strong></div>
        <div><small>Untouched final-test returns</small><strong>
          {statusText(worklist.summary.final_test_forward_returns)} /
          {' '}{worklist.summary.required_final_test_forward_returns} minimum
        </strong></div>
      </div>
      <div className="hv-buttons">
        <button onClick={onOpenDhan}><Download size={13}/> Get mapped Dhan history</button>
        <button onClick={onOpenData}><Database size={13}/> Import original dataset / TRI</button>
        <a className="hv-source-link" href="https://www.niftyindices.com/reports/historical-data"
          target="_blank" rel="noopener noreferrer">Official NIFTY TRI archive <ArrowRight size={13}/></a>
      </div>
      {!worklist.exact_gap_calculation_available&&<p className="hv-source-shortfall" role="alert">
        Exact security-month analysis could not run on this incomplete or invalid source.
        {' '}{worklist.coverage_warnings.join(' ')}
      </p>}
      {!!worklist.missing_calendar_months.length&&<p className="hv-source-shortfall">
        Unobserved months: {worklist.missing_calendar_months.slice(0,12).join(', ')}
        {worklist.missing_calendar_months.length>12?' … (complete list in ZIP)':''}.
      </p>}
      {!!worklist.unresolved_symbols.length&&<p className="hv-source-shortfall">
        Source-reported unresolved historical symbols:
        {' '}{worklist.unresolved_symbols.slice(0,12).join(', ')}
        {worklist.unresolved_symbols.length>12?' … (complete list in ZIP)':''}.
      </p>}
      {!!worklist.missing_security_month_count&&<details className="hv-missing-table">
        <summary>Inspect {worklist.missing_security_month_count.toLocaleString()}
          {' '}exact missing security-month observations</summary>
        <div className="hv-scroll"><table><thead><tr><th>Month</th><th>Security</th><th>Evidence needed</th></tr></thead>
          <tbody>{worklist.missing_security_month_preview.map((row,i)=>
            <tr key={row.date+'-'+row.ticker+'-'+i}><td>{row.date}</td><td>{row.ticker}</td>
              <td>{row.problem.replaceAll('_',' ')}</td></tr>)}</tbody></table></div>
        {worklist.missing_security_month_count>worklist.missing_security_month_preview.length&&
          <p>Showing the first {worklist.missing_security_month_preview.length};
            export the ZIP for the full source worklist.</p>}
      </details>}
      <h4>What original evidence is missing or needs review?</h4>
      <div className="hv-source-actions">{worklist.actions
        .filter(row=>row.status==='blocked'||row.status==='review').map(row=>
        <article key={row.category} className={'hv-source-action '+row.status}>
          <div><span>{row.status.toUpperCase()}</span><strong>{row.category}</strong>
            <small>Required: {row.target}</small>
            <p>{row.next_action}</p></div>
          <div className="hv-buttons">
            {row.flow==='dhan'&&<button onClick={onOpenDhan}>Open Dhan manager</button>}
            {row.flow==='import'&&<button onClick={onOpenData}>Open imports</button>}
            <a className="hv-source-link" href={row.official_source_url}
              rel="noopener noreferrer" target="_blank">Official source <ArrowRight size={12}/></a>
          </div>
        </article>)}</div>
      <p className="hv-disclosure"><ShieldAlert size={16}/>{worklist.warning}</p>
    </section>}
    <div className="hv-audit-title"><h3>Source and validation gates</h3>
      <button onClick={()=>exportJson('quantlab_historical_readiness_'+datasetId+'.json',report)}>
        <Download size={14}/> Export detailed audit</button></div>
    <div className="hv-checks">{report.checks.map((item,i)=><article key={item.name+'-'+i}
      className={'hv-check '+item.status}>
      <span className="hv-status">{item.status==='pass'?<CheckCircle2 size={16}/>:<ShieldAlert size={16}/>}
        {item.status.toUpperCase().replaceAll('_',' ')}</span>
      <div><strong>{item.name}</strong><p>{item.detail}</p>
        {item.status!=='pass'&&item.next_action&&<small>Next: {item.next_action}</small>}</div></article>)}</div>
    <p className="hv-disclosure"><ShieldAlert size={16}/>{report.warning}</p></>}
    <div className="hv-freeze">
      <div><span className="hv-kicker"><LockKeyhole size={14}/> ONE-TIME CHRONOLOGICAL FINAL TEST</span>
        <h3>Freeze your source hashes, parameters and test dates</h3>
        <p>From configuration above: validation <strong>{config.validation_start||'not selected'}</strong>,
          final test <strong>{config.final_test_start||'not selected'}</strong>.
          You can still run ordinary exploratory backtests without freezing, but those cannot claim a locked holdout.</p>
        {frozen&&<p className="hv-notice"><FileCheck2 size={15}/> Protocol <code>{frozen.id}</code> · {frozen.state} ·
          saved {frozen.registered_utc}. It is <strong>not externally notarized</strong>.</p>}</div>
      <div className="hv-buttons">
        <button disabled={busy!==null||!report?.structural_run_ready||!!frozen}
          onClick={()=>void freeze()}><LockKeyhole size={15}/> {busy==='freeze'?'Freezing…':'Create frozen protocol'}</button>
        <button className="hv-primary" disabled={busy!==null||frozen?.state!=='available'}
          onClick={()=>void execute()}><Play size={15}/> {busy==='execute'?'Submitting…':'Run once on frozen protocol'}
          <ArrowRight size={14}/></button>
      </div>
      <p className="hv-muted">A local freeze prevents accidental parameter edits and repeated use, but cannot prove a researcher never viewed the data. Independent source/holdout reviews remain required before empirical publication claims.</p>
    </div>
  </section>
}

import {useCallback, useEffect, useMemo, useRef, useState} from 'react'
import {Activity, ArrowRight, BookOpen, CheckCircle2, CircleAlert, Database,
  Copy, Download, FlaskConical, Heart, Layers, LoaderCircle, Play, Save, ShieldCheck, SlidersHorizontal, Trash2} from 'lucide-react'
import ResearchPlot, {type ResearchPlotData} from './ResearchPlots'
import './model-lab.css'

type Parameter={
  key:string;type:'number'|'integer'|'select';default:number|string;
  min?:number;max?:number;step?:number;options?:string[];description?:string
}
type ModelSpec={
  id:string;group:string;title:string;mode:'synthetic'|'theoretical'|'historical';
  min_observations:number;description:string;formula:string;status:string;
  parameters:Parameter[];chart:string
}
type Datum={id:string;label:string;has_prices:boolean;ready:boolean;source_interval_minutes?:number|null}
type LabResult={
  run_id?:string;model_id:string;title:string;group:string;mode:string;formula:string;
  generated_utc:string;params:Record<string,number|string>;source?:{
    dataset_id:string;dataset_label:string;frequency:string;observations:number;
    assets:string[];from_date:string;to_date:string;source_file:string;
    selection_rule:string;benchmark_kind:string
  }|null;metrics:{label:string;value:string|number|null;unit:string}[];
  plots:ResearchPlotData[];table:Record<string,unknown>[];
  limitations:string[];notes:string[]
}
type SavedRun={id:string;model_id:string;group:string;title:string;mode:string;
  generated_utc:string;dataset_id?:string|null;observations?:number|null;figures:number}
type Readiness={dataset_id:string;frequency?:string;observed_dates?:number;
  eligible_assets_60?:number;eligible_assets_180?:number;has_prices:boolean;
  sample_start?:string;sample_end?:string;benchmark_kind?:string;warning?:string}
type DataPlan={model_id:string;mode:string;status:string;runnable:boolean;min_returns:number;target_returns:number;
  buffer_returns:number;common_returns?:number;assets_requested:number;assets_found?:number;
  missing_minimum?:number;missing_to_target?:number;can_download?:boolean;download_explanation?:string;
  suggested_start?:string;suggested_end_exclusive?:string;message:string;
  estimated_calendar_weekdays?:number;estimated_max_instrument_day_requests?:number;
  request_scope_note?:string;cached_instrument_calendar_days?:number;
  missing_instrument_calendar_days?:number;missing_uncovered_windows?:number;
  estimated_vendor_daily_requests?:number}
type ExtensionJob={id:string;status:string;kind:string;error?:string;result?:{dataset_id?:string;status:string;message:string;after?:DataPlan}}
type ConfigRecord={id:string;title:string;payload:{model_id?:string;dataset_id?:string;params?:Record<string,number|string>};
  favorite:boolean;tags:string[]}
type Props={
  section:'mathematics'|'models';
  datasets:Datum[];
  selectedDataset:string;
  onSelectDataset:(id:string)=>void;
  onOpenGuide:()=>void;
  onDataChanged?:()=>void;
  onOpenWorkspace?:()=>void
}
type ResultView='configure'|'figures'|'numbers'|'method'
const SECTIONS=['Stochastic Processes','Volatility & Econometrics','Derivatives & Options',
  'Portfolio Optimization','Tail Risk & Inference','3D Visual Laboratory']
const MODE_LABELS:Record<ModelSpec['mode'],string>={
  synthetic:'SEEDED SIMULATION',theoretical:'THEORETICAL',historical:'OBSERVED MARKET DATA'
}
const valueText=(value:unknown)=>{
  if(value===null||value===undefined)return 'Unavailable'
  if(typeof value==='number')return Number.isFinite(value)
    ?value.toLocaleString('en-US',{maximumFractionDigits:6}):'Unavailable'
  return String(value)
}
const errorText=async(response:Response)=>{
  try{
    const json:unknown=await response.json()
    if(json&&typeof json==='object'&&'detail' in json){
      const detail=(json as {detail:unknown}).detail
      return typeof detail==='string'?detail:JSON.stringify(detail)
    }
  }catch{/* API returned a non-JSON error */}
  return 'Research backend returned HTTP '+response.status
}
async function getJSON<T>(path:string):Promise<T>{
  const response=await fetch('/api'+path,{credentials:'same-origin'})
  if(!response.ok)throw new Error(await errorText(response))
  return response.json() as Promise<T>
}
function exportResult(modelId:string,result:LabResult,format:'json'|'csv'){
  let content:string,mime:string
  if(format==='json'){
    content=JSON.stringify(result,null,2);mime='application/json'
  }else{
    const escape=(value:unknown)=>'"'+String(value??'').replaceAll('"','""')+'"'
    const keys=[...new Set(result.table.flatMap(row=>Object.keys(row)))]
    const rows:Record<string,unknown>[]=result.table.length?result.table:result.metrics.map(m=>({
      metric:m.label,value:m.value,unit:m.unit
    }))
    const headers=keys.length?keys:['metric','value','unit']
    content=[headers.map(escape).join(','),...rows.map(row=>headers.map(k=>escape(row[k])).join(','))].join('\n')
    mime='text/csv'
  }
  const url=URL.createObjectURL(new Blob([content],{type:mime}))
  const link=document.createElement('a')
  link.href=url;link.download='quantlab_'+modelId+'_'+new Date().toISOString().slice(0,10)+'.'+format
  document.body.appendChild(link);link.click();link.remove()
  URL.revokeObjectURL(url)
}
export default function ModelLaboratory({section,datasets,selectedDataset,onSelectDataset,onOpenGuide,onDataChanged,onOpenWorkspace}:Props){
  const [catalog,setCatalog]=useState<ModelSpec[]>([])
  const [catalogError,setCatalogError]=useState<string|null>(null)
  const [group,setGroup]=useState(section==='mathematics'?SECTIONS[0]:SECTIONS[3])
  const [modelId,setModelId]=useState(section==='mathematics'?'gbm':'min_variance')
  const [params,setParams]=useState<Record<string,number|string>>({})
  const [view,setView]=useState<ResultView>('configure')
  const [readiness,setReadiness]=useState<Readiness|null>(null)
  const [readinessError,setReadinessError]=useState<string|null>(null)
  const [result,setResult]=useState<LabResult|null>(null)
  const [error,setError]=useState<string|null>(null)
  const [working,setWorking]=useState(false)
  const [savedRuns,setSavedRuns]=useState<SavedRun[]>([])
  const [configs,setConfigs]=useState<ConfigRecord[]>([])
  const [notebooks,setNotebooks]=useState<{id:string;title:string}[]>([])
  const [notebookTarget,setNotebookTarget]=useState('')
  const [configMessage,setConfigMessage]=useState<string|null>(null)
  const [configBusy,setConfigBusy]=useState(false)
  const pendingPreset=useRef<{model_id:string;params:Record<string,number|string>}|null>(null)
  const refreshConfigs=useCallback(()=>getJSON<{records:ConfigRecord[]}>(
    '/workspace/records?kind=configuration')
      .then(r=>setConfigs(r.records)).catch(()=>setConfigs([])),[])
  useEffect(()=>{void refreshConfigs()},[refreshConfigs])
  useEffect(()=>{
    void getJSON<{records:{id:string;title:string}[]}>('/workspace/records?kind=notebook')
      .then(r=>setNotebooks(r.records)).catch(()=>setNotebooks([]))
  },[])
  const addRunToNotebook=async()=>{
    if(!result?.run_id||!notebookTarget)return
    setConfigBusy(true)
    try{
      const r=await fetch('/api/workspace/notebooks/'+encodeURIComponent(notebookTarget)+'/attach',{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({kind:'run',source_id:result.run_id})})
      if(!r.ok)throw new Error(await errorText(r))
      setConfigMessage('Model run attached to the selected report notebook')
    }catch(e){setConfigMessage(e instanceof Error?e.message:String(e))}
    finally{setConfigBusy(false)}
  }

  const [dataPlan,setDataPlan]=useState<DataPlan|null>(null)
  const [planError,setPlanError]=useState<string|null>(null)
  const [planLoading,setPlanLoading]=useState(false)
  const [extensionJob,setExtensionJob]=useState<ExtensionJob|null>(null)
  const [extensionMessage,setExtensionMessage]=useState<string|null>(null)
  const [extensionError,setExtensionError]=useState<string|null>(null)
  const refreshSaved=useCallback(()=>getJSON<{runs:SavedRun[]}>('/lab/runs')
    .then(data=>setSavedRuns(data.runs)).catch(()=>setSavedRuns([])),[])
  useEffect(()=>{void refreshSaved()},[refreshSaved])
  useEffect(()=>{
    let active=true
    getJSON<{models:ModelSpec[]}>('/lab/catalog').then(data=>{
      if(!active)return
      setCatalog(data.models)
      let target:string|null=null
      try{target=window.localStorage.getItem('ql-target-model')}catch{}
      const requested=data.models.find(m=>m.id===target)
      if(requested){
        setGroup(requested.group)
        setModelId(requested.id)
        setResult(null);setView('configure')
        try{window.localStorage.removeItem('ql-target-model')}catch{}
      }
    }).catch(e=>{if(active)setCatalogError(e instanceof Error?e.message:String(e))})
    return()=>{active=false}
  },[])
  useEffect(()=>{
    const next=section==='mathematics'?SECTIONS[0]:SECTIONS[3]
    setGroup(next)
    setModelId(section==='mathematics'?'gbm':'min_variance')
    setResult(null);setError(null);setView('configure')
  },[section])
  const groupModels=catalog.filter(spec=>spec.group===group)
  const selected=catalog.find(spec=>spec.id===modelId)
  const defaultParams=useCallback((spec:ModelSpec)=>Object.fromEntries(
    spec.parameters.map(p=>[p.key,p.default])
  ),[])
  useEffect(()=>{
    if(!selected)return
    const preset=pendingPreset.current
    pendingPreset.current=null
    if(preset&&preset.model_id===selected.id){setParams({...preset.params});return}
    let draft:Record<string,number|string>|null=null
    try{const raw=window.localStorage.getItem('ql-model-draft-'+selected.id)
      if(raw)draft=JSON.parse(raw) as Record<string,number|string>}catch{/* no prior draft */}
    const validKeys=new Set(selected.parameters.map(x=>x.key))
    if(draft&&Object.keys(draft).every(key=>validKeys.has(key)))
      setParams({...defaultParams(selected),...draft})
    else setParams(result?.model_id===selected.id?{...result.params}:defaultParams(selected))
  },[selected?.id,defaultParams])
  useEffect(()=>{
    if(!selected||!Object.keys(params).length)return
    try{window.localStorage.setItem('ql-model-draft-'+selected.id,JSON.stringify(params))}
    catch{/* browser may restrict persistent storage */}
  },[selected?.id,params])
  const applyConfig=(entry:ConfigRecord)=>{
    const modelId=entry.payload.model_id
    const model=catalog.find(m=>m.id===modelId)
    if(!model||!entry.payload.params){setConfigMessage('Saved model is no longer registered');return}
    const preset={model_id:model.id,params:entry.payload.params}
    pendingPreset.current=preset
    if(entry.payload.dataset_id&&datasets.some(d=>d.id===entry.payload.dataset_id))
      onSelectDataset(entry.payload.dataset_id)
    setGroup(model.group)
    setResult(null);setError(null);setView('configure')
    if(model.id===selected?.id){setParams({...preset.params});pendingPreset.current=null}
    else setModelId(model.id)
    setConfigMessage('Loaded '+entry.title)
  }
  const storeConfig=async(copy?:ConfigRecord)=>{
    if(!selected||configBusy)return
    const title=copy?copy.title+' (copy)':window.prompt('Name your reusable model configuration',selected.title+' — baseline')
    if(!title?.trim())return
    setConfigBusy(true);setConfigMessage(null)
    try{
      const body={kind:'configuration',title:title.trim(),
        payload:copy?copy.payload:{model_id:selected.id,dataset_id:selectedDataset,params},
        tags:['model-configuration']}
      const response=await fetch('/api/workspace/records',{method:'POST',
        headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
      if(!response.ok)throw new Error(await errorText(response))
      await refreshConfigs();setConfigMessage('Configuration saved to Research Workspace')
    }catch(e){setConfigMessage(e instanceof Error?e.message:String(e))}
    finally{setConfigBusy(false)}
  }
  const configAction=async(entry:ConfigRecord,action:'trash'|'favorite'|'unfavorite')=>{
    setConfigBusy(true)
    try{
      const response=await fetch('/api/workspace/records/'+entry.id+'/action',{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({action})})
      if(!response.ok)throw new Error(await errorText(response))
      await refreshConfigs();setConfigMessage('Saved configuration updated')
    }catch(e){setConfigMessage(e instanceof Error?e.message:String(e))}
    finally{setConfigBusy(false)}
  }

  useEffect(()=>{
    setReadiness(null);setReadinessError(null)
    if(!selectedDataset)return
    let active=true
    getJSON<Readiness>('/lab/readiness?dataset_id='+encodeURIComponent(selectedDataset))
      .then(r=>{if(active)setReadiness(r)})
      .catch(e=>{if(active)setReadinessError(e instanceof Error?e.message:String(e))})
    return()=>{active=false}
  },[selectedDataset])
  const changeGroup=(next:string)=>{
    setGroup(next)
    const first=catalog.find(spec=>spec.group===next)
    setModelId(first?.id||'')
    setResult(null);setError(null);setView('configure')
  }
  const changeModel=(id:string)=>{
    setModelId(id);setResult(null);setError(null);setView('configure')
  }
  const observedNeeded=selected?.mode==='historical'
  const syntheticHistory=observedNeeded&&selectedDataset==='synthetic'
  const min=selected?.min_observations||0
  const requestedAssets=Number(params.assets??8)
  const requestedWindow=Number(params.train_window??60)
  useEffect(()=>{
    setDataPlan(null);setPlanError(null)
    if(!selected||selected.mode!=='historical'||!selectedDataset)return
    let active=true
    setPlanLoading(true)
    const query=new URLSearchParams({model_id:selected.id,dataset_id:selectedDataset,
      assets:String(requestedAssets),train_window:String(requestedWindow)})
    getJSON<DataPlan>('/lab/data-requirements?'+query.toString())
      .then(plan=>{if(active)setDataPlan(plan)})
      .catch(e=>{if(active)setPlanError(e instanceof Error?e.message:String(e))})
      .finally(()=>{if(active)setPlanLoading(false)})
    return()=>{active=false}
  },[selected?.id,selected?.mode,selectedDataset,requestedAssets,requestedWindow,extensionJob?.status])
  useEffect(()=>{
    if(!extensionJob||!['queued','running'].includes(extensionJob.status))return
    let active=true
    const timer=window.setTimeout(()=>{
      void getJSON<ExtensionJob>('/jobs/'+encodeURIComponent(extensionJob.id))
        .then(next=>{
          if(!active)return
          setExtensionJob(next)
          if(next.status==='complete'){
            const response=next.result
            setExtensionMessage(response?.message??'Shared history preparation completed.')
            if(response?.dataset_id){
              onDataChanged?.()
              onSelectDataset(response.dataset_id)
            }
          }
          if(next.status==='error')setExtensionError(next.error||'Historical download failed.')
        })
        .catch(e=>{if(active)setExtensionError(e instanceof Error?e.message:String(e))})
    },1250)
    return()=>{active=false;window.clearTimeout(timer)}
  },[extensionJob,onSelectDataset,onDataChanged])
  const extendHistory=async()=>{
    if(!selected||!selectedDataset||!dataPlan?.can_download||
      (extensionJob&&['queued','running'].includes(extensionJob.status)))return
    setExtensionError(null);setExtensionMessage(null)
    const request={model_id:selected.id,dataset_id:selectedDataset,params,confirm_download:true}
    try{
      const reply=await fetch('/api/lab/data-requirements/extend',{
        method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},
        body:JSON.stringify(request)})
      if(!reply.ok)throw new Error(await errorText(reply))
      const job=await reply.json() as {job_id:string;status:string}
      setExtensionJob({id:job.job_id,kind:'lab_shared_data_extension',status:job.status})
    }catch(e){setExtensionError(e instanceof Error?e.message:String(e))}
  }
  const insufficient=!!observedNeeded&&(
    !selectedDataset||planLoading||!!planError||
    (dataPlan? !dataPlan.runnable :
      readiness?.has_prices===false||(readiness?.observed_dates!==undefined&&readiness.observed_dates<=min))
  )
  const run=async()=>{
    if(!selected||working)return
    setError(null);setResult(null);setWorking(true)
    try{
      const response=await fetch('/api/lab/run',{
        method:'POST',credentials:'same-origin',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({model_id:selected.id,
          dataset_id:selected.mode==='historical'?selectedDataset:null,params}),
      })
      if(!response.ok)throw new Error(await errorText(response))
      const data=await response.json() as LabResult
      setResult(data);setView('figures')
      void refreshSaved()
    }catch(e){setError(e instanceof Error?e.message:String(e));setView('configure')}
    finally{setWorking(false)}
  }
  const reopen=async(run:SavedRun)=>{
    setError(null);setWorking(true)
    try{
      const data=await getJSON<LabResult>('/lab/runs/'+encodeURIComponent(run.id))
      setGroup(run.group);setModelId(run.model_id)
      setParams({...data.params})
      if(data.source?.dataset_id&&datasets.some(d=>d.id===data.source?.dataset_id)){
        onSelectDataset(data.source.dataset_id)
      }
      setResult(data);setView('figures')
    }catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setWorking(false)}
  }
  const dataHint=useMemo(()=>{
    if(!observedNeeded)return 'This experiment does not fit to a stock dataset.'
    if(!selectedDataset)return 'Select the saved NIFTY/BANK NIFTY research dataset first.'
    if(!readiness)return 'Inspecting local sample availability…'
    return (readiness.frequency||'unknown')+' observations · '+readiness.observed_dates+
      ' recorded dates · at least '+min+' common returns required.'
  },[observedNeeded,selectedDataset,readiness,min])
  return <div className="ql-workbench">
    <header className="ql-intro">
      <div><span className="ql-kicker">QUANTLAB / MODEL LABORATORY</span>
        <h2>Research the model. Inspect the evidence.</h2>
        <p>Choose a mathematical family, run its Python implementation, then explore verified outputs in 2D or 3D. No placeholder performance data.</p>
      </div>
      <button type="button" className="ql-guide-button" onClick={onOpenGuide}>
        <BookOpen size={16}/> How to use QuantLab <ArrowRight size={14}/>
      </button>
    </header>

    <nav className="ql-family-tabs" aria-label="Mathematical model families">
      {SECTIONS.map((name,i)=><button type="button" key={name} onClick={()=>changeGroup(name)}
        className={'ql-family-button '+(name===group?'active':'')} aria-current={name===group?'page':undefined}>
        <span className="ql-family-index">{String(i+1).padStart(2,'0')}</span>{name}
        <small>{catalog.filter(m=>m.group===name).length}</small>
      </button>)}
    </nav>
    {catalogError&&<div className="ql-alert bad" role="alert">Model catalog unavailable: {catalogError}</div>}
    {!catalogError&&!catalog.length&&<p className="ql-muted">Connecting to the local Python model registry…</p>}
    <div className="ql-content-grid">
      <section className="ql-card ql-model-selector">
        <div className="ql-panel-title"><Layers size={17}/><h3>{group}</h3><span>{groupModels.length} algorithms</span></div>
        <div className="ql-model-list">{groupModels.map(spec=><button
          type="button" key={spec.id} className={'ql-model-option '+(modelId===spec.id?'selected':'')}
          onClick={()=>changeModel(spec.id)}>
          <span className="ql-model-title">{spec.title}</span>
          <span className={'ql-mode '+spec.mode}>{MODE_LABELS[spec.mode]}</span>
          <small>{spec.description}</small>
          {modelId===spec.id&&<CheckCircle2 size={17} className="ql-check"/>}
        </button>)}</div>
        {savedRuns.length>0&&<div className="ql-saved-runs">
          <div className="ql-panel-title"><Database size={15}/><h3>Saved model runs</h3><span>{savedRuns.length}</span></div>
          {savedRuns.slice(0,8).map(run=><button type="button" key={run.id}
            onClick={()=>void reopen(run)} disabled={working}>
            <strong>{run.title}</strong><small>{run.mode.toUpperCase()} · {run.generated_utc?.slice(0,16).replace('T',' ')}</small>
          </button>)}
          <p className="ql-muted">Saved locally with exact parameters and source checksums. Reopen to compare or export.</p>
        </div>}
        <div className="ql-sidebar-help"><ShieldCheck size={17}/><p>Every model has validated input bounds and a documented evidence type. Live broker execution is disabled.</p></div>
      </section>
      <div className="ql-main-column">
        {selected?<><section className="ql-card ql-selected-header">
          <div><span className={'ql-mode '+selected.mode}>{MODE_LABELS[selected.mode]}</span>
            <h3>{selected.title}</h3><p>{selected.description}</p></div>
          <div className="ql-equation" aria-label="Mathematical model formula">{selected.formula}</div>
        </section>
        <nav className="ql-inner-tabs" aria-label="Selected model views">
          {([['configure','Parameters',SlidersHorizontal],['figures','2D / 3D Graphs',Activity],
             ['numbers','Results & diagnostics',Database],['method','Theory & limitations',BookOpen]] as const).map(
            ([id,title,Icon])=><button type="button" key={id}
              aria-current={view===id?'page':undefined}
              className={view===id?'active':''} onClick={()=>setView(id)}>
              <Icon size={15}/>{title}</button>)}
        </nav>
        {view==='configure'&&<section className="ql-card">
          <div className="ql-panel-title"><FlaskConical size={18}/><h3>Experiment setup</h3></div>
          <label className="ql-field"><span>Source dataset</span>
            <select value={selectedDataset} onChange={e=>onSelectDataset(e.target.value)}>
              <option value="">No dataset selected</option>
              {datasets.map(d=><option key={d.id} value={d.id}>{d.label}{d.ready?'':' · incomplete'}</option>)}
            </select></label>
          <p className="ql-note">{dataHint}</p>
          {syntheticHistory&&<p className="ql-alert warning" role="status">
            <CircleAlert size={15}/> SYNTHETIC FIXTURE · These demo prices are generated, not
            historical market observations. Model fits are for interface/testing use only.
          </p>}
          {readinessError&&<p className="ql-alert bad">{readinessError}</p>}
          {observedNeeded&&readiness&&<div className="ql-readiness">
            <div><strong>{readiness.observed_dates??0}</strong><small>Observed price dates</small></div>
            <div><strong>{readiness.eligible_assets_60??0}</strong><small>Assets with 60+ returns</small></div>
            <div><strong>{readiness.eligible_assets_180??0}</strong><small>Assets with 180+ returns</small></div>
          </div>}
          {observedNeeded&&selectedDataset&&<div className="ql-coverage-panel" role="region" aria-label="Model data requirements">
            <div className="ql-panel-title"><Database size={17}/><h3>Data requirements & shared history</h3></div>
            {planLoading?<p className="ql-muted"><LoaderCircle size={14} className="ql-spinning"/> Checking aligned observations…</p>:
            dataPlan?<><div className="ql-coverage-stats">
              <div><small>Observed common returns</small><strong>{dataPlan.common_returns??0}</strong></div>
              <div><small>Model minimum</small><strong>{dataPlan.min_returns}</strong></div>
              <div><small>Preferred +20% target</small><strong>{dataPlan.target_returns}</strong></div>
              <div><small>Still needed for target</small><strong>{dataPlan.missing_to_target??0}</strong></div>
            </div>
              <p className={dataPlan.runnable?'ql-alert good':'ql-alert warning'}>
                {dataPlan.runnable?<CheckCircle2 size={16}/>:<CircleAlert size={16}/>}
                {dataPlan.message}{dataPlan.status==='ready_minimum'?' The model can run, but the preferred research buffer is not yet met.':''}
              </p>
              {dataPlan.can_download&&<div className="ql-download-offer">
                <p><strong>Use shared market history</strong> · Reuse cached NIFTY / BANK NIFTY securities first.
                  Request missing Dhan daily windows from {dataPlan.suggested_start} to {dataPlan.suggested_end_exclusive} (end exclusive).
                  Existing observations will be appended, not replaced. The exact number of market sessions cannot be guaranteed.</p>
                <div className="ql-coverage-stats">
                  <div><small>Calendar weekdays in candidate window</small>
                    <strong>{dataPlan.estimated_calendar_weekdays??'N/A'}</strong></div>
                  <div><small>Max instrument-weekday combinations</small>
                    <strong>{dataPlan.estimated_max_instrument_day_requests??'N/A'}</strong></div>
                  <div><small>Instrument-calendar days already cached</small>
                    <strong>{dataPlan.cached_instrument_calendar_days??'N/A'}</strong></div>
                  <div><small>Uncovered date windows</small>
                    <strong>{dataPlan.missing_uncovered_windows??'N/A'}</strong></div>
                  <div><small>Estimated NEW Dhan daily requests</small>
                    <strong>{dataPlan.estimated_vendor_daily_requests??'N/A'}</strong></div>
                </div>
                <p className="ql-note">{dataPlan.request_scope_note}</p>
                <button type="button" disabled={!!extensionJob&&['queued','running'].includes(extensionJob.status)}
                  onClick={()=>void extendHistory()}>
                  <Download size={15}/> {extensionJob&&['queued','running'].includes(extensionJob.status)?
                    'Downloading / preparing…':'Yes — download & prepare missing data'}
                </button>
              </div>}
              {!dataPlan.can_download&&dataPlan.download_explanation&&dataPlan.status!=='ready_with_buffer'&&
                <p className="ql-muted">{dataPlan.download_explanation}</p>}
            </>:<p className="ql-muted">No model coverage result yet.</p>}
            {planError&&<p className="ql-alert bad">{planError}</p>}
            {extensionMessage&&<p className="ql-alert good" role="status"><CheckCircle2 size={16}/>{extensionMessage}</p>}
            {extensionError&&<p className="ql-alert bad" role="alert">{extensionError}</p>}
          </div>}
          <div className="ql-param-grid">{selected.parameters.map(spec=><label className="ql-field" key={spec.key}>
            <span>{spec.key.replaceAll('_',' ')}</span>
            {spec.type==='select'?<select value={String(params[spec.key]??spec.default)}
              onChange={e=>setParams({...params,[spec.key]:e.target.value})}>
              {spec.options?.map(opt=><option key={opt} value={opt}>{opt}</option>)}
            </select>:<input type="number" value={params[spec.key]??spec.default}
              min={spec.min} max={spec.max} step={spec.step}
              onChange={e=>setParams({...params,[spec.key]:e.target.value===''?NaN:Number(e.target.value)})}/>}
            {spec.description&&<small>{spec.description}</small>}
          </label>)}</div>
          <div className="ql-config-library">
            <div className="ql-panel-title"><Save size={17}/><h3>Reusable model configurations</h3>
              <span>{configs.filter(x=>x.payload.model_id===selected.id).length} saved</span></div>
            <p className="ql-note">Presets store the exact parameters and selected dataset reference. Draft edits are also saved locally as you type.</p>
            <div className="ql-actions">
              <button type="button" disabled={configBusy} onClick={()=>void storeConfig()}>
                <Save size={15}/> Save current configuration</button>
              {onOpenWorkspace&&<button type="button" onClick={onOpenWorkspace}>
                <ArrowRight size={14}/> Open Research Workspace</button>}
            </div>
            {configs.filter(item=>item.payload.model_id===selected.id).map(item=>
              <div className="ql-config-row" key={item.id}>
                <div><strong>{item.title}</strong><small>{item.payload.dataset_id||'No historical dataset'}</small></div>
                <button type="button" title="Load configuration" disabled={configBusy}
                  onClick={()=>applyConfig(item)}><ArrowRight size={14}/> Load</button>
                <button type="button" aria-label={'Duplicate '+item.title} disabled={configBusy}
                  onClick={()=>void storeConfig(item)}><Copy size={14}/></button>
                <button type="button" aria-label={'Favorite '+item.title} disabled={configBusy}
                  onClick={()=>void configAction(item,item.favorite?'unfavorite':'favorite')}>
                  <Heart size={14} fill={item.favorite?'currentColor':'none'}/></button>
                <button type="button" aria-label={'Delete '+item.title} disabled={configBusy}
                  onClick={()=>void configAction(item,'trash')}><Trash2 size={14}/></button>
              </div>)}
            {configMessage&&<p className="ql-note" role="status">{configMessage}</p>}
          </div>
          {insufficient&&<p className="ql-alert warning"><CircleAlert size={16}/> {dataHint}
            {readiness?.has_prices!==false?' Use a longer history or a theoretical model.':''}</p>}
          {error&&<p className="ql-alert bad" role="alert"><CircleAlert size={16}/>{error}</p>}
          <div className="ql-actions"><button type="button" className="ql-run" disabled={working||!!insufficient}
            onClick={()=>void run()}>
            {working?<LoaderCircle size={16} className="ql-spinning"/>:<Play size={16}/>}
            {working?'Computing in Python…':'Run selected model'}
          </button>
          <span>Read-only · No trading orders · Deterministic seeds where applicable</span></div>
        </section>}
        {view==='figures'&&<section className="ql-figures">
          {result&&result.model_id===selected.id?
            result.plots.length?result.plots.map((plot,i)=><ResearchPlot key={i} plot={plot}/>):
            <div className="ql-card ql-empty">The selected computation returned no figures. Inspect its numerical results.</div>
            :<div className="ql-card ql-empty"><Activity size={24}/>
              <h3>Run {selected.title} to generate graphs</h3><p>Every graph comes from the Python model, not a static illustration.</p>
              <button type="button" onClick={()=>setView('configure')}>Configure model <ArrowRight size={15}/></button>
            </div>}
        </section>}
        {view==='numbers'&&<section className="ql-card">
          <div className="ql-panel-title"><Database size={17}/><h3>Computed measurements</h3></div>
          {result&&result.model_id===selected.id?<><div className="ql-metrics">
            {result.metrics.map((m,i)=><div key={i}><small>{m.label}</small>
              <strong>{valueText(m.value)}</strong><span>{m.unit}</span></div>)}</div>
            {result.source&&<div className="ql-source"><h4>Actual dataset lineage</h4>
              <p>{result.source.dataset_label} · {result.source.source_file} · {result.source.frequency} · {result.source.observations} common observed returns</p>
              <p>{result.source.from_date} → {result.source.to_date} · {result.source.assets.join(', ')}</p>
              <small>Selection rule: {result.source.selection_rule}</small></div>}
            {!!result.table.length&&<div className="ql-table-scroll">
              <table><thead><tr>{Object.keys(result.table[0]).map(k=><th key={k}>{k.replaceAll('_',' ')}</th>)}</tr></thead>
                <tbody>{result.table.slice(0,30).map((row,i)=><tr key={i}>{Object.keys(result.table[0]).map(k=>
                  <td key={k}>{valueText(row[k])}</td>)}</tr>)}</tbody></table>
            </div>}
            <div className="ql-actions"><button type="button" onClick={()=>exportResult(selected.id,result,'json')}><Download size={15}/> Export reproducible JSON</button>
              <button type="button" onClick={()=>exportResult(selected.id,result,'csv')}><Download size={15}/> Export table CSV</button></div>
            {result.run_id&&<div className="ql-config-library">
              <div className="ql-panel-title"><BookOpen size={16}/><h3>Add computed result to a research report</h3></div>
              <div className="ql-actions">
                <label className="ql-field"><span>Research notebook</span>
                  <select value={notebookTarget} onChange={e=>setNotebookTarget(e.target.value)}>
                    <option value="">Choose notebook</option>
                    {notebooks.map(n=><option value={n.id} key={n.id}>{n.title}</option>)}
                  </select></label>
                <button disabled={configBusy||!notebookTarget} onClick={()=>void addRunToNotebook()}>
                  <Save size={14}/> Add model result to report</button>
              </div>
              {configMessage&&<p className="ql-note" role="status">{configMessage}</p>}
            </div>}
          </>:<div className="ql-empty">Run this model to inspect exact metrics, selected assets and numerical diagnostics.</div>}
        </section>}
        {view==='method'&&<section className="ql-card">
          <div className="ql-panel-title"><BookOpen size={17}/><h3>Mathematics and research interpretation</h3></div>
          <div className="ql-method"><h4>Mathematical definition</h4><p className="ql-formula">{selected.formula}</p>
            <h4>What this model computes</h4><p>{selected.description}</p>
            <h4>Evidence requirement</h4><p>{selected.mode==='historical'?
              'Fits to observed local prices. At least '+selected.min_observations+' common finite return observations are required; incomplete sessions are not filled. Reported fit is in-sample unless a strict validation algorithm is explicitly selected.'
              :selected.mode==='synthetic'?
              'This is a seeded synthetic simulation; select a seed to reproduce paths. It is not an empirical forecast or trading signal.'
              :'This is an analytical or numerical theoretical experiment. Inputs are user assumptions, not measured market quotes.'}</p>
            <h4>Limits and responsible reporting</h4>
            <p>Prepared Dhan index spot benchmarks are price-index series, not dividend-reinvested total returns. Splits, delistings, data-vintage issues and actual execution costs need independent review before performance claims.</p>
            {result?.limitations.map((message,i)=><div className="ql-alert warning" key={i}>{message}</div>)}
            <button type="button" className="ql-guide-button" onClick={onOpenGuide}><BookOpen size={14}/> Open complete user guide</button>
          </div>
        </section>}
        {result&&<div className="ql-status-banner"><CheckCircle2 size={16}/>
          <strong>{result.title} calculated</strong>
          <span>{result.mode.toUpperCase()} · {new Date(result.generated_utc).toLocaleString()}</span>
          <button type="button" onClick={()=>setView('numbers')}>Review results <ArrowRight size={13}/></button>
          {onOpenWorkspace&&<button type="button" onClick={onOpenWorkspace}>
            Compare in Research Workspace <ArrowRight size={13}/></button>}
        </div>}
        </>:<section className="ql-card ql-empty">Select a registered model to begin.</section>}
      </div>
    </div>
  </div>
}

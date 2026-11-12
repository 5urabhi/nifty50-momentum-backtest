import {useCallback, useEffect, useMemo, useState} from 'react'
import {Activity, ArrowRight, BookOpen, CheckCircle2, CircleAlert, Database,
  Download, FlaskConical, Layers, LoaderCircle, Play, ShieldCheck, SlidersHorizontal} from 'lucide-react'
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
  model_id:string;title:string;group:string;mode:string;formula:string;
  generated_utc:string;params:Record<string,number|string>;source?:{
    dataset_id:string;dataset_label:string;frequency:string;observations:number;
    assets:string[];from_date:string;to_date:string;source_file:string;
    selection_rule:string;benchmark_kind:string
  }|null;metrics:{label:string;value:string|number|null;unit:string}[];
  plots:ResearchPlotData[];table:Record<string,unknown>[];
  limitations:string[];notes:string[]
}
type Readiness={dataset_id:string;frequency?:string;observed_dates?:number;
  eligible_assets_60?:number;eligible_assets_180?:number;has_prices:boolean;
  sample_start?:string;sample_end?:string;benchmark_kind?:string;warning?:string}
type Props={
  section:'mathematics'|'models';
  datasets:Datum[];
  selectedDataset:string;
  onSelectDataset:(id:string)=>void;
  onOpenGuide:()=>void
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
export default function ModelLaboratory({section,datasets,selectedDataset,onSelectDataset,onOpenGuide}:Props){
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
  useEffect(()=>{
    let active=true
    getJSON<{models:ModelSpec[]}>('/lab/catalog').then(data=>{
      if(active)setCatalog(data.models)
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
    if(selected){setParams(defaultParams(selected))}
  },[selected?.id,defaultParams])
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
  const min=selected?.min_observations||0
  const insufficient=observedNeeded&&(
    !selectedDataset||readiness?.has_prices===false||
    (readiness?.observed_dates!==undefined&&readiness.observed_dates<=min)
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
    }catch(e){setError(e instanceof Error?e.message:String(e));setView('configure')}
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
          {readinessError&&<p className="ql-alert bad">{readinessError}</p>}
          {observedNeeded&&readiness&&<div className="ql-readiness">
            <div><strong>{readiness.observed_dates??0}</strong><small>Observed price dates</small></div>
            <div><strong>{readiness.eligible_assets_60??0}</strong><small>Assets with 60+ returns</small></div>
            <div><strong>{readiness.eligible_assets_180??0}</strong><small>Assets with 180+ returns</small></div>
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
        </div>}
        </>:<section className="ql-card ql-empty">Select a registered model to begin.</section>}
      </div>
    </div>
  </div>
}

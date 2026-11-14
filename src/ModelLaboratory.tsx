import {useCallback, useEffect, useMemo, useRef, useState} from 'react'
import {Activity, ArrowRight, BookOpen, CheckCircle2, CircleAlert, Database,
  Copy, Download, FlaskConical, Heart, Layers, LoaderCircle, Play, Save, ShieldCheck, SlidersHorizontal, Trash2} from 'lucide-react'
import ResearchPlot, {type ResearchPlotData} from './ResearchPlots'
import ModelResultBrief from './ModelResultBrief'
import './model-lab.css'

type Parameter={
  key:string;type:'number'|'integer'|'select'|'symbol'|'quote';default:number|string;
  min?:number;max?:number;step?:number;options?:string[];description?:string
}
type ModelSpec={
  id:string;group:string;title:string;mode:'synthetic'|'theoretical'|'historical'|'market';
  min_observations:number;description:string;formula:string;status:string;
  parameters:Parameter[];chart:string
}
type Datum={id:string;label:string;has_prices:boolean;ready:boolean;source_interval_minutes?:number|null}
type LabResult={
  run_id?:string;model_id:string;title:string;group:string;mode:string;formula:string;
  generated_utc:string;params:Record<string,number|string>;source?:{
    dataset_id:string;dataset_label:string;frequency:string;observations:number;
    assets:string[];from_date:string;to_date:string;source_file:string;
    selection_rule:string;benchmark_kind:string;dataset_kind?:string;
    is_synthetic_fixture?:boolean;source_evidence?:string
  }|null;metrics:{label:string;value:string|number|null;unit:string}[];
  plots:ResearchPlotData[];table:Record<string,unknown>[];
  limitations:string[];notes:string[];calibration?:Record<string,unknown>
}
type SavedRun={id:string;model_id:string;group:string;title:string;mode:string;
  generated_utc:string;dataset_id?:string|null;observations?:number|null;figures:number}
type Readiness={dataset_id:string;frequency?:string;observed_dates?:number;
  eligible_assets_60?:number;eligible_assets_180?:number;has_prices:boolean;
  sample_start?:string;sample_end?:string;benchmark_kind?:string;warning?:string;
  available_symbols?:string[]}
type ModelReadinessMatrix={
  total_models:number;math_ready:number;historical_source_ready:number;
  option_source_ready:number;input_blocked:number;dataset_label:string;
  data_problem:string;
  models:{id:string;group:string;title:string;mode:string;status:string;
    source_ready:boolean;mathematics_ready:boolean;detail:string;next_action:string}[]
}
type ModelSourceOptions={
  dataset_id:string;model_id:string;dataset_label:string;source_file:string|null;
  frequency:string;minimum:number;preferred_with_buffer:number;
  synthetic_fixture:boolean;eligible_count:number;selection_is_explicit:boolean;
  candidates:{ticker:string;returns:number;runnable:boolean;reason:string}[];
  tri:{runnable:boolean;returns:number;reason:string;index_name?:string}
}
type MarketQuoteSnapshot={id:string;dataset_id:string;captured_at:string;source_sha256:string;
  contracts:{provider:string;underlying:string;strike:number;option_type:string;
    captured_at:string;expiry_at:string;row_index:number;bid:number;ask:number;quote_age_days:number}[]}
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
  synthetic:'SEEDED SIMULATION · DEMO',theoretical:'THEORETICAL',
  historical:'HISTORICAL DATA MODEL',market:'OBSERVED QUOTE · MODEL VALUE'
}
const MARKET_PAIRS=[
  {base:'gbm',market:'gbm_fit',label:'Fit to historical data (train / test)'},
  {base:'ou',market:'ou_fit',label:'Fit from historical daily volatility'},
  {base:'merton',market:'merton_fit',label:'Fit historical jump proxy'},
  {base:'heston',market:'heston_proxy',label:'Historical variance proxy (not option calibration)'},
  {base:'black_scholes',market:'black_scholes_quote',label:'Use observed option bid/ask'},
  {base:'binomial',market:'binomial_quote',label:'Use observed option bid/ask'},
  {base:'implied_vol',market:'implied_vol_quote',label:'Calculate from actual quoted premium'},
  {base:'mc_option',market:'mc_option_quote',label:'Use real quote + simulated payoff'},
  {base:'option_surface',market:'option_surface_quote',label:'Anchor scenarios to observed quote'},
] as const
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
  const [modelSearch,setModelSearch]=useState('')
  const [modelFilter,setModelFilter]=useState<'all'|'data'|'math'>('all')
  const [quoteSearch,setQuoteSearch]=useState('')
  const [sourceChoices,setSourceChoices]=useState<ModelSourceOptions|null>(null)
  const [sourceChoiceError,setSourceChoiceError]=useState('')
  const [sourceChoiceLoading,setSourceChoiceLoading]=useState(false)
  const [matrix,setMatrix]=useState<ModelReadinessMatrix|null>(null)
  const [matrixError,setMatrixError]=useState<string|null>(null)
  const [matrixLoading,setMatrixLoading]=useState(false)
  const [quoteSnapshots,setQuoteSnapshots]=useState<MarketQuoteSnapshot[]>([])
  const [quoteFile,setQuoteFile]=useState<File|null>(null)
  const [quoteConfirmed,setQuoteConfirmed]=useState(false)
  const [quoteLoading,setQuoteLoading]=useState(false)
  const [quoteError,setQuoteError]=useState('')
  const [quoteMessage,setQuoteMessage]=useState('')
  const [dhanUnderlying,setDhanUnderlying]=useState<'NIFTY50'|'BANKNIFTY'>('NIFTY50')
  const [dhanQuoteJob,setDhanQuoteJob]=useState<{
    id:string;status:string;error?:string;
    result?:{id:string;contracts:number;expiry:string;warning:string}
  }|null>(null)
  const [dhanQuoteMessage,setDhanQuoteMessage]=useState('')
  const [dhanQuoteError,setDhanQuoteError]=useState('')
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
  const refreshMatrix=useCallback(async()=>{
    setMatrixLoading(true);setMatrixError(null)
    try{
      const query=selectedDataset?'?dataset_id='+encodeURIComponent(selectedDataset):''
      const result=await getJSON<ModelReadinessMatrix>('/lab/model-readiness'+query)
      setMatrix(result)
    }catch(e){setMatrixError(e instanceof Error?e.message:String(e))}
    finally{setMatrixLoading(false)}
  },[selectedDataset])
  useEffect(()=>{void refreshMatrix()},[refreshMatrix])
  const refreshQuotes=useCallback(async()=>{
    if(!selectedDataset){setQuoteSnapshots([]);return}
    try{
      const data=await getJSON<{snapshots:MarketQuoteSnapshot[]}>(
        '/lab/option-quotes?dataset_id='+encodeURIComponent(selectedDataset))
      setQuoteSnapshots(data.snapshots)
    }catch(e){setQuoteError(e instanceof Error?e.message:String(e))}
  },[selectedDataset])
  useEffect(()=>{setQuoteError('');setQuoteMessage('');setQuoteFile(null)
    void refreshQuotes()},[refreshQuotes])
  const fetchDhanOptionChain=async()=>{
    if(!selectedDataset||quoteLoading||dhanQuoteJob&&['queued','running'].includes(dhanQuoteJob.status))return
    setDhanQuoteError('');setDhanQuoteMessage('')
    try{
      const response=await fetch('/api/lab/option-quotes/dhan',{
        method:'POST',credentials:'same-origin',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({dataset_id:selectedDataset,
          underlying:dhanUnderlying,confirm_readonly:true})})
      if(!response.ok)throw new Error(await errorText(response))
      const job=await response.json() as {job_id:string;status:string}
      setDhanQuoteJob({id:job.job_id,status:job.status})
      setDhanQuoteMessage('Authorized read-only Dhan option-chain request queued. No orders will be submitted.')
    }catch(e){setDhanQuoteError(e instanceof Error?e.message:String(e))}
  }
  useEffect(()=>{
    if(!dhanQuoteJob||!['queued','running'].includes(dhanQuoteJob.status))return
    let active=true
    const timer=window.setTimeout(()=>{
      void getJSON<{status:string;error?:string;
        result?:{id:string;contracts:number;expiry:string;warning:string}}>('/jobs/'+
          encodeURIComponent(dhanQuoteJob.id)).then(job=>{
        if(!active)return
        setDhanQuoteJob(prev=>prev?{...prev,...job}:null)
        if(job.status==='complete'&&job.result){
          setDhanQuoteMessage(job.result.contracts+' actual Dhan quote contracts captured for expiry '+
            job.result.expiry+'. '+job.result.warning)
          setParams(prev=>({...prev,quote:job.result!.id+':0'}))
          void refreshQuotes()
          void refreshMatrix()
        }
        if(job.status==='error')setDhanQuoteError(job.error||'Dhan option-chain read failed.')
      }).catch(e=>{if(active)setDhanQuoteError(e instanceof Error?e.message:String(e))})
    },1400)
    return()=>{active=false;window.clearTimeout(timer)}
  },[dhanQuoteJob,refreshQuotes,refreshMatrix])
  const uploadOptionQuotes=async()=>{
    if(!quoteFile||!selectedDataset||!quoteConfirmed||quoteLoading)return
    setQuoteLoading(true);setQuoteError('');setQuoteMessage('')
    try{
      const form=new FormData()
      form.append('dataset_id',selectedDataset)
      form.append('file',quoteFile)
      form.append('confirm_original_quote','true')
      const response=await fetch('/api/lab/option-quotes/import',{
        method:'POST',credentials:'same-origin',body:form})
      if(!response.ok)throw new Error(await errorText(response))
      const created=await response.json() as {id:string;contracts:unknown[];warning:string}
      setQuoteMessage('Original source snapshot saved. '+created.warning)
      setQuoteFile(null);setQuoteConfirmed(false)
      setParams(prev=>({...prev,quote:created.id+':0'}))
      await refreshQuotes()
      void refreshMatrix()
    }catch(e){setQuoteError(e instanceof Error?e.message:String(e))}
    finally{setQuoteLoading(false)}
  }
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
  const groupModels=catalog.filter(spec=>spec.group===group
    &&(modelFilter==='all'||(modelFilter==='data'
      ?['historical','market'].includes(spec.mode)
      :['theoretical','synthetic'].includes(spec.mode)))
    &&(spec.title+' '+spec.description+' '+spec.id).toLowerCase().includes(modelSearch.trim().toLowerCase()))
  const selected=catalog.find(spec=>spec.id===modelId)
  const modelPair=MARKET_PAIRS.find(pair=>pair.base===selected?.id||pair.market===selected?.id)
  const singleSeries=!!selected&&['gbm_fit','ou_fit','merton_fit','heston_proxy'].includes(selected.id)
  const currentModelStatus=matrix?.models.find(item=>item.id===selected?.id)
  const quoteRefs=quoteSnapshots.flatMap(snapshot=>snapshot.contracts.map(contract=>({
    value:snapshot.id+':'+contract.row_index,
    label:contract.provider+' · '+contract.underlying+' '+contract.strike+' '+contract.option_type+
      ' · '+contract.expiry_at.slice(0,10)+' · bid '+contract.bid+' / ask '+contract.ask+
      ' · captured '+contract.captured_at.slice(0,16).replace('T',' ')
  })))
  const shownQuoteRefs=quoteRefs.filter(item=>
    item.value===String(params.quote||'')||
    item.label.toLowerCase().includes(quoteSearch.trim().toLowerCase())).slice(0,150)
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
    setModelSearch('');setModelFilter('all')
    const first=catalog.find(spec=>spec.group===next)
    setModelId(first?.id||'')
    setResult(null);setError(null);setView('configure')
  }
  const changeModel=(id:string)=>{
    setModelId(id);setModelSearch('');setModelFilter('all');setResult(null);setError(null);setView('configure')
  }
  const observedNeeded=selected?.mode==='historical'||selected?.mode==='market'
  useEffect(()=>{
    setSourceChoices(null);setSourceChoiceError('')
    if(!singleSeries||!selectedDataset||!selected)return
    let active=true
    setSourceChoiceLoading(true)
    getJSON<ModelSourceOptions>('/lab/model-inputs?dataset_id='+
      encodeURIComponent(selectedDataset)+'&model_id='+encodeURIComponent(selected.id))
      .then(choices=>{if(active)setSourceChoices(choices)})
      .catch(err=>{if(active)setSourceChoiceError(err instanceof Error?err.message:String(err))})
      .finally(()=>{if(active)setSourceChoiceLoading(false)})
    return()=>{active=false}
  },[singleSeries,selectedDataset,selected?.id])
  const syntheticHistory=selected?.mode==='historical'&&selectedDataset==='synthetic'
  const min=selected?.min_observations||0
  const requestedAssets=Number(params.assets??8)
  const requestedWindow=Number(params.train_window??60)
  useEffect(()=>{
    setDataPlan(null);setPlanError(null)
    if(!selected||!['historical','market'].includes(selected.mode)||!selectedDataset)return
    let active=true
    setPlanLoading(true)
    const query=new URLSearchParams({model_id:selected.id,dataset_id:selectedDataset,
      assets:String(requestedAssets),train_window:String(requestedWindow)})
    if(['gbm_fit','ou_fit','merton_fit','heston_proxy'].includes(selected.id)){
      query.set('target',String(params.target||(selected.id==='gbm_fit'?'benchmark_tri':'stock')))
      query.set('ticker',String(params.ticker||''))
    }
    if(selected.mode==='market')query.set('quote',String(params.quote||''))
    getJSON<DataPlan>('/lab/data-requirements?'+query.toString())
      .then(plan=>{if(active)setDataPlan(plan)})
      .catch(e=>{if(active)setPlanError(e instanceof Error?e.message:String(e))})
      .finally(()=>{if(active)setPlanLoading(false)})
    return()=>{active=false}
  },[selected?.id,selected?.mode,selectedDataset,requestedAssets,requestedWindow,extensionJob?.status,params.target,params.ticker,params.quote])
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
          dataset_id:observedNeeded?selectedDataset:null,params}),
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
  const workflowInstruction=result&&result.model_id===selected?.id?
    'Your run is saved. Inspect the diagnostic comparison and export any figure.':
    !selected?'Choose a mathematical model.':
    !observedNeeded?'Parameters are ready; click Run selected model to compute.':
    !selectedDataset?'Choose one saved research dataset to continue.':
    selected.mode==='market'&&!params.quote?
      'Fetch a read-only Dhan option chain or import original option quotes, then choose a contract.':
    singleSeries&&params.target==='stock'&&!params.ticker?
      'Select an eligible stock symbol from the input checklist; QuantLab never silently substitutes one.':
    planLoading?'Checking the exact input requirements…':
    dataPlan&&!dataPlan.runnable?
      dataPlan.message:
    'The selected inputs pass preflight. Run the model and inspect its computed diagnostics.'
  const workflowStage=!selected?1:
    result&&result.model_id===selected.id?4:
    observedNeeded&&(!selectedDataset||!!insufficient)?2:3
  const dataHint=useMemo(()=>{
    if(!observedNeeded)return 'Mathematical engine ready. Inputs are assumptions; any simulated paths are artificial.'
    if(selected?.mode==='market')return 'Use a saved original option bid/ask and expiry; option model outputs remain theoretical valuations.'
    if(!selectedDataset)return 'Select the saved NIFTY/BANK NIFTY research dataset first.'
    if(!readiness)return 'Inspecting local sample availability…'
    return (readiness.frequency||'unknown')+' observations · '+readiness.observed_dates+
      ' recorded dates · at least '+min+' common returns required.'
  },[observedNeeded,selected?.mode,selectedDataset,readiness,min])
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

    <section className="ql-guided-next" aria-label="Research workflow">
      <div className="ql-guided-track">
        {['Choose model','Select real inputs','Run calculation','Interpret & export'].map((name,i)=>
          <span key={name} className={workflowStage===i+1?'active':workflowStage>i+1?'done':''}>
            <b>{i+1}</b>{name}</span>)}
      </div>
      <p><ArrowRight size={15}/>{workflowInstruction}</p>
    </section>
    <nav className="ql-family-tabs" aria-label="Mathematical model families">
      {SECTIONS.map((name,i)=><button type="button" key={name} onClick={()=>changeGroup(name)}
        className={'ql-family-button '+(name===group?'active':'')} aria-current={name===group?'page':undefined}>
        <span className="ql-family-index">{String(i+1).padStart(2,'0')}</span>{name}
        <small>{catalog.filter(m=>m.group===name).length}</small>
      </button>)}
    </nav>
    <details className="ql-model-matrix" aria-label="All model input readiness">
      <summary><div><span className="ql-kicker">MODEL COMPLETENESS / LIVE SOURCE CHECKLIST</span>
        <h3>What can run with the selected data?</h3>
        <p>Mathematical models always compute. Historical fits and option-quote calculations
          depend on genuine local source inputs. Click to inspect every model and its next action.</p></div>
        {matrix&&<span className="ql-model-matrix-count">
          {matrix.total_models} registered · {matrix.historical_source_ready} historical source-ready ·
          {matrix.option_source_ready} quote-ready · {matrix.input_blocked} need inputs
        </span>}</summary>
      {matrixLoading&&<p className="ql-note" role="status">Checking local dataset and saved quote evidence…</p>}
      {matrixError&&<p className="ql-alert bad" role="alert">{matrixError}</p>}
      {matrix&&<><div className="ql-matrix-summary">
        <div><strong>{matrix.math_ready}</strong><small>Math and simulations runnable (assumptions)</small></div>
        <div><strong>{matrix.historical_source_ready}</strong><small>Historical data source-ready</small></div>
        <div><strong>{matrix.option_source_ready}</strong><small>Original quote source-ready</small></div>
        <div><strong>{matrix.input_blocked}</strong><small>Missing model-specific inputs</small></div>
      </div>
      {matrix.data_problem&&<p className="ql-alert bad">{matrix.data_problem}</p>}
      <div className="ql-matrix-models">
        {matrix.models.map(entry=><button type="button" key={entry.id}
          onClick={()=>{setGroup(entry.group);changeModel(entry.id)}}>
          <strong>{entry.title}</strong><span className={'ql-matrix-status '+entry.status}>
            {entry.status==='math_ready'?'Math runnable':
             entry.status==='source_available'?'Source available':
             entry.status==='need_option_quote'?'Needs option quote':
             entry.status==='fixture_only'?'Synthetic test fixture':'Needs historical data'}</span>
          <small>{entry.detail}</small><em>Next: {entry.next_action}</em>
        </button>)}
      </div></>}
    </details>
    {catalogError&&<div className="ql-alert bad" role="alert">Model catalog unavailable: {catalogError}</div>}
    {!catalogError&&!catalog.length&&<p className="ql-muted">Connecting to the local Python model registry…</p>}
    <div className="ql-content-grid">
      <section className="ql-card ql-model-selector">
        <div className="ql-panel-title"><Layers size={17}/><h3>{group}</h3><span>{groupModels.length} visible</span></div>
        <label className="ql-field"><span>Find a model</span>
          <input type="search" value={modelSearch} placeholder="Search name or algorithm..."
            onChange={e=>setModelSearch(e.target.value)} /></label>
        <div className="ql-model-filters" role="group" aria-label="Show model types">
          {([['all','All'],['data','Uses market data'],['math','Math & simulation']] as const).map(([key,label])=>
            <button type="button" key={key} aria-pressed={modelFilter===key}
              onClick={()=>setModelFilter(key)}>{label}</button>)}
        </div>
        <div className="ql-model-list">{groupModels.map(spec=><button
          type="button" key={spec.id} className={'ql-model-option '+(modelId===spec.id?'selected':'')}
          onClick={()=>changeModel(spec.id)}>
          <span className="ql-model-title">{spec.title}</span>
          <span className={'ql-mode '+spec.mode}>{MODE_LABELS[spec.mode]}</span>
          {matrix&&['historical','market'].includes(spec.mode)&&<span
            className={'ql-model-check '+(matrix.models.find(item=>item.id===spec.id)?.source_ready?'ready':'missing')}>
            {matrix.models.find(item=>item.id===spec.id)?.source_ready?
              'Source available':'Needs inputs'}</span>}
          <small>{spec.description}</small>
          {modelId===spec.id&&<CheckCircle2 size={17} className="ql-check"/>}
        </button>)}</div>
        {!groupModels.length&&<p className="ql-note">No models match that filter. Choose All or clear search.</p>}
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
            <h3>{selected.title}</h3><p>{selected.description}</p>
            {modelPair&&
              <div className="ql-gbm-mode-choice" role="group" aria-label="Choose model research approach">
                <button type="button" aria-pressed={selected.id===modelPair.base}
                  onClick={()=>changeModel(modelPair.base)}
                  className={selected.id===modelPair.base?'active':''}>
                  Explore mathematics (assumed parameters)</button>
                <button type="button" aria-pressed={selected.id===modelPair.market}
                  onClick={()=>changeModel(modelPair.market)}
                  className={selected.id===modelPair.market?'active':''}>
                  {modelPair.label}</button>
              </div>}
            {selected.id==='gbm_fit'&&
              <div className="ql-alert good" role="note">
                <ShieldCheck size={16}/> Fitted drift and volatility use real archived returns
                when the source is observed. The first 80% calibrates the parameters;
                the final 20% is used only for diagnostics. All fan paths are computer simulations.
              </div>}
            {selected.mode==='market'&&<div className="ql-alert warning" role="note">
              <Database size={16}/> A genuine market quote supplies bid, ask, spot, strike
              and expiry. The valuation is still a mathematical MODEL using explicitly
              assumed interest rate and dividend yield. No artificial market premium.
            </div>}
            {selected.id==='heston_proxy'&&<div className="ql-alert warning" role="note">
              <CircleAlert size={16}/> Historical realized-variance proxy only:
              stock prices cannot uniquely identify the risk-neutral Heston volatility surface.
              A full options-chain calibration needs market quotes across strikes and expiries.
            </div>}
            {selected.mode==='synthetic'&&<div className="ql-seed-explain" role="note">
              <strong>SIMULATED EXAMPLE — NOT LIVE OR HISTORICAL MARKET DATA</strong>
              <p><b>Seeded simulation</b> means the model generates artificial scenarios
                using a fixed random seed. Use the same seed to reproduce the same paths.
                These curves are for learning and testing, <b>not</b> predictions or
                evidence of strategy performance.</p>
              <button type="button" onClick={()=>setView('method')}>
                See mathematical assumptions <ArrowRight size={13}/>
              </button>
            </div>}
          </div>
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
          {selected.mode==='market'&&<div className="ql-quote-import" role="region"
             aria-label="Import original provider option quotes">
            <div className="ql-panel-title"><Database size={16}/>
              <h3>Original option quote snapshots · source-bound</h3>
              <span>{quoteRefs.length} saved contracts</span></div>
            <p>Quote CSV must contain <code>captured_at, provider, underlying, underlying_spot,
              expiry_at, strike, option_type, bid, ask</code>.
              Both timestamps must include a UTC offset (for example
              <code> 2026-11-14T10:00:00+05:30</code>).
              QuantLab reads actual bid/ask; it never fabricates a market premium.</p>
            <div className="ql-dhan-quote-fetch">
              <div className="ql-panel-title"><Activity size={15}/>
                <h3>Automatic current option chain · Dhan</h3></div>
              <p>Use your existing local Dhan token to fetch NIFTY 50 or BANK NIFTY best bid/ask
                and exact strikes. Fetch is read-only; underlying IDs and upcoming expiry
                are resolved automatically. Quote timestamps are local capture times;
                the regular-session 15:30 IST expiry time is an explicit assumption.</p>
              <div className="ql-dhan-quote-controls">
                <label className="ql-field"><span>Index underlying</span>
                  <select value={dhanUnderlying}
                    onChange={e=>setDhanUnderlying(e.target.value as 'NIFTY50'|'BANKNIFTY')}
                    disabled={!!dhanQuoteJob&&['queued','running'].includes(dhanQuoteJob.status)}>
                    <option value="NIFTY50">NIFTY 50 · Dhan instrument 13</option>
                    <option value="BANKNIFTY">BANK NIFTY · Dhan instrument 25</option>
                  </select></label>
                <button type="button"
                  disabled={!selectedDataset||quoteLoading||
                    !!dhanQuoteJob&&['queued','running'].includes(dhanQuoteJob.status)}
                  onClick={()=>void fetchDhanOptionChain()}>
                  <Download size={14}/>
                  {dhanQuoteJob&&['queued','running'].includes(dhanQuoteJob.status)?
                    'Fetching Dhan option chain…':'Fetch current Dhan quotes (read-only)'}
                </button>
              </div>
              {dhanQuoteMessage&&<p role="status" className="ql-alert good">{dhanQuoteMessage}</p>}
              {dhanQuoteError&&<p role="alert" className="ql-alert bad">{dhanQuoteError}</p>}
              <p className="ql-note">Dhan subscription/token must permit option-chain API access.
                A live snapshot is not historical options backtest data. No credential
                or proprietary quote is sent to this browser.</p>
            </div>
            <div className="ql-actions">
              <button type="button" onClick={()=>{
                const text='captured_at,provider,underlying,underlying_spot,expiry_at,strike,option_type,bid,ask\n'
                const url=URL.createObjectURL(new Blob([text],{type:'text/csv'}))
                const anchor=document.createElement('a');anchor.href=url
                anchor.download='quantlab_option_quotes_blank_template.csv'
                anchor.click();URL.revokeObjectURL(url)
              }}><Download size={14}/> Download blank CSV template</button>
            </div>
            <label className="ql-field"><span>Choose original option quote CSV</span>
              <input type="file" accept=".csv,text/csv"
                disabled={!selectedDataset||quoteLoading}
                onChange={e=>setQuoteFile(e.target.files?.[0]||null)}/></label>
            <label className="ql-quote-ack"><input type="checkbox"
              checked={quoteConfirmed} onChange={e=>setQuoteConfirmed(e.target.checked)}/>
              I confirm this is a source-provided quote export; these are not generated prices.</label>
            <div className="ql-actions"><button type="button"
              disabled={!selectedDataset||!quoteFile||!quoteConfirmed||quoteLoading}
              onClick={()=>void uploadOptionQuotes()}>
              <Database size={14}/>{quoteLoading?'Importing original quote…':'Import & version quote snapshot'}</button>
              <button type="button" disabled={!selectedDataset||quoteLoading}
                onClick={()=>void refreshQuotes()}><Activity size={14}/> Refresh saved quotes</button></div>
            {quoteError&&<div className="ql-alert bad" role="alert">{quoteError}</div>}
            {quoteMessage&&<div className="ql-alert good" role="status">{quoteMessage}</div>}
          </div>}
          {['gbm_fit','ou_fit','merton_fit','heston_proxy'].includes(selected.id)&&
            <p className="ql-note">NIFTY TRI is the right choice to fit the actual index.
              For an individual security, choose <b>target: stock</b> and select its exact ticker.
              Dhan daily prices are split/bonus adjusted, but that doesn't establish reinvested dividends.
              Fitting never requires an independent vendor to approve every candle.</p>}
          {['gbm_fit','ou_fit','merton_fit','heston_proxy'].includes(selected.id)&&<datalist id="ql-available-stock-symbols">
            {readiness?.available_symbols?.map(name=><option value={name} key={name}/>)}
          </datalist>}
          <div className="ql-param-grid">{selected.parameters.map(spec=><label className="ql-field" key={spec.key}>
            <span>{spec.key.replaceAll('_',' ')}</span>
            {spec.type==='select'?<select value={String(params[spec.key]??spec.default)}
              onChange={e=>setParams({...params,[spec.key]:e.target.value})}>
              {spec.options?.map(opt=><option key={opt} value={opt}>{opt}</option>)}
            </select>:spec.type==='quote'?<select
              value={String(params[spec.key]??spec.default)}
              onChange={e=>setParams({...params,[spec.key]:e.target.value})}>
              <option value="">Select saved original option quote / contract</option>
              {quoteRefs.map(item=><option key={item.value} value={item.value}>{item.label}</option>)}
            </select>:spec.type==='symbol'?<input type="text" list="ql-available-stock-symbols"
              autoComplete="off" value={String(params[spec.key]??spec.default)}
              placeholder="Choose ticker from dataset" maxLength={32}
              disabled={['gbm_fit','ou_fit','merton_fit','heston_proxy'].includes(selected.id)&&params.target!=='stock'}
              onChange={e=>setParams({...params,[spec.key]:e.target.value})}/>:
            <input type="number" value={params[spec.key]??spec.default}
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
          {result&&['gbm_fit','ou_fit','merton_fit','heston_proxy'].includes(result.model_id)&&
            <div className="ql-alert warning" role="note">
              <CircleAlert size={16}/> <strong>HISTORICAL PARAMETERS · SEEDED SIMULATION</strong>
              <span> Observed returns/volatility come from the selected dataset; forward fans are seeded simulations.
                Heston is a historical volatility PROXY, not a uniquely identified options calibration.
                Consult the model-specific holdout and baseline measurements.</span>
            </div>}
          {result&&result.model_id===selected.id&&result.mode==='market'&&
            <div className="ql-alert warning" role="note">
              <CircleAlert size={16}/> <strong>OBSERVED QUOTE INPUTS · THEORETICAL MODEL OUTPUTS</strong>
              <span> Vendor bid/ask are real source inputs. Model premium, implied volatility,
                simulated payoffs or 3D surface are analytical/numerical outputs,
                not a historical options backtest or guaranteed executable trade.</span>
            </div>}
          {result&&result.model_id===selected.id&&result.mode==='synthetic'&&
            <div className="ql-alert warning" role="note">
              <CircleAlert size={16}/> <strong>SEEDED SIMULATION · DEMO RESULTS</strong>
              <span> The graph shows reproducible computer-generated paths, not observed stock
                prices, forecasts, or verified backtest returns.</span>
            </div>}
          {result&&result.model_id===selected.id?
            result.plots.length?result.plots.map((plot,i)=><ResearchPlot key={i} plot={plot}
              provenance={result.mode}/>):
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
            <h4>Evidence requirement</h4><p>{selected.mode==='market'?
              'Use original source-dated option bid/ask snapshots for one named contract. Rate and dividend yield are assumptions; the same-quote implied volatility fit is not independent market validation.'
              :selected.mode==='historical'?
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

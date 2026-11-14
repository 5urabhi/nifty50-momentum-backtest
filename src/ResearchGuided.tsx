import {useEffect,useMemo,useState} from 'react'
import {BarChart3,BookOpen,Database,Gauge,LoaderCircle,Play,ShieldCheck,SlidersHorizontal} from 'lucide-react'
import ResearchPlot,{type ResearchPlotData} from './ResearchPlots'
import {formatMetric} from './metricDisplay'

type Dataset={id:string;label:string;has_prices:boolean;ready:boolean}
type Model={id:string;title:string;group:string;mode:string;formula?:string;
  min_observations?:number;parameters:{key:string;type:string;default:number|string;
    min?:number;max?:number;description?:string}[]}
type Run={id:string;kind:'model_run'|'research_run';label:string;model?:string}
type ModelInfo={model_id:string;title:string;mode:string;minimum:number;formula:string;
  description:string;readiness?:string;observed?:number;target?:number;can_extend?:boolean;
  readiness_message?:string}
type Guidance={title:string;explanation:string;suggested_evaluation:string;
  models:ModelInfo[];steps:string[];warning:string}
type Work={run_count:number;estimated_relative_work_units:number;warning:string;calibration:string}
type Job={job_id:string;status:string}
type ModelResult={title:string;model_id:string;mode:string;params:Record<string,unknown>;
  source?:Record<string,unknown>;metrics:{label:string;value:number|string|null;unit:string}[];
  plots:ResearchPlotData[];warnings?:string[]}
type Props={models:Model[];datasets:Dataset[];selectedDataset:string;
  onSelectDataset:(v:string)=>void;onOpenModels:()=>void;onOpenDhan:()=>void;
  runs:Run[];onStartJob:(j:Job,caption:string)=>void;onMessage:(s:string)=>void;
  onError:(s:string)=>void;onDataChanged:()=>void}
const GOALS=[
  ['portfolio_allocation','Compare portfolio allocation methods'],
  ['volatility','Understand changing volatility'],
  ['tail_risk','Evaluate downside and tail risk'],
  ['stochastic_models','Explore stochastic models'],
  ['derivatives','Study option pricing'],
  ['factor_exposures','Analyze factor return proxies'],
] as const
const format=(v:unknown)=>typeof v==='number'&&Number.isFinite(v)?
  v.toLocaleString(undefined,{maximumFractionDigits:5}):String(v??'N/A')
async function call<T>(url:string,body?:object){
  const r=await fetch('/api/'+url,body?{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(body)}:undefined)
  if(!r.ok){const e=await r.json().catch(()=>({detail:'Research request failed'})) as {detail?:string}
    throw new Error(e.detail||'Research request failed')}
  return r.json() as Promise<T>
}
function Select({title,value,onChange,items}:{title:string;value:string;onChange:(v:string)=>void;
  items:{id:string;label:string}[]}){
  return <label className="rw-field"><span>{title}</span><select value={value} onChange={e=>onChange(e.target.value)}>
    {items.map(x=><option key={x.id} value={x.id}>{x.label}</option>)}</select></label>
}
function Field({title,value,onChange}:{title:string;value:string;onChange:(v:string)=>void}){
  return <label className="rw-field"><span>{title}</span><input value={value}
    onChange={e=>onChange(e.target.value)}/></label>
}
function Guided({models,datasets,selectedDataset,onSelectDataset,onOpenModels,onOpenDhan,
  onMessage,onError,onDataChanged}:Props){
  const [goal,setGoal]=useState('portfolio_allocation')
  const [guidance,setGuidance]=useState<Guidance|null>(null)
  const [selected,setSelected]=useState('')
  const [running,setRunning]=useState(false)
  const [busy,setBusy]=useState(false)
  useEffect(()=>{
    let active=true;setGuidance(null)
    void call<Guidance>('workspace/guided/'+goal+
      '?dataset_id='+encodeURIComponent(selectedDataset))
      .then(v=>{if(active)setGuidance(v)})
      .catch(e=>{if(active)onError(e instanceof Error?e.message:String(e))})
    return()=>{active=false}
  },[goal,selectedDataset,onError])
  const run=async(model_id:string)=>{
    const model=models.find(m=>m.id===model_id)
    if(!model)return
    setBusy(true)
    try{
      const params=Object.fromEntries(model.parameters.map(p=>[p.key,p.default]))
      const result=await call<ModelResult>('lab/run',{model_id,
        dataset_id:model.mode==='historical'?selectedDataset:null,params})
      onMessage('Saved '+result.title+' result. Open Compare & Graph to inspect it.')
      onDataChanged()
    }catch(e){onError(e instanceof Error?e.message:String(e))}
    finally{setBusy(false)}
  }
  const extend=async(model_id:string)=>{
    const model=models.find(m=>m.id===model_id)
    if(!model||!selectedDataset)return
    if(!window.confirm('Download only the uncovered Dhan date windows to the shared price store? This is read-only market-data access.'))return
    setRunning(true)
    try{
      const params=Object.fromEntries(model.parameters.map(p=>[p.key,p.default]))
      const j=await call<Job>('lab/data-requirements/extend',{
        model_id,dataset_id:selectedDataset,params,confirm_download:true})
      onMessage('Shared Dhan data-extension job queued: '+j.job_id+'. See Jobs for status.')
      onDataChanged()
    }catch(e){onError(e instanceof Error?e.message:String(e))}
    finally{setRunning(false)}
  }
  const selectedSpec=guidance?.models.find(m=>m.model_id===selected)
  return <div className="rw-stack">
    <section className="rw-box"><header className="rw-box-head">
      <h3>Guided Research · Define a question, not an algorithm</h3></header>
      <p className="rw-help">Guided and Advanced modes use the same registered Python models; recommendations are deterministic, not performance rankings.</p>
      <Select title="Research objective" value={goal} onChange={setGoal}
        items={GOALS.map(([id,label])=>({id,label}))}/>
      <Select title="Observed research dataset" value={selectedDataset} onChange={onSelectDataset}
        items={[{id:'',label:'Not selected'},...datasets.filter(x=>x.has_prices)
          .map(d=>({id:d.id,label:d.label}))]}/>
      {guidance?<><p className="rw-note">{guidance.explanation}</p>
        <div className="ra-guided-cards">{guidance.models.map(info=>
          <article key={info.model_id} className="ra-guided-card">
            <div><strong>{info.title}</strong><small>{info.mode} · {info.readiness||'Requires no observed dataset'}</small></div>
            <p>{info.description}</p><code>{info.formula}</code>
            {info.target!==undefined&&<p className="rw-help">
              {info.observed??0} observed common returns, {info.minimum} minimum,
              {info.target} preferred (+20%).</p>}
            {info.readiness_message&&<p className="rw-caution">{info.readiness_message}</p>}
            <div className="rw-button-group">
              <button onClick={()=>{setSelected(info.model_id);onOpenModels()}}>
                <BookOpen size={14}/> Model details</button>
              <button className="rw-primary" disabled={busy||
                (info.mode==='historical'&&(!selectedDataset||info.readiness==='insufficient'||info.readiness==='unavailable'))}
                onClick={()=>void run(info.model_id)}><Play size={14}/> Run model</button>
              {info.can_extend&&<button onClick={()=>void extend(info.model_id)} disabled={running}>
                <Database size={14}/> Extend missing data</button>}
            </div>
          </article>)}</div>
        <div className="rw-box"><h3>Research workflow</h3><ol className="ra-steps">
          {guidance.steps.map(step=><li key={step}>{step}</li>)}</ol>
          <p className="rw-caution">{guidance.warning}</p></div></>:
          <p className="rw-help"><LoaderCircle size={14}/> Loading model recommendations…</p>}
      <p className="rw-help">Need a new verified historical series? <button onClick={onOpenDhan}>
        Open shared Dhan market-data manager</button></p>
      {selectedSpec&&<p className="rw-help">Selected: {selectedSpec.title}</p>}
    </section>
  </div>
}
function Grid({models,datasets,selectedDataset,onSelectDataset,onStartJob,onError}:Props){
  const [modelId,setModelId]=useState('gbm')
  const [first,setFirst]=useState('volatility')
  const [second,setSecond]=useState('')
  const [firstValues,setFirstValues]=useState('0.10, 0.20, 0.30')
  const [secondValues,setSecondValues]=useState('')
  const [metric,setMetric]=useState('')
  const [estimate,setEstimate]=useState<Work|null>(null)
  const [busy,setBusy]=useState(false)
  const selected=models.find(x=>x.id===modelId)
  const numeric=(selected?.parameters||[]).filter(x=>x.type==='number'||x.type==='integer')
  const selectors=numeric.map(p=>({id:p.key,label:p.key.replaceAll('_',' ')}))
  const choose=(value:string)=>{
    setModelId(value);setEstimate(null)
    const m=models.find(x=>x.id===value)
    const opts=m?.parameters.filter(x=>x.type==='number'||x.type==='integer')||[]
    const preferred=opts.find(x=>x.key==='volatility')||opts[0]
    if(preferred){
      setFirst(preferred.key);setFirstValues(String(preferred.default))
      setSecond('');setSecondValues('')
    }
  }
  const parse=(v:string)=>v.split(/[,\n]/).map(x=>Number(x.trim()))
  const args=()=>{
    const axes:Record<string,number[]>={[first]:parse(firstValues)}
    if(second)axes[second]=parse(secondValues)
    const params=Object.fromEntries((selected?.parameters||[]).map(p=>[p.key,p.default]))
    return {model_id:modelId,dataset_id:selected?.mode==='historical'?selectedDataset:null,
      params,axes,metric_name:metric||null}
  }
  const preview=async()=>{
    setBusy(true)
    try{
      setEstimate(await call<Work>('workspace/grid/estimate',args()))
    }catch(e){onError(e instanceof Error?e.message:String(e))}
    finally{setBusy(false)}
  }
  const run=async()=>{
    if(!estimate||!window.confirm('Run '+estimate.run_count+
      ' validated configurations using the local Python model? Every run is saved separately.'))return
    setBusy(true)
    try{
      const job=await call<Job>('workspace/grid/run',{...args(),confirm_run:true})
      onStartJob(job,'Two-dimensional parameter grid')
    }catch(e){onError(e instanceof Error?e.message:String(e))}
    finally{setBusy(false)}
  }
  return <div className="rw-two">
    <section className="rw-box">
      <header className="rw-box-head"><h3>Parameter grid · Validate before executing</h3></header>
      <Select title="Registered model" value={modelId} onChange={choose}
        items={models.map(x=>({id:x.id,label:x.title}))}/>
      {selected?.mode==='historical'&&<Select title="Observed dataset" value={selectedDataset}
        onChange={onSelectDataset} items={datasets.filter(x=>x.has_prices)
          .map(x=>({id:x.id,label:x.label}))}/>}
      <div className="rw-form-grid">
        <Select title="Primary parameter" value={first} onChange={v=>{setFirst(v);setEstimate(null)}}
          items={selectors}/>
        <Field title="2–12 distinct values, comma-separated" value={firstValues}
          onChange={v=>{setFirstValues(v);setEstimate(null)}}/>
        <Select title="Secondary parameter (optional)" value={second}
          onChange={v=>{setSecond(v);setEstimate(null)}} items={[{id:'',label:'None'},
            ...selectors.filter(x=>x.id!==first)]}/>
        {second&&<Field title="Secondary values" value={secondValues}
          onChange={v=>{setSecondValues(v);setEstimate(null)}}/>}
      </div>
      <Field title="Metric name (optional)" value={metric}
        onChange={v=>{setMetric(v);setEstimate(null)}}/>
      <button disabled={busy||!first} onClick={()=>void preview()}>
        <Gauge size={14}/> Validate complete experiment grid</button>
      {estimate&&<div className="rw-insight">
        <strong>{estimate.run_count} model executions</strong> ·
        relative work units: {format(estimate.estimated_relative_work_units)}
        <p>{estimate.calibration}</p>
        <button className="rw-primary" disabled={busy} onClick={()=>void run()}>
          <Play size={14}/> Confirm and run complete grid</button></div>}
      <p className="rw-caution">Grid studies are exploratory. Selection after viewing outcomes requires separately frozen later testing.</p>
    </section>
    <section className="rw-box">
      <header className="rw-box-head"><h3>Experiment design</h3></header>
      <p>Select one or two model parameters, provide explicit values and inspect computational scope before starting. Up to 36 combinations are permitted per job.</p>
      <p>Each configuration calls the same Python engine as Model Laboratory and saves independent run data and the grid response. Partial fake outputs are not generated.</p>
      <p>For a true out-of-sample comparison, freeze parameters before starting the chronological evaluation rather than treating an in-sample optimized grid as predictive evidence.</p>
    </section>
  </div>
}
function Optimization({runs,onError}:Props){
  const candidates=runs.filter(r=>r.kind==='model_run')
  const [selected,setSelected]=useState<string[]>([])
  const [details,setDetails]=useState<ModelResult[]>([])
  const [busy,setBusy]=useState(false)
  const toggle=(id:string)=>setSelected(old=>old.includes(id)?old.filter(x=>x!==id):old.length<6?[...old,id]:old)
  const analyze=async()=>{
    setBusy(true)
    try{
      const arr=await Promise.all(selected.map(id=>call<ModelResult>('lab/runs/'+id)))
      setDetails(arr)
    }catch(e){onError(e instanceof Error?e.message:String(e))}
    finally{setBusy(false)}
  }
  const metricNames=useMemo(()=>[...new Set(details.flatMap(x=>x.metrics.map(m=>m.label)))], [details])
  return <div className="rw-stack">
    <section className="rw-box">
      <header className="rw-box-head"><h3>Optimization and model diagnostics comparison</h3></header>
      <p className="rw-help">Choose up to six saved model runs. Exact reported metrics are aligned by name and units; missing values remain missing instead of fabricated zeros.</p>
      <div className="ra-column-picker">{candidates.map(x=><label key={x.id}>
        <input type="checkbox" checked={selected.includes(x.id)}
          onChange={()=>toggle(x.id)}/>{x.label}</label>)}</div>
      <button className="rw-primary" disabled={busy||!selected.length} onClick={()=>void analyze()}>
        <BarChart3 size={14}/> Compare archived metric tables</button>
    </section>
    {!!details.length&&<section className="rw-box">
      <header className="rw-box-head"><h3>Observed or modeled outcomes</h3></header>
      <div className="rw-scroll"><table><thead><tr><th>Metric / units</th>{details.map((x,i)=>
        <th key={i}>{x.title}</th>)}</tr></thead><tbody>
          {metricNames.map(metric=><tr key={metric}><td>{metric}</td>
            {details.map((x,i)=>{const m=x.metrics.find(z=>z.label===metric)
              return <td key={i}>{m?formatMetric(m.label,m.value,m.unit).value+
                ' · '+formatMetric(m.label,m.value,m.unit).unit:'Not available'}</td>})}</tr>)}
        </tbody></table></div>
      <div className="rw-grid-plots">{details.flatMap((x,i)=>x.plots.slice(0,1)
        .map((plot,j)=><ResearchPlot key={i+'-'+j} plot={plot}/>))}</div>
      <p className="rw-caution">Different units, frequencies, sample vintages and theoretical assumptions make cross-model rankings potentially invalid. Inspect each saved run's source checksum and conditions.</p>
    </section>}
  </div>
}
export default function ResearchGuided(props:Props){
  const [tab,setTab]=useState<'guided'|'grid'|'optimization'>('guided')
  return <div className="rw-stack">
    <div className="rw-segments">
      <button className={tab==='guided'?'active':''} onClick={()=>setTab('guided')}>
        <BookOpen size={14}/> Guided research</button>
      <button className={tab==='grid'?'active':''} onClick={()=>setTab('grid')}>
        <SlidersHorizontal size={14}/> Multi-parameter grids</button>
      <button className={tab==='optimization'?'active':''} onClick={()=>setTab('optimization')}>
        <ShieldCheck size={14}/> Optimization dashboard</button>
    </div>
    {tab==='guided'?<Guided {...props}/>:tab==='grid'?<Grid {...props}/>:<Optimization {...props}/>}
  </div>
}

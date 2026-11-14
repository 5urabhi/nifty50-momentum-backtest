import {useEffect,useState} from 'react'
import {ArrowRight,BookOpen,CheckCircle2,Database,Download,FlaskConical,
  LoaderCircle,Save,ShieldAlert,ShieldCheck} from 'lucide-react'
import ModelLaboratory from './ModelLaboratory'
import ResultsStudio from './ResultsStudio'
import './research-journey.css'

type Datum={id:string;label:string;has_prices:boolean;ready:boolean;kind?:string;
  missing?:string[];basis?:string;source_interval_minutes?:number|null}
type Catalog={id:string;group:string;title:string;mode:string;description:string;
  min_observations:number;status:string}
type Stage=0|1|2|3|4
type Props={datasets:Datum[];selectedDataset:string;onSelectDataset:(id:string)=>void;
  onDataChanged:()=>void;onOpenData:()=>void;onOpenDhan:()=>void;
  onOpenWorkspace:()=>void;onOpenGuide:()=>void;onOpenExperiments:()=>void;
  onOpenModels:()=>void;onOpenResults:()=>void}
const STAGES=[
  {title:'Select data',caption:'Observed, theoretical, or demo'},
  {title:'Choose model',caption:'Registered math and evidence'},
  {title:'Run',caption:'Exact validated inputs'},
  {title:'Analyze',caption:'Saved numbers, plots, audits'},
  {title:'Save',caption:'Reusable note and evidence bundle'},
] as const
type State={stage:Stage;modelId:string;runId:string}
function saved():State{
  try{
    const value=JSON.parse(window.localStorage.getItem('ql-research-journey-v1')||'{}') as Partial<State>
    return {stage:Number.isInteger(value.stage)&&Number(value.stage)>=0&&Number(value.stage)<=4?
      value.stage as Stage:0,
      modelId:typeof value.modelId==='string'?value.modelId:'',
      runId:typeof value.runId==='string'?value.runId:''}
  }catch{return {stage:0,modelId:'',runId:''}}
}
async function responseText(r:Response){
  try{const obj=await r.json() as {detail?:string}
    if(typeof obj.detail==='string')return obj.detail}catch{}
  return 'Research engine HTTP '+r.status
}
export default function ResearchJourney({datasets,selectedDataset,onSelectDataset,onDataChanged,
  onOpenData,onOpenDhan,onOpenWorkspace,onOpenGuide,onOpenExperiments,onOpenModels,
  onOpenResults}:Props){
  const [state,setState]=useState<State>(saved)
  const [catalog,setCatalog]=useState<Catalog[]>([])
  const [loading,setLoading]=useState(true)
  const [error,setError]=useState('')
  const [filter,setFilter]=useState('')
  const [modelType,setModelType]=useState('all')
  const [note,setNote]=useState('')
  const [noteTitle,setNoteTitle]=useState('Research interpretation')
  const [saving,setSaving]=useState(false)
  const [savedNote,setSavedNote]=useState<string|null>(null)
  const dataset=datasets.find(d=>d.id===selectedDataset)
  const choice=catalog.find(m=>m.id===state.modelId)
  useEffect(()=>{
    try{window.localStorage.setItem('ql-research-journey-v1',JSON.stringify(state))}catch{}
  },[state])
  useEffect(()=>{
    let alive=true
    void fetch('/api/lab/catalog').then(async response=>{
      if(!response.ok)throw new Error(await responseText(response))
      const data=await response.json() as {models:Catalog[]}
      if(alive)setCatalog(data.models)
    }).catch(e=>{if(alive)setError(e instanceof Error?e.message:String(e))})
      .finally(()=>{if(alive)setLoading(false)})
    return()=>{alive=false}
  },[])
  useEffect(()=>{
    if(!state.runId||state.stage<3)return
    let alive=true
    void fetch('/api/lab/runs/'+encodeURIComponent(state.runId)).then(async r=>{
      if(!r.ok)throw new Error(await responseText(r))
    }).catch(e=>{if(alive)setError('Saved run check: '+(e instanceof Error?e.message:String(e))+
      '. Return to Run to regenerate an archived result if it was deleted.')})
    return()=>{alive=false}
  },[state.runId,state.stage])
  const goto=(stage:Stage)=>{
    if(stage>=2&&!choice)return
    if(stage>=3&&!state.runId)return
    setState(prev=>({...prev,stage}));setError('')
    window.scrollTo({top:0,behavior:'smooth'})
  }
  const chooseModel=(id:string)=>{
    setState(prev=>({stage:1,modelId:id,runId:prev.modelId===id?prev.runId:''}))
    setSavedNote(null);setError('')
  }
  const recordRun=(id:string)=>{
    setState(prev=>({...prev,runId:id,stage:3}))
    setSavedNote(null);setError('')
    onDataChanged()
    window.scrollTo({top:0,behavior:'smooth'})
  }
  const saveNote=async()=>{
    if(!state.runId)return
    setSaving(true);setError('')
    try{
      const r=await fetch('/api/workspace/records',{method:'POST',
        headers:{'Content-Type':'application/json'},credentials:'same-origin',
        body:JSON.stringify({kind:'note',title:noteTitle.trim()||'Research interpretation',
          tags:['guided-research','source-bound'],
          payload:{source_kind:'model_run',source_id:state.runId,
            model_id:state.modelId,dataset_id:dataset?.id||null,
            interpretation:note.trim(),evidence_status:'research_diagnostic_only',
            warning:'Research note is not independent market-data verification.'}})})
      if(!r.ok)throw new Error(await responseText(r))
      const item=await r.json() as {id:string}
      setSavedNote(item.id)
    }catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setSaving(false)}
  }
  const choices=catalog.filter(m=>(modelType==='all'||m.mode===modelType)&&
    (m.title+' '+m.group+' '+m.description).toLowerCase().includes(filter.trim().toLowerCase()))
  return <div className="rj-root">
    <header className="rj-hero">
      <span className="rs-kicker"><FlaskConical size={15}/> ONE GUIDED RESEARCH WORKFLOW</span>
      <h2>From data to research evidence.</h2>
      <p>Follow five steps without learning separate tabs first. Models still use the real
        Python implementation, exact saved source provenance, and the existing
        download/quote recovery system. No placeholders or trading orders.</p>
    </header>
    <nav className="rj-stepper" aria-label="Guided research progress">{STAGES.map((step,i)=>{
      const stage=i as Stage
      const allowed=i<=2?i===2?!!choice:true:!!state.runId
      return <button type="button" key={step.title}
        className={state.stage===i?'active':state.stage>i?'complete':''}
        aria-current={state.stage===i?'step':undefined}
        disabled={!allowed} onClick={()=>goto(stage)}>
        <span>{state.stage>i?<CheckCircle2 size={15}/>:String(i+1)}</span>
        <strong>{step.title}</strong><small>{step.caption}</small></button>
    })}</nav>
    {error&&<div className="rj-error" role="alert"><ShieldAlert size={15}/>{error}</div>}
    {state.stage===0&&<section className="rj-panel" aria-label="Research step 1: Select data">
      <h3>1 · Start with a source</h3>
      <p>Use observed prices, an existing prepared dataset, or proceed with mathematical
        models that do not require market history. A seeded demonstration will always be
        marked as synthetic. The preferred history buffer is +20% beyond the model minimum.</p>
      <label className="rj-field">Available research dataset
        <select value={selectedDataset} onChange={e=>{onSelectDataset(e.target.value);setSavedNote(null)}}>
          <option value="">No dataset · mathematical / theoretical models only</option>
          {datasets.map(d=><option key={d.id} value={d.id}>
            {d.label} · {d.kind==='synthetic'?'SYNTHETIC':d.ready?'prepared':'incomplete'}
          </option>)}
        </select></label>
      {dataset&&<div className="rj-source">
        <span className={dataset.kind==='synthetic'?'rj-tag demo':'rj-tag'}>
          {dataset.kind==='synthetic'?'SYNTHETIC / DEMONSTRATION':
            dataset.ready?'PREPARED / UNVERIFIED':'INCOMPLETE SOURCE'}</span>
        <strong>{dataset.label}</strong>
        <small>{dataset.basis||'No data source notes stored'}</small>
        {!!dataset.missing?.length&&<div className="rj-missing">
          <h4>Specific source requirements</h4>
          {dataset.missing.map((m,i)=><p key={i}><ShieldAlert size={13}/>{m}</p>)}
        </div>}
      </div>}
      <div className="rj-actions">
        <button type="button" onClick={onOpenDhan}><Database size={14}/>
          Download / reuse Dhan candles</button>
        <button type="button" onClick={onOpenData}><Database size={14}/>
          Import or repair data</button>
        <button className="rj-primary" type="button" onClick={()=>goto(1)}>
          Next · Choose a research model <ArrowRight size={14}/></button>
      </div>
      <p className="rj-caution">Dhan OHLCV alone is not official TRI, historical
        index memberships, dividend-adjusted investment returns or publication-dated fundamentals.</p>
    </section>}
    {state.stage===1&&<section className="rj-panel" aria-label="Research step 2: Choose model">
      <h3>2 · Choose a registered model</h3>
      <p>Every registered model declares whether it uses mathematical assumptions, a
        synthetic simulation, historical closes or actual source-dated option quotes.</p>
      <div className="rj-filters">
        <input type="search" aria-label="Search registered models" value={filter}
          placeholder="Search model, name or algorithm" onChange={e=>setFilter(e.target.value)}/>
        <select aria-label="Filter models by evidence type" value={modelType}
          onChange={e=>setModelType(e.target.value)}>
          <option value="all">All model types</option>
          <option value="historical">Historical data required</option>
          <option value="market">Original option quote required</option>
          <option value="theoretical">Theoretical mathematics</option>
          <option value="synthetic">Seeded simulation</option>
        </select>
      </div>
      {loading&&<p role="status"><LoaderCircle size={14}/> Loading Python model catalog…</p>}
      <div className="rj-model-grid">{choices.map(m=><button type="button" key={m.id}
        className={state.modelId===m.id?'selected':''} onClick={()=>chooseModel(m.id)}>
        <span className="rj-tag">{m.mode.toUpperCase()}</span><strong>{m.title}</strong>
        <small>{m.group} · {m.min_observations>0?m.min_observations+' minimum observations':
          'No market observations needed'}</small><p>{m.description}</p>
      </button>)}</div>
      {!choices.length&&!loading&&<p>No models match your search. Clear the filter to see the registered catalog.</p>}
      <div className="rj-actions"><button type="button" onClick={()=>goto(0)}>
        Back to data</button><button className="rj-primary" type="button" disabled={!choice}
        onClick={()=>goto(2)}>Configure and run {choice?.title||'model'} <ArrowRight size={14}/></button></div>
    </section>}
    {state.stage===2&&<section className="rj-model-stage" aria-label="Research step 3: Run model">
      <div className="rj-panel"><h3>3 · Run the actual Python model</h3>
        <p>Below is the canonical Model Laboratory. It checks exact instrument availability,
          +20% source buffers, parameter bounds and optional quoted inputs. Use its
          recovery buttons if anything is missing. A successful saved run automatically
          opens the analysis step.</p>
        <div className="rj-actions"><button type="button" onClick={()=>goto(1)}>
          Change model</button><button type="button" onClick={onOpenGuide}>
          <BookOpen size={14}/> Explain mathematics</button></div></div>
      <ModelLaboratory section={choice?.group==='Portfolio Optimization'?'models':'mathematics'}
        preferredModelId={state.modelId} datasets={datasets} selectedDataset={selectedDataset}
        onSelectDataset={onSelectDataset} onOpenGuide={onOpenGuide}
        onDataChanged={onDataChanged} onOpenWorkspace={onOpenWorkspace}
        onOpenData={onOpenData} onRunSaved={recordRun}/>
    </section>}
    {state.stage===3&&state.runId&&<section aria-label="Research step 4: Analyze saved run">
      <div className="rj-panel"><h3>4 · Analyze saved results</h3>
        <p>The real Results Studio below uses the selected archived run's numerical
          output. Inspect Sharpe or other available metrics, diagnostics, evidence
          checks, interactive graphs, comparison and the research assistant.</p>
        <div className="rj-actions">
          <button type="button" onClick={()=>goto(2)}>Back to model settings</button>
          <button type="button" className="rj-primary" onClick={()=>goto(4)}>
            Next · Save and export evidence <ArrowRight size={14}/></button>
          <button type="button" onClick={onOpenResults}>
            Open full Results Studio <ArrowRight size={14}/></button>
        </div></div>
      <ResultsStudio selectedIndexRunId="" selectedModelRunId={state.runId}
        onSelectIndexRun={()=>{}} onModels={onOpenModels} onExperiments={onOpenExperiments}
        onWorkspace={onOpenWorkspace} onData={onOpenData} onReports={onOpenWorkspace}/>
    </section>}
    {state.stage===4&&state.runId&&<section className="rj-panel" aria-label="Research step 5: Save evidence">
      <span className="rs-kicker"><ShieldCheck size={15}/> ARCHIVED PYTHON CALCULATION</span>
      <h3>5 · Save an interpretation and reproducible evidence</h3>
      <p>The numerical model run is <strong>already saved</strong> by Python; you do not need to
        rerun it. Attach a human interpretation or export a source-hash-checked
        evidence bundle. External source data must be supplied by an authorized user
        for a full independent reproduction.</p>
      <dl className="rj-summary"><div><dt>Selected model</dt><dd>{choice?.title||state.modelId}</dd></div>
        <div><dt>Archived run ID</dt><dd>{state.runId}</dd></div>
        <div><dt>Source dataset</dt><dd>{dataset?.label||'Mathematical assumptions only'}</dd></div>
      </dl>
      <label className="rj-field">Research note title<input value={noteTitle} maxLength={120}
        onChange={e=>setNoteTitle(e.target.value)}/></label>
      <label className="rj-field">What did the saved evidence establish?
        <textarea rows={5} value={note} maxLength={5000}
          placeholder="Interpret the actual saved metrics and limitations. Avoid claiming independently certified alpha."
          onChange={e=>setNote(e.target.value)}/>
      </label>
      {savedNote&&<p className="rj-saved" role="status">
        <CheckCircle2 size={15}/> Research note saved as {savedNote}.</p>}
      <div className="rj-actions">
        <button type="button" disabled={saving||!note.trim()} onClick={()=>void saveNote()}>
          {saving?<LoaderCircle size={14}/>:<Save size={14}/>} Save interpretation to library</button>
        <a className="rj-primary" download
          href={'/api/workspace/evidence-bundles/model_run/'+encodeURIComponent(state.runId)+'.zip'}>
          <Download size={15}/> Export research evidence ZIP</a>
        <button type="button" onClick={onOpenWorkspace}>Open notebooks and reports</button>
        <button type="button" onClick={()=>goto(3)}>Review analysis again</button>
      </div>
      <p className="rj-caution">No trading execution. SHA-256 checksums verify local
        integrity of archived files—not accuracy of the original vendor or independent
        verification of historical performance.</p>
      <button type="button" className="rj-restart" onClick={()=>{
        setState({stage:0,modelId:'',runId:''});setSavedNote(null);setNote('');setError('')
      }}>Start a different research study <ArrowRight size={14}/></button>
    </section>}
    <footer className="rj-footer">QUANTLAB · LOCAL RESEARCH · SOURCE CLAIMS REQUIRE AUDIT</footer>
  </div>
}

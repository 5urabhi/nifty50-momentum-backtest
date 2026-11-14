import {useCallback,useEffect,useMemo,useRef,useState} from 'react'
import {Archive,ArrowDownToLine,ArrowLeft,ArrowRight,BarChart3,BookOpen,Check,
  CheckCircle2,Copy,Database,Download,FileText,Folder,Heart,
  History,Layers3,LoaderCircle,Plus,RefreshCw,RotateCcw,Save,Search,
  Settings2,ShieldCheck,SlidersHorizontal,Trash2,Undo2,Upload,Workflow,X} from 'lucide-react'
import ResearchPlot,{type ResearchPlotData} from './ResearchPlots'
import ResearchAdvanced from './ResearchAdvanced'
import ResearchGuided from './ResearchGuided'
import ResearchCompletion from './ResearchCompletion'
import ResearchScholar from './ResearchScholar'
import './research-workspace.css'

type Raw = Record<string,unknown>
type Page='home'|'library'|'compare'|'plots'|'guided'|'scholar'|'projects'|'automation'|'quality'|'integrity'|'jobs'
type RecordKind='configuration'|'project'|'notebook'|'chart'|'comparison'|'dashboard'|'note'|'report'|'study'
type ResourceKind='dataset'|'model_run'|'research_run'
type Item={id:string;kind:RecordKind;title:string;payload:Raw;tags:string[];
  favorite:boolean;archived:boolean;trashed:boolean;updated_utc:string;created_utc:string}
type Resource={id:string;kind:ResourceKind;title:string;summary:string;tags?:string[];favorite?:boolean;
  protected:boolean;archived:boolean;trashed:boolean}
type Datum={id:string;label:string;has_prices:boolean;ready:boolean}
type ModelRun={id:string;model_id:string;title:string;group:string;mode:string;
  dataset_id?:string|null;figures:number;generated_utc?:string}
type IndexRun={id:string;name:string;dataset_id?:string;created_utc?:string}
type RunOption={key:string;kind:'model_run'|'research_run';id:string;label:string;model?:string;figures:number}
type Job={id:string;kind:string;status:string;result?:Raw;error?:string;
  created_utc?:string;stage?:string;percent?:number;cancellable?:boolean}
type ModelSpec={id:string;title:string;group:string;mode:string;parameters:{
  key:string;default:number|string;type:string;min?:number;max?:number}[]}
type NotebookCell={id:string;type:'markdown'|'run'|'chart'|'table';content?:string;run_id?:string;chart_id?:string;previous_run_ids?:string[]}
type Props={datasets:Datum[];selectedDataset:string;onSelectDataset:(id:string)=>void;
  onOpenDhan:()=>void;onOpenModels:()=>void;onDataChanged:()=>void;initialPage?:Page}
const PAGES:{id:Page;label:string;sub:string}[]=[
  {id:'home',label:'Start',sub:'Resume and guided workflows'},
  {id:'library',label:'Library',sub:'Datasets, models, results'},
  {id:'compare',label:'Compare & Graph',sub:'Saved model overlays'},
  {id:'plots',label:'Plot Builder',sub:'2D / 3D and statistics'},
  {id:'guided',label:'Guided & Grids',sub:'Goals and optimization'},
  {id:'scholar',label:'Index Research Studio',sub:'Explainers, attribution & publishing'},
  {id:'projects',label:'Projects & Notes',sub:'Notebooks and reports'},
  {id:'automation',label:'Research Tools',sub:'Sweeps, validation, shocks'},
  {id:'quality',label:'Data Quality',sub:'Coverage and provenance'},
  {id:'integrity',label:'Evidence & ML',sub:'Vendor validation and learning'},
  {id:'jobs',label:'Jobs',sub:'Runs and downloads'},
]
const fmt=(v:number)=>v.toLocaleString('en-US',{maximumFractionDigits:3})
const errText=async(resp:Response)=>{let detail:unknown
  try{detail=(await resp.json() as {detail?:unknown}).detail}catch{}
  return typeof detail==='string'?detail:'HTTP '+resp.status+' — operation failed'
}
async function api<T>(path:string,body?:object,method='GET'):Promise<T>{
  let resp:Response
  try{resp=await fetch('/api'+path,{method,headers:body?{'Content-Type':'application/json'}:undefined,
    body:body?JSON.stringify(body):undefined,credentials:'same-origin'})}
  catch{throw new Error('Local Python engine unavailable. Start QuantLab with bash run.sh.')}
  if(!resp.ok)throw new Error(await errText(resp))
  return await resp.json() as T
}
const isJobActive=(job:Job|null)=>!!job&&['queued','running'].includes(job.status)
const safeDownload=(name:string,contents:string,mime:string)=>{
  const url=URL.createObjectURL(new Blob([contents],{type:mime}))
  const a=document.createElement('a');a.href=url;a.download=name
  document.body.append(a);a.click();a.remove()
  window.setTimeout(()=>URL.revokeObjectURL(url),1000)
}
function Box({title,children,side}:{title:string;children:React.ReactNode;side?:React.ReactNode}){
  return <section className="rw-box"><header className="rw-box-head"><h3>{title}</h3>{side}</header>{children}</section>
}
function Field({label,value,onChange,placeholder='',type='text'}:{label:string;value:string;
  onChange:(value:string)=>void;placeholder?:string;type?:string}){
  return <label className="rw-field"><span>{label}</span><input type={type} value={value}
    placeholder={placeholder} onChange={e=>onChange(e.target.value)}/></label>
}
function Select({label,value,options,onChange}:{label:string;value:string;
  options:{value:string;label:string}[];onChange:(value:string)=>void}){
  return <label className="rw-field"><span>{label}</span><select value={value}
    onChange={e=>onChange(e.target.value)}>{options.map(x=><option key={x.value}
    value={x.value}>{x.label}</option>)}</select></label>
}
function Empty({title,children}:{title:string;children?:React.ReactNode}){
  return <div className="rw-empty"><Layers3 size={25}/><strong>{title}</strong>
    <span>{children}</span></div>
}
function loadDraft(key:string,fallback:string){
  try{return window.localStorage.getItem(key)??fallback}catch{return fallback}
}
function NumberStats({data}:{data:{label:string;value:string|number}[]}){
  return <div className="rw-stats">{data.map(d=><div key={d.label}>
    <small>{d.label}</small><strong>{d.value}</strong></div>)}</div>
}
const dataOptions=(datasets:Datum[])=>datasets.filter(d=>d.has_prices)
  .map(d=>({value:d.id,label:d.label}))

export default function ResearchWorkspace({datasets,selectedDataset,onSelectDataset,
  onOpenDhan,onOpenModels,onDataChanged,initialPage='home'}:Props){
  const [page,setPage]=useState<Page>(initialPage)
  const [library,setLibrary]=useState<Item[]>([])
  const [resources,setResources]=useState<Resource[]>([])
  const [models,setModels]=useState<ModelSpec[]>([])
  const [runs,setRuns]=useState<RunOption[]>([])
  const [runOffsets,setRunOffsets]=useState({model:100,index:100})
  const [hasOlderRuns,setHasOlderRuns]=useState({model:false,index:false})
  const pagingTouched=useRef(false)
  const [jobs,setJobs]=useState<Job[]>([])
  const [loading,setLoading]=useState(true)
  const [busy,setBusy]=useState(false)
  const [message,setMessage]=useState<string|null>(null)
  const [error,setError]=useState<string|null>(null)
  const [searchOpen,setSearchOpen]=useState(false)
  const [query,setQuery]=useState('')
  const [matches,setMatches]=useState<{kind:string;id:string;title:string;location:string}[]>([])
  const [theme,setTheme]=useState(loadDraft('ql-rw-theme','dark'))
  const [activeJob,setActiveJob]=useState<Job|null>(null)
  const [savedConfigs,setSavedConfigs]=useState(0)
  const running=useRef(false)
  const reload=useCallback(async()=>{
    if(running.current)return
    running.current=true
    try{
      const [records,trashedRecords,items,saved,index,registry,queue]=await Promise.all([
        api<{records:Item[]}>('/workspace/records?archived=true'),
        api<{records:Item[]}>('/workspace/records?trashed=true'),
        api<{resources:Resource[]}>('/workspace/resources?include_trashed=true'),
        api<{runs:ModelRun[]}>('/lab/runs?limit=100&offset=0'),
        api<{runs:IndexRun[]}>('/runs?limit=100&offset=0'),
        api<{models:ModelSpec[]}>('/lab/catalog'),
        api<{jobs:Job[]}>('/workspace/jobs')])
      setLibrary([...records.records,...trashedRecords.records])
      setResources(items.resources)
      setModels(registry.models)
      const freshest:RunOption[]=[
        ...saved.runs.map(x=>({key:'model_run:'+x.id,kind:'model_run' as const,id:x.id,
            label:x.title+' · '+x.id.slice(0,8),model:x.model_id,figures:x.figures})),
        ...index.runs.map(x=>({key:'research_run:'+x.id,kind:'research_run' as const,
            id:x.id,label:x.name+' · '+x.id.slice(0,8),figures:1}))]
      setRuns(existing=>{
        if(!pagingTouched.current)return freshest
        const ids=new Set(freshest.map(r=>r.key))
        return [...freshest,...existing.filter(item=>!ids.has(item.key))]
      })
      if(!pagingTouched.current){
        setRunOffsets({model:100,index:100})
        setHasOlderRuns({model:saved.runs.length===100,index:index.runs.length===100})
      }
      setSavedConfigs(records.records.filter(x=>x.kind==='configuration'&&!x.trashed).length)
      setJobs(queue.jobs)
    }catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{running.current=false;setLoading(false)}
  },[])
  useEffect(()=>{void reload()},[reload])
  useEffect(()=>{
    if(page!=='jobs'&&!isJobActive(activeJob))return
    const timer=window.setInterval(()=>{
      void api<{jobs:Job[]}>('/workspace/jobs').then(data=>{
        setJobs(data.jobs)
        if(activeJob){
          const next=data.jobs.find(j=>j.id===activeJob.id)
          if(next&&next.status!==activeJob.status){
            setActiveJob(next)
            if(next.status==='complete'){setMessage('Research job completed. Outputs are ready for review.');void reload()}
            if(next.status==='error')setError(next.error||'Research job failed')
          }
        }
      }).catch(()=>{})
    },1600)
    return()=>window.clearInterval(timer)
  },[page,activeJob,reload])
  useEffect(()=>{window.localStorage.setItem('ql-rw-theme',theme)},[theme])
  useEffect(()=>{
    const key=(e:KeyboardEvent)=>{
      if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){
        e.preventDefault();setSearchOpen(v=>!v)
      }
      if(e.key==='Escape')setSearchOpen(false)
    }
    window.addEventListener('keydown',key)
    return()=>window.removeEventListener('keydown',key)
  },[])
  useEffect(()=>{
    if(!query.trim()){setMatches([]);return}
    let alive=true
    const timer=window.setTimeout(()=>{
      void api<{results:typeof matches}>('/workspace/search?q='+encodeURIComponent(query))
        .then(r=>{if(alive)setMatches(r.results)})
        .catch(()=>{if(alive)setMatches([])})
    },250)
    return()=>{alive=false;window.clearTimeout(timer)}
  },[query])
  const loadOlderRuns=async()=>{
    pagingTouched.current=true
    setBusy(true)
    setError(null)
    try{
      const [modelPage,indexPage]=await Promise.all([
        hasOlderRuns.model?api<{runs:ModelRun[]}>(
          '/lab/runs?limit=100&offset='+runOffsets.model):Promise.resolve({runs:[] as ModelRun[]}),
        hasOlderRuns.index?api<{runs:IndexRun[]}>(
          '/runs?limit=100&offset='+runOffsets.index):Promise.resolve({runs:[] as IndexRun[]}),
      ])
      const loaded:RunOption[]=[
        ...modelPage.runs.map(x=>({key:'model_run:'+x.id,kind:'model_run' as const,id:x.id,
          label:x.title+' · '+x.id.slice(0,8),model:x.model_id,figures:x.figures})),
        ...indexPage.runs.map(x=>({key:'research_run:'+x.id,kind:'research_run' as const,
          id:x.id,label:x.name+' · '+x.id.slice(0,8),figures:1})),
      ]
      setRuns(current=>{
        const existing=new Set(current.map(x=>x.key))
        return [...current,...loaded.filter(x=>!existing.has(x.key))]
      })
      setRunOffsets(old=>({model:old.model+modelPage.runs.length,
                           index:old.index+indexPage.runs.length}))
      setHasOlderRuns({model:hasOlderRuns.model&&modelPage.runs.length===100,
                       index:hasOlderRuns.index&&indexPage.runs.length===100})
      setMessage(loaded.length+' older archived experiments are available for comparison')
    }catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setBusy(false)}
  }
  const perform=async<T,>(action:()=>Promise<T>,then?:(value:T)=>void)=>{
    setBusy(true);setError(null)
    try{const result=await action();then?.(result);await reload()}
    catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setBusy(false)}
  }
  const openSearch=(x:{kind:string;id:string;location:string})=>{
    setSearchOpen(false);setQuery('')
    if(x.location==='model_catalog'){
      try{window.localStorage.setItem('ql-target-model',x.id)}catch{}
      onOpenModels();return
    }
    if(x.location==='documentation'){
      window.open('/api/guide/'+encodeURIComponent(x.id),'_blank','noopener,noreferrer')
      return
    }
    if(x.location==='resource_library')setPage('library')
    else if(x.kind==='project'||x.kind==='notebook')setPage('projects')
    else if(x.kind==='chart'||x.kind==='comparison')setPage('compare')
    else setPage('library')
    setMessage('Found '+x.id+'. Select it in this workspace.')
  }
  const start=(job:{job_id:string;status:string},caption:string)=>{
    setActiveJob({id:job.job_id,kind:caption,status:job.status})
    setPage('jobs');setMessage(caption+' started. Progress is tracked here.')
  }
  const notice=<>{message&&<div className="rw-notice" role="status"><CheckCircle2 size={16}/>{message}
    <button onClick={()=>setMessage(null)} aria-label="Dismiss success"><X size={14}/></button></div>}
    {error&&<div className="rw-notice error" role="alert"><X size={16}/>{error}
      <button onClick={()=>setError(null)} aria-label="Dismiss error"><X size={14}/></button></div>}</>
  return <div className={'rw-root '+(theme==='light'?'rw-theme-light':'')}>
    <div className="rw-top"><div><small>QUANTLAB / RESEARCH DESK</small>
      <h2>Research Workspace</h2><p>One library for data, experiments, models, figures and reproducible reports.</p>
    </div><div className="rw-top-actions"><button onClick={()=>setSearchOpen(true)}
      aria-label="Search research workspace"><Search size={15}/> Search <kbd>Ctrl K</kbd></button>
      <button onClick={()=>setTheme(v=>v==='dark'?'light':'dark')}><Settings2 size={15}/>
        {theme==='dark'?'Light':'Dark'} theme</button>
      <button onClick={()=>void reload()} aria-label="Refresh workspace"><RefreshCw size={15}/></button>
    </div></div>
    <div className="rw-navigation" role="tablist" aria-label="Research workspaces">
      {PAGES.map(item=><button role="tab" key={item.id} type="button"
        aria-selected={page===item.id} className={page===item.id?'active':''}
        onClick={()=>setPage(item.id)}>{item.label}<small>{item.sub}</small></button>)}
    </div>{notice}
    {loading?<div className="rw-working"><LoaderCircle className="ql-spinning"/> Loading research library…</div>:null}
    {page==='home'&&<div className="rw-stack"><div className="rw-two">
      <Box title="Resume research">
        <div className="rw-button-group">
          <button className="rw-primary" onClick={()=>setPage('guided')}>
            <BookOpen size={15}/> Start a guided research workflow</button>
          <button onClick={()=>setPage('plots')}><BarChart3 size={15}/> Build a graph</button>
        </div>
        <NumberStats data={[
          {label:'Saved model results',value:runs.filter(x=>x.kind==='model_run').length},
          {label:'Research projects',value:library.filter(x=>x.kind==='project'&&!x.trashed).length},
          {label:'Saved configurations',value:savedConfigs},
          {label:'Observed datasets',value:datasets.filter(x=>x.has_prices).length},
        ]}/>
        <div className="rw-intro-steps">
          <button onClick={onOpenDhan}><Database size={20}/><strong>1 · Get data</strong><small>Inspect, extend and reuse local Dhan data.</small><ArrowRight size={15}/></button>
          <button onClick={onOpenModels}><SlidersHorizontal size={20}/><strong>2 · Choose a model</strong><small>Run mathematical, stochastic and portfolio models.</small><ArrowRight size={15}/></button>
          <button onClick={()=>setPage('compare')}><BarChart3 size={20}/><strong>3 · Compare evidence</strong><small>Overlay compatible saved outputs and export graphs.</small><ArrowRight size={15}/></button>
          <button onClick={()=>setPage('scholar')}><ShieldCheck size={20}/><strong>4 · Explain the research</strong><small>Inspect every index decision, factor-risk prerequisite and evidence limitation.</small><ArrowRight size={15}/></button>
          <button onClick={()=>setPage('projects')}><BookOpen size={20}/><strong>5 · Publish findings</strong><small>Store notes and create a reproducible report.</small><ArrowRight size={15}/></button>
        </div>
      </Box>
      <Box title="Recently saved work" side={<button className="rw-link" onClick={()=>setPage('library')}>View library <ArrowRight size={14}/></button>}>
        {library.slice(0,7).map(item=><button className="rw-row" key={item.id}
          onClick={()=>setPage(item.kind==='project'||item.kind==='notebook'?'projects':'library')}>
          <span><strong>{item.title}</strong><small>{item.kind} · {item.updated_utc.slice(0,16).replace('T',' ')}</small></span>
          {item.favorite&&<Heart size={13}/>}</button>)}
        {!library.length&&<Empty title="No saved work yet">Run a model, then save its configuration, comparison or notes.</Empty>}
        <div className="rw-insight">Research guardrails: synthetic demonstrations, in-sample fitted values and genuinely later holdout outcomes are never treated as equivalent evidence.</div>
      </Box>
    </div>
    <DashboardPanel runs={runs} records={library} busy={busy}
      perform={perform} onMessage={setMessage} onCompare={()=>setPage('compare')}/>
    <SettingsTransfer onMessage={setMessage}/>
    </div>}
    {page==='library'&&<LibraryPanel items={library} resources={resources} busy={busy}
      perform={perform} onChanged={onDataChanged} onOpenModels={onOpenModels}
      onOpenDhan={onOpenDhan} onMessage={setMessage}/>}
    {page==='compare'&&<><ComparePanel runs={runs} items={library} busy={busy}
      perform={perform} onMessage={setMessage}/>
      {(hasOlderRuns.model||hasOlderRuns.index)&&<div className="rw-pagination">
        <p className="rw-help">More older saved model/index runs are available. Archived history is paged instead of silently truncated.</p>
        <button disabled={busy} onClick={()=>void loadOlderRuns()}>
          <History size={14}/> Load 100 more saved runs per research family</button>
      </div>}</>}
    {page==='plots'&&<ResearchAdvanced datasets={datasets} selectedDataset={selectedDataset}
      onSelectDataset={onSelectDataset} records={library} onMessage={setMessage}
      onError={setError} onChanged={()=>void reload()}/>}
    {page==='guided'&&<ResearchGuided models={models} datasets={datasets}
      selectedDataset={selectedDataset} onSelectDataset={onSelectDataset}
      onOpenModels={onOpenModels} onOpenDhan={onOpenDhan} runs={runs}
      onStartJob={start} onMessage={setMessage} onError={setError}
      onDataChanged={()=>{void reload();onDataChanged()}}/>}
    {page==='scholar'&&<ResearchScholar datasets={datasets}
      selectedDataset={selectedDataset} onSelectDataset={onSelectDataset}
      runs={runs} onStartJob={start}/>}
    {page==='projects'&&<ProjectsPanel records={library} runs={runs} busy={busy}
      perform={perform} onMessage={setMessage} startJob={start}
      onOpenCompare={()=>setPage('compare')}/>}
    {page==='automation'&&<AutomationPanel datasets={datasets} selectedDataset={selectedDataset}
      onSelectDataset={onSelectDataset} models={models} runs={runs} busy={busy}
      perform={perform} startJob={start}/>}
    {page==='quality'&&<QualityPanel datasets={datasets} selectedDataset={selectedDataset}
      onSelectDataset={onSelectDataset} onOpenDhan={onOpenDhan}
      onOpenLibrary={()=>setPage('library')}/>}
    {page==='integrity'&&<ResearchCompletion datasets={datasets}
      selectedDataset={selectedDataset} onSelectDataset={onSelectDataset}
      records={library} onOpenDhan={onOpenDhan} onStartJob={start}
      onChanged={()=>void reload()}/>}
    {page==='jobs'&&<JobsPanel jobs={jobs} busy={busy} perform={perform} onPage={setPage}/>}
    {searchOpen&&<div className="rw-modal-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)setSearchOpen(false)}}>
      <div className="rw-search-dialog" role="dialog" aria-modal="true" aria-label="Search QuantLab research library">
        <div><Search size={20}/><input autoFocus value={query} onChange={e=>setQuery(e.target.value)}
          placeholder="Find datasets, saved results, projects, notes, charts…"/>
          <button onClick={()=>setSearchOpen(false)} aria-label="Close"><X size={17}/></button></div>
        {matches.slice(0,15).map(x=><button key={x.kind+x.id} onClick={()=>openSearch(x)}>
          <strong>{x.title}</strong><small>{x.kind}</small></button>)}
        {!matches.length&&<p>Start typing to search the local research library.</p>}
      </div>
    </div>}
  </div>
}

function LibraryPanel({items,resources,busy,perform,onChanged,onOpenModels,onOpenDhan,onMessage}:{
  items:Item[];resources:Resource[];busy:boolean;
  perform:<T,>(action:()=>Promise<T>,done?:(result:T)=>void)=>Promise<void>;
  onChanged:()=>void;onOpenModels:()=>void;onOpenDhan:()=>void;
  onMessage:(s:string)=>void
}){
  const [mode,setMode]=useState<'resources'|'saved'|'trash'>('resources')
  const [filter,setFilter]=useState('all')
  const [search,setSearch]=useState('')
  const [selected,setSelected]=useState<string[]>([])
  const [showArchived,setShowArchived]=useState(false)
  const [detail,setDetail]=useState<Item|Resource|null>(null)
  const [newTitle,setNewTitle]=useState('')
  const [newTags,setNewTags]=useState('')
  const [newDescription,setNewDescription]=useState('')
  const visibleResources=resources.filter(x=>(filter==='all'||x.kind===filter)&&
    (mode==='trash'?x.trashed:!x.trashed)&&(showArchived||mode==='trash'||!x.archived)&&
    (x.title+' '+x.summary+' '+(x.tags||[]).join(' ')).toLowerCase().includes(search.toLowerCase()))
  const visibleRecords=items.filter(x=>(filter==='all'||x.kind===filter)&&
    (mode==='trash'?x.trashed:!x.trashed)&&
    (showArchived||mode==='trash'||!x.archived)&&
    (x.title+' '+x.tags.join(' ')).toLowerCase().includes(search.toLowerCase()))
  const resourceOperation=(resource:Resource,operation:string)=>{
    if(operation==='purge'&&!window.confirm('Permanently delete this resource from Trash? This cannot be undone.'))return
    if(operation==='trash'&&!window.confirm('Move '+resource.title+' to recoverable Trash? Shared raw market history will remain untouched.'))return
    perform(()=>api<Raw>('/workspace/resources/action',{kind:resource.kind,item_id:resource.id,
      action:operation,confirm:operation==='trash'||operation==='purge'},'POST'),()=>{
        onChanged();onMessage(operation+' completed for '+resource.title);setDetail(null)})
  }
  const recordOperation=(item:Item,operation:string)=>{
    if(operation==='purge'&&!window.confirm('Permanently delete this trashed record?'))return
    perform(()=>api<Raw>('/workspace/records/'+item.id+'/action',
      {action:operation,confirm:operation==='purge'},'POST'),()=>{
      onMessage(operation+' completed');setDetail(null)})
  }
  const batch=(action:string)=>{
    if(action==='trash'&&!window.confirm('Move '+selected.length+' items to Trash?'))return
    perform(()=>api<Raw>('/workspace/batch',{ids:selected,action},'POST'),
      ()=>{setSelected([]);onMessage(selected.length+' items updated')})
  }
  return <div className="rw-stack">
    <Box title="Manage datasets, results and saved artifacts" side={<div className="rw-button-group">
      <button onClick={onOpenDhan}><Database size={14}/> Dhan data</button>
      <button onClick={onOpenModels}><Plus size={14}/> Run model</button></div>}>
      <div className="rw-toolbar">
        <div className="rw-segments">{(['resources','saved','trash'] as const).map(v=>
          <button key={v} className={mode===v?'active':''} onClick={()=>{setMode(v);setFilter('all');setDetail(null);setSelected([])}}>
            {v==='resources'?'Datasets & results':v==='saved'?'Saved work':'Trash'}</button>)}</div>
        <input className="rw-search-field" value={search} onChange={e=>setSearch(e.target.value)} placeholder="Filter by name or tag"/>
        <select value={filter} onChange={e=>setFilter(e.target.value)}>
          <option value="all">All kinds</option>
          {(mode==='resources'?['dataset','model_run','research_run']:
            mode==='trash'?['dataset','model_run','research_run','configuration','chart',
              'comparison','project','notebook','report','note','study','dashboard']:
              ['configuration','chart','comparison','project','notebook','report','note','study','dashboard'])
            .map(v=><option key={v} value={v}>{v.replaceAll('_',' ')}</option>)}
        </select>
        <label className="rw-inline"><input type="checkbox" checked={showArchived}
          onChange={e=>setShowArchived(e.target.checked)}/> Show archived</label>
      </div>
      {(mode==='resources'||mode==='trash')&&
        <div className="rw-list">{visibleResources.map(r=><div key={r.kind+r.id} className="rw-list-item">
          <div><strong>{r.title}</strong><small>{r.kind} · {r.id} {r.protected?' · Protected source':''}</small>
            <p>{r.summary.slice(0,180)}</p></div>
          <div className="rw-row-actions">
            <button onClick={()=>{setDetail(r);setNewTitle(r.title);setNewTags((r.tags||[]).join(', '));
              setNewDescription(r.summary)}} aria-label={'Details '+r.title}><BookOpen size={15}/></button>
            {!r.trashed&&<button title="Favorite" disabled={busy} onClick={()=>
              perform(()=>api<Raw>('/workspace/resources/metadata?kind='+r.kind+'&item_id='+encodeURIComponent(r.id),
                {favorite:!r.favorite},'PATCH'),()=>onMessage('Favorite status updated'))}>
              <Heart size={15} fill={r.favorite?'currentColor':'none'}/></button>}
            {r.trashed?<><button title="Restore resource" disabled={busy}
              onClick={()=>resourceOperation(r,'restore')}><RotateCcw size={15}/></button>
              <button title="Permanently delete" disabled={busy}
              onClick={()=>resourceOperation(r,'purge')}><Trash2 size={15}/></button></>:
              <><button title={r.archived?'Unarchive':'Archive'} disabled={busy}
                onClick={()=>resourceOperation(r,r.archived?'unarchive':'archive')}><Archive size={15}/></button>
                {!r.protected&&<button title="Move to Trash" disabled={busy}
                  onClick={()=>resourceOperation(r,'trash')}><Trash2 size={15}/></button>}</>}
          </div></div>)}
          {!visibleResources.length&&<Empty title="No matching resources">Try another filter or include archived items.</Empty>}
        </div>}
      {mode!=='resources'&&<><div className="rw-toolbar">
          {!!selected.length&&<><strong>{selected.length} selected</strong>
            {(['archive','favorite','trash','restore'] as const).filter(v=>mode==='trash'?v==='restore':v!=='restore')
              .map(v=><button key={v} onClick={()=>batch(v)} disabled={busy}>{v}</button>)}</>}
        </div>
        <div className="rw-list">{visibleRecords.map(item=><div className="rw-list-item" key={item.id}>
          <input type="checkbox" checked={selected.includes(item.id)} aria-label={'Select '+item.title}
            onChange={e=>setSelected(s=>e.target.checked?[...s,item.id]:s.filter(v=>v!==item.id))}/>
          <div><strong>{item.title}</strong><small>{item.kind} · {item.updated_utc.slice(0,16)} · {item.tags.join(', ')||'No tags'}</small></div>
          <div className="rw-row-actions">
            <button title="Inspect" onClick={()=>{setDetail(item);setNewTitle(item.title);setNewTags(item.tags.join(', '))}}><BookOpen size={15}/></button>
            {mode==='trash'?<button onClick={()=>recordOperation(item,'restore')}><RotateCcw size={15}/></button>:
            <><button title="Favorite" onClick={()=>recordOperation(item,item.favorite?'unfavorite':'favorite')}>
              <Heart size={15} fill={item.favorite?'currentColor':'none'}/></button>
              <button title="Archive" onClick={()=>recordOperation(item,'archive')}><Archive size={15}/></button>
              <button title="Trash" onClick={()=>recordOperation(item,'trash')}><Trash2 size={15}/></button></>}
          </div></div>)}
          {!visibleRecords.length&&<Empty title="No matching saved items">Save an experiment, model preset, chart or research note first.</Empty>}
        </div></>}
    </Box>
    {detail&&<Box title={'Inspect '+detail.title} side={<button className="rw-link" onClick={()=>setDetail(null)}><X size={15}/> Close</button>}>
      {'payload' in detail?<><div className="rw-form-grid">
        <Field label="Title" value={newTitle} onChange={setNewTitle}/>
        <Field label="Tags (comma-separated)" value={newTags} onChange={setNewTags}/>
        <div className="rw-inline-actions"><button disabled={busy||detail.trashed} onClick={()=>perform(
          ()=>api<Item>('/workspace/records/'+detail.id,{
            title:newTitle,tags:newTags.split(',').map(x=>x.trim()).filter(Boolean)},'PATCH'),
          updated=>{setDetail(updated);onMessage('Title and tags updated')})}>
          <Save size={15}/> Save details</button>
          <button onClick={()=>safeDownload(detail.id+'.json',JSON.stringify(detail,null,2),'application/json')}>
            <Download size={15}/> Export JSON</button>
          {detail.kind!=='report'&&!detail.trashed&&<button disabled={busy}
            onClick={()=>perform(()=>api<Item>('/workspace/records',{
              kind:detail.kind,title:detail.title+' (copy)',payload:detail.payload,tags:detail.tags},'POST'),
              ()=>onMessage('Saved item duplicated'))}><Copy size={15}/> Duplicate</button>}</div></div>
        {detail.kind==='study'&&typeof detail.payload.test_observations==='number'&&
          <a className="rw-download-link" download
             href={'/api/workspace/studies/'+detail.id+'/returns.csv'}>
            <Download size={15}/> Download all holdout returns (CSV)
          </a>}
        <pre className="rw-json">{JSON.stringify(detail.payload,null,2)}</pre></>:
      <><p>Resource identity: {detail.kind}:{detail.id}</p>
        <p>Archive hides the resource without deleting source data. Trash is recoverable and refuses to remove referenced datasets or canonical shared Dhan history.</p>
        <div className="rw-form-grid">
          <Field label="User-visible title" value={newTitle} onChange={setNewTitle}/>
          <Field label="Tags (comma-separated)" value={newTags} onChange={setNewTags}/>
        </div>
        <label className="rw-field"><span>Resource description</span><textarea rows={3}
          value={newDescription} onChange={e=>setNewDescription(e.target.value)}/></label>
        <div className="rw-button-group">
          <button disabled={busy||detail.trashed} onClick={()=>perform(()=>
            api<Raw>('/workspace/resources/metadata?kind='+detail.kind+'&item_id='+encodeURIComponent(detail.id),
             {title:newTitle,description:newDescription,
               tags:newTags.split(',').map(x=>x.trim()).filter(Boolean)},'PATCH'),()=>{
                setDetail(null);onMessage('Resource title, description and tags saved')})}>
            <Save size={15}/> Save metadata</button>
          {detail.kind==='model_run'&&!detail.trashed&&<button disabled={busy} onClick={()=>perform(
            ()=>api<Raw>('/workspace/resources/duplicate-model/'+encodeURIComponent(detail.id),{},'POST'),
            ()=>{setDetail(null);onMessage('Independent saved result copy created')})}>
            <Copy size={15}/> Duplicate saved result</button>}
          <button onClick={()=>perform(()=>api<{dependencies:Raw[]}>(
            '/workspace/resources/dependencies?kind='+detail.kind+'&item_id='+encodeURIComponent(detail.id)),
            x=>onMessage(x.dependencies.length?x.dependencies.length+' saved references found':'No saved library dependencies found'))}>
            <ShieldCheck size={15}/> Check references</button>
        </div></>}
    </Box>}
  </div>
}

function ComparePanel({runs,items,busy,perform,onMessage}:{
  runs:RunOption[];items:Item[];busy:boolean;
  perform:<T,>(action:()=>Promise<T>,done?:(result:T)=>void)=>Promise<void>;
  onMessage:(text:string)=>void
}){
  const [selection,setSelection]=useState<string[]>([])
  const [normalization,setNormalization]=useState('none')
  const [alignment,setAlignment]=useState('intersection')
  const [title,setTitle]=useState(loadDraft('ql-rw-chart-title','Saved model comparison'))
  const [annotation,setAnnotation]=useState(loadDraft('ql-rw-chart-note',''))
  const [plot,setPlot]=useState<ResearchPlotData|null>(null)
  const [panels,setPanels]=useState<ResearchPlotData[]>([])
  const [plotIndices,setPlotIndices]=useState<Record<string,number>>({})
  const [kind,setKind]=useState('line2d')
  const [from,setFrom]=useState('0')
  const [to,setTo]=useState('100')
  const [comparison,setComparison]=useState<Raw|null>(null)
  const [saved,setSaved]=useState('')
  const [savedTemplate,setSavedTemplate]=useState('')
  const [reportNotebook,setReportNotebook]=useState('')
  const [overlay,setOverlay]=useState<'overlay'|'split'>('overlay')
  const history=useRef<{title:string;annotation:string;kind:string}[]>([])
  const redoHistory=useRef<{title:string;annotation:string;kind:string}[]>([])
  useEffect(()=>{window.localStorage.setItem('ql-rw-chart-title',title)},[title])
  useEffect(()=>{window.localStorage.setItem('ql-rw-chart-note',annotation)},[annotation])
  const edit=(next:{title?:string;annotation?:string;kind?:string})=>{
    history.current.push({title,annotation,kind})
    redoHistory.current=[]
    setTitle(next.title??title);setAnnotation(next.annotation??annotation);setKind(next.kind??kind)
  }
  const undo=()=>{
    const last=history.current.pop()
    if(last){redoHistory.current.push({title,annotation,kind})
      setTitle(last.title);setAnnotation(last.annotation);setKind(last.kind)}
  }
  const redo=()=>{
    const next=redoHistory.current.pop()
    if(next){history.current.push({title,annotation,kind})
      setTitle(next.title);setAnnotation(next.annotation);setKind(next.kind)}
  }
  const toggle=(key:string)=>{
    setSelection(s=>s.includes(key)?s.filter(v=>v!==key):s.length>=8?s:[...s,key])
    setPlot(null);setPanels([]);setComparison(null)
  }
  const chosen=selection.map(key=>runs.find(run=>run.key===key)).filter(
    (x):x is RunOption=>!!x)
  const selections=chosen.map(run=>({kind:run.kind,run_id:run.id,plot_index:plotIndices[run.key]||0}))
  const build=()=>perform(()=>api<Raw>('/workspace/compare',{
    title,selections,normalize:normalization,alignment,layout:overlay},'POST'),
    res=>{setPlot((res.plot||null) as ResearchPlotData|null)
      setPanels(Array.isArray(res.plots)?res.plots as ResearchPlotData[]:[])
      setComparison(res)
      onMessage(overlay==='split'?'Saved results shown in independent panels':'Compatible results aligned on one graph')})
  const saveComparison=()=>perform(()=>api<Item>('/workspace/records',{
    kind:'comparison',title,payload:{selections,normalize:normalization,alignment,layout:overlay,
      annotation,created_chart:comparison?.plot||null,plots:comparison?.plots||null},tags:['comparison']},'POST'),
    savedItem=>{setSaved(savedItem.id);onMessage('Comparison workspace saved')})
  const saveChart=()=>perform(()=>api<Item>('/workspace/records',{
    kind:'chart',title,payload:{source_comparison:saved||null,plot:displayPlot,plots:panels,
      annotation,layout:{kind,from,to,overlay}},tags:['chart']},'POST'),
    res=>{setSavedTemplate(res.id);onMessage('Graph layout saved')})
  const attachSavedChart=()=>perform(()=>api<Raw>(
    '/workspace/notebooks/'+encodeURIComponent(reportNotebook)+'/attach',
    {kind:'chart',source_id:savedTemplate},'POST'),
    ()=>onMessage('Chart attached to the selected research notebook; generate the report from Projects & Notes'))
  const loadComparison=(item:Item)=>{
    const configs=item.payload.selections
    if(!Array.isArray(configs))return
    const values=(configs as {kind:string;run_id:string}[]).map(x=>x.kind+':'+x.run_id)
    setSelection(values);setTitle(item.title)
    setPlotIndices(Object.fromEntries((configs as {kind:string;run_id:string;plot_index?:number}[])
      .map(x=>[x.kind+':'+x.run_id,x.plot_index||0])))
    setOverlay(item.payload.layout==='split'?'split':'overlay')
    setNormalization(String(item.payload.normalize||'none'))
    setAlignment(String(item.payload.alignment||'intersection'))
    setAnnotation(String(item.payload.annotation||''));setPlot(null);setPanels([]);setComparison(null)
  }
  const loadChart=(item:Item)=>{
    if(!item.payload.plot&&!item.payload.plots)return
    setPlot(item.payload.plot as ResearchPlotData|null)
    setPanels(Array.isArray(item.payload.plots)?item.payload.plots as ResearchPlotData[]:[])
    setTitle(item.title);setAnnotation(String(item.payload.annotation||''))
    const layout=item.payload.layout as {kind?:string;from?:string;to?:string;overlay?:string}|undefined
    setKind(layout?.kind||'line2d');setFrom(layout?.from||'0');setTo(layout?.to||'100')
    setOverlay(layout?.overlay==='split'?'split':'overlay')
  }
  const displayPlot=useMemo(()=>{
    if(!plot)return null
    if(plot.kind==='surface3d'||plot.kind==='heatmap2d')
      return {...plot,title}
    const size=plot.x?.length||0
    const start=Math.min(100,Math.max(0,Number(from)||0))
    const finish=Math.min(100,Math.max(start+1,Number(to)||100))
    const lo=Math.max(0,Math.floor(size*start/100))
    const hi=Math.min(size,Math.max(lo+1,Math.ceil(size*finish/100)))
    const displayKind=plot.kind==='scatter2d'?'scatter2d':
      kind==='bar2d'?'bar2d':'line2d'
    return {...plot,title,kind:displayKind,
      x:plot.x?.slice(lo,hi),y:plot.y?.slice(lo,hi),
      traces:plot.traces?.map(trace=>({...trace,y:trace.y.slice(lo,hi)}))}
  },[plot,title,kind,from,to])
  const exportSVG=()=>{
    const graph=document.querySelector('.rw-graph-preview .ql-svg-chart, .rw-graph-preview .ql-surface svg') as SVGElement|null
    if(!graph){onMessage('SVG export is available for a rendered graph.');return}
    const serialized=new XMLSerializer().serializeToString(graph)
    safeDownload('quantlab_comparison.svg',serialized,'image/svg+xml')
  }
  const exportPNG=()=>{
    const graph=document.querySelector('.rw-graph-preview .ql-svg-chart, .rw-graph-preview .ql-surface svg') as SVGElement|null
    if(!graph)return
    const raw=new XMLSerializer().serializeToString(graph)
    const blob=new Blob([raw],{type:'image/svg+xml;charset=utf-8'})
    const address=URL.createObjectURL(blob)
    const image=new Image()
    image.onload=()=>{
      const canvas=document.createElement('canvas')
      canvas.width=1320;canvas.height=690
      const ctx=canvas.getContext('2d')
      if(ctx){ctx.fillStyle='#0c1b2a';ctx.fillRect(0,0,canvas.width,canvas.height)
        ctx.drawImage(image,0,0,canvas.width,canvas.height)
        canvas.toBlob(result=>{if(!result)return
          const url=URL.createObjectURL(result)
          const a=document.createElement('a');a.href=url;a.download='quantlab_comparison.png'
          document.body.appendChild(a);a.click();a.remove()
          window.setTimeout(()=>URL.revokeObjectURL(url),1000)},'image/png')}
      URL.revokeObjectURL(address)
    }
    image.onerror=()=>URL.revokeObjectURL(address)
    image.src=address
  }
  const exportCSV=()=>{
    if(!displayPlot?.x?.length)return
    const traces=displayPlot.traces||[]
    const escape=(s:unknown)=>'"'+String(s??'').replaceAll('"','""')+'"'
    const lines=[['x',...traces.map(t=>t.name)].map(escape).join(','),
      ...displayPlot.x.map((x,i)=>[x,...traces.map(t=>t.y[i])].map(escape).join(','))]
    safeDownload('quantlab_comparison.csv',lines.join('\n'),'text/csv')
  }
  return <div className="rw-stack">
    <div className="rw-two">
      <Box title="Choose saved model and index results">
        <p className="rw-help">Select 2–8 completed saved runs. QuantLab checks compatible axes and evidence types before overlaying outputs.</p>
        <div className="rw-run-list">{runs.map(r=><label key={r.key} className="rw-check-row">
          <input type="checkbox" checked={selection.includes(r.key)} onChange={()=>toggle(r.key)}/>
          <span><strong>{r.label}</strong><small>{r.kind} · {r.model||'index experiment'}</small></span>
          {selection.includes(r.key)&&r.figures>1&&<select aria-label={'Choose figure for '+r.label}
            value={plotIndices[r.key]||0}
            onChange={e=>{setPlotIndices(p=>({...p,[r.key]:Number(e.target.value)}));setPlot(null);setPanels([])}}>
            {Array.from({length:r.figures},(_,i)=><option key={i} value={i}>Figure {i+1}</option>)}</select>}
        </label>)}
          {!runs.length&&<Empty title="No saved results">First run a mathematical model or index experiment.</Empty>}
        </div>
        <div className="rw-form-grid">
          <Select label="Normalization" value={normalization} onChange={setNormalization}
            options={[{value:'none',label:'Original units'},{value:'base100',label:'Base-100 (positive level series)'},
              {value:'zscore',label:'Z-score (standardized)'}]}/>
          <Select label="Alignment" value={alignment} onChange={setAlignment}
            options={[{value:'intersection',label:'Common X observations only'},{value:'union',label:'Union (missing values stay blank)'}]}/>
        </div>
        <button className="rw-primary" disabled={busy||selection.length<2} onClick={build}>
          <BarChart3 size={15}/> Compare selected runs</button>
      </Box>
      <Box title="Comparison and Graph Studio">
        <Field label="Figure title" value={title} onChange={v=>edit({title:v})}/>
        <Field label="Research annotation" value={annotation}
          onChange={v=>edit({annotation:v})} placeholder="What did this comparison show?"/>
        <div className="rw-form-grid"><Select label="Visualization" value={kind}
          onChange={v=>edit({kind:v})} options={[{value:'line2d',label:'Line / ordered series'},
            {value:'bar2d',label:'Grouped bars'}]}/>
          <Select label="Layout" value={overlay} onChange={v=>{
            setOverlay(v as 'overlay'|'split');setPlot(null);setPanels([]);setComparison(null)}}
            options={[{value:'overlay',label:'Compatible curves on same graph'},
              {value:'split',label:'Independent 2D / 3D figure panels'}]}/></div>
        <div className="rw-form-grid">
          <Field label="Show from (%)" type="number" value={from} onChange={setFrom}/>
          <Field label="Show through (%)" type="number" value={to} onChange={setTo}/>
        </div>
        <div className="rw-button-group">
          <button onClick={undo} disabled={!history.current.length}><Undo2 size={14}/> Undo edit</button>
          <button onClick={redo} disabled={!redoHistory.current.length}><RotateCcw size={14}/> Redo</button>
          <button onClick={saveComparison} disabled={!comparison||busy}><Save size={14}/> Save comparison</button>
          <button onClick={saveChart} disabled={(!displayPlot&&!panels.length)||busy}><Save size={14}/> Save graph</button>
        </div>
        <div className="rw-button-group"><button disabled={!displayPlot} onClick={exportCSV}>
          <Download size={14}/> CSV</button>
          <button disabled={!displayPlot&&!panels.length} onClick={exportSVG}><Download size={14}/> SVG</button>
          <button disabled={!displayPlot&&!panels.length} onClick={exportPNG}><Download size={14}/> PNG</button>
          <button disabled={!displayPlot} onClick={()=>displayPlot&&safeDownload(
            'quantlab_comparison.json',JSON.stringify({plot:displayPlot,annotation},null,2),'application/json')}>
            <Download size={14}/> JSON</button></div>
        {(saved||savedTemplate)&&<p className="rw-success">Saved {savedTemplate||saved} in the research library.</p>}
        {savedTemplate&&<div className="rw-form-grid">
          <Select label="Add saved graph directly to report notebook"
            value={reportNotebook} onChange={setReportNotebook}
            options={[{value:'',label:'Choose a research notebook'},...items
              .filter(x=>x.kind==='notebook'&&!x.trashed)
              .map(x=>({value:x.id,label:x.title}))]}/>
          <div className="rw-inline-actions">
            <button disabled={busy||!reportNotebook} onClick={attachSavedChart}>
              <FileText size={14}/> Add to report notebook</button>
          </div>
        </div>}
      </Box>
    </div>
    {(!!displayPlot||panels.length>0)&&<div className="rw-graph-preview">
      {overlay==='overlay'&&displayPlot?<ResearchPlot plot={displayPlot}/>:
        <div className="rw-grid-plots">{panels.map((p,i)=><ResearchPlot key={i} plot={p}/>)}</div>}
      {annotation&&<p className="rw-note">Research note: {annotation}</p>}
      <p className="rw-caution">These are saved numerical outputs, not proof of independent out-of-sample predictive skill. Rebase and z-score transformations change plotted units.</p>
    </div>}
    <Box title="Restore a saved comparison">
      {items.filter(x=>x.kind==='comparison'&&!x.trashed).map(item=>
        <button className="rw-row" key={item.id} onClick={()=>loadComparison(item)}>
          <span><strong>{item.title}</strong><small>{item.updated_utc.slice(0,16)}</small></span>
          <RotateCcw size={15}/></button>)}
      {!items.some(x=>x.kind==='comparison'&&!x.trashed)&&
        <Empty title="No saved comparison layouts">Build a compatible overlay to save it here.</Empty>}
      <h4>Saved graph templates</h4>
      {items.filter(x=>x.kind==='chart'&&!x.trashed).map(item=><button className="rw-row"
        key={item.id} onClick={()=>loadChart(item)}>
          <span><strong>{item.title}</strong><small>{item.updated_utc.slice(0,16)}</small></span>
          <RotateCcw size={15}/></button>)}
    </Box>
  </div>
}

function NotebookChartCell({cell,charts,onChange}:{
  cell:NotebookCell;charts:Item[];onChange:(next:Partial<NotebookCell>)=>void
}){
  const item=charts.find(c=>c.id===cell.chart_id)
  const first=item?.payload.plot
  const all=item?.payload.plots
  const plot=(first||(Array.isArray(all)?all[0]:null)) as ResearchPlotData|null
  return <div className="rw-notebook-chart">
    <Select label="Archived graph snapshot" value={cell.chart_id||''}
      onChange={value=>onChange({chart_id:value})}
      options={[{value:'',label:'Choose saved graph'},...charts.map(x=>({
        value:x.id,label:x.title}))]}/>
    {!!plot&&<ResearchPlot plot={plot}/>}
    {item&&<p className="rw-help">Figure reference: {item.id}. The report freezes the selected saved chart values.</p>}
    <label className="rw-field"><span>Figure caption / interpretation</span>
      <textarea rows={3} value={cell.content||''}
        onChange={e=>onChange({content:e.target.value})}/></label>
  </div>
}

function ProjectsPanel({records,runs,busy,perform,onMessage,startJob,onOpenCompare}:{
  records:Item[];runs:RunOption[];busy:boolean;
  perform:<T,>(action:()=>Promise<T>,done?:(r:T)=>void)=>Promise<void>;
  onMessage:(text:string)=>void;
  startJob:(job:{job_id:string;status:string},caption:string)=>void;
  onOpenCompare:()=>void
}){
  const projects=records.filter(r=>r.kind==='project'&&!r.trashed)
  const notebooks=records.filter(r=>r.kind==='notebook'&&!r.trashed)
  const charts=records.filter(r=>r.kind==='chart'&&!r.trashed)
  const [name,setName]=useState('')
  const [projectId,setProjectId]=useState('')
  const [notebookId,setNotebookId]=useState('')
  const [cells,setCells]=useState<NotebookCell[]>([])
  const [dirty,setDirty]=useState(false)
  const [saving,setSaving]=useState(false)
  const [notebookTitle,setNotebookTitle]=useState('')
  const [goal,setGoal]=useState('')
  const [description,setDescription]=useState('')
  const [editingReport,setEditingReport]=useState('')
  const [reportBody,setReportBody]=useState('')

  const initialized=useRef(false)
  const revision=useRef(0)
  const selectedNotebook=notebooks.find(n=>n.id===notebookId)
  const project=projects.find(p=>p.id===projectId)
  useEffect(()=>{
    setGoal(String(project?.payload.goal||''))
    setDescription(String(project?.payload.description||''))
  },[project?.id])
  const saveProject=()=>{if(!project)return
    perform(()=>api<Item>('/workspace/records/'+project.id,{
      payload:{...project.payload,goal,description}},'PATCH'),
      ()=>onMessage('Research project details saved'))
  }
  const openReport=async(item:Item)=>{
    try{const src=await api<{content:string}>('/workspace/reports/'+item.id+'/source')
      setEditingReport(item.id);setReportBody(src.content)}
    catch(e){onMessage(e instanceof Error?e.message:String(e))}
  }
  const saveReport=()=>{if(!editingReport)return
    perform(()=>api<Item>('/workspace/reports/'+editingReport+'/source',
      {content:reportBody},'PUT'),()=>{setEditingReport('');onMessage('Report updated in HTML, Markdown and PDF')})}
  const projectNotebooks=notebooks.filter(n=>String(n.payload.project_id||'')===projectId)
  const pickNotebook=(item:Item)=>{
    revision.current+=1
    type NotebookDraft={title:string;project_id:string;cells:NotebookCell[]}
    let draft:NotebookDraft|null=null
    try{
      const stored=window.localStorage.getItem('ql-notebook-draft-'+item.id)
      if(stored){
        const parsed=JSON.parse(stored) as NotebookDraft|null
        if(parsed&&typeof parsed.title==='string'&&Array.isArray(parsed.cells)&&parsed.cells.length<=100)
          draft=parsed
      }
    }catch{/* invalid or unavailable local draft */}
    setNotebookId(item.id)
    setProjectId(String(draft?.project_id||item.payload.project_id||projectId))
    setNotebookTitle(draft?.title||item.title)
    setCells(draft?.cells||(Array.isArray(item.payload.cells)?item.payload.cells as NotebookCell[]:[]))
    setDirty(!!draft);initialized.current=true
  }
  useEffect(()=>{
    if(selectedNotebook||initialized.current)return
    if(notebooks.length)pickNotebook(notebooks[0])
  },[notebooks,selectedNotebook])
  useEffect(()=>{
    if(!dirty||!notebookId)return
    const key='ql-notebook-draft-'+notebookId
    const version=revision.current
    // Keep the current draft locally even when the user switches tabs before
    // the debounce finishes. Only the newest write may mark it as saved.
    try{window.localStorage.setItem(key,JSON.stringify({
      title:notebookTitle,project_id:projectId,cells}))}
    catch{/* storage disabled or quota exceeded; manual save remains available */}
    const timer=window.setTimeout(()=>{
      setSaving(true)
      void api<Item>('/workspace/records/'+notebookId,
        {title:notebookTitle,payload:{project_id:projectId,cells}},'PATCH')
        .then(()=>{
          if(version===revision.current){
            setDirty(false)
            try{window.localStorage.removeItem(key)}catch{}
            onMessage('Notebook autosaved')
          }
        })
        .catch(()=>onMessage('Autosave failed: use Save now to retry'))
        .finally(()=>setSaving(false))
    },1200)
    return()=>window.clearTimeout(timer)
  },[cells,dirty,notebookId,notebookTitle,projectId,onMessage])
  const createProject=()=>perform(()=>api<Item>('/workspace/records',
    {kind:'project',title:name||'Untitled research project',
      payload:{goal:'',description:'',status:'active'},tags:['research']},'POST'),
    item=>{setProjectId(item.id);setName('');onMessage('Research project created')})
  const createNotebook=()=>perform(()=>api<Item>('/workspace/records',
    {kind:'notebook',title:name||'Research notebook',
      payload:{project_id:projectId,cells:[]},tags:['notebook']},'POST'),
    item=>{pickNotebook(item);setName('');onMessage('Notebook created')})
  const alter=(newCells:NotebookCell[])=>{
    revision.current+=1;setCells(newCells);setDirty(true)
  }
  const addCell=(type:NotebookCell['type'])=>{
    const initial:NotebookCell={id:'cell_'+Date.now().toString(36),type,
      content:type==='markdown'?'Research observation…':'',
      run_id:type==='run'?runs.find(r=>r.kind==='model_run')?.id:undefined,
      chart_id:type==='chart'?charts[0]?.id:undefined}
    alter([...cells,initial])
  }
  const updateCell=(index:number,patch:Partial<NotebookCell>)=>alter(cells.map((c,i)=>
    i===index?{...c,...patch}:c))
  const save=()=>{
    if(!notebookId)return
    const version=revision.current
    const key='ql-notebook-draft-'+notebookId
    void perform(()=>api<Item>('/workspace/records/'+notebookId,
      {title:notebookTitle,payload:{project_id:projectId,cells}},'PATCH'),()=>{
        if(version===revision.current){
          setDirty(false)
          try{window.localStorage.removeItem(key)}catch{}
        }
        onMessage('Notebook saved')
      })
  }
  const importPortable=async(file:File)=>{
    if(file.size>8*1024*1024){onMessage('Portable bundle exceeds 8 MB');return}
    await perform(async()=>{
      const form=new FormData();form.append('file',file)
      const response=await fetch('/api/workspace/projects/import-bundle',{method:'POST',body:form})
      if(!response.ok){const err=await response.json().catch(()=>({detail:'Invalid research bundle'}))
        throw new Error(String(err.detail||'Import failed'))}
      return response.json() as Promise<{project_id:string;imported_records:number}>
    },x=>{setProjectId(x.project_id);setNotebookId('');initialized.current=true;
      onMessage(x.imported_records+' research records imported. Market data and credentials were excluded.')})
  }
  const rerunCell=(index:number,run_id:string)=>{
    if(!run_id||!window.confirm('Rerun the saved configuration using the current local dataset? The existing result is retained as an earlier version.'))return
    void perform(async()=>{
      const old=await api<{model_id:string;source?:{dataset_id?:string};params:Raw}>('/lab/runs/'+encodeURIComponent(run_id))
      return api<{run_id:string}>('/lab/run',{model_id:old.model_id,
        dataset_id:old.source?.dataset_id||null,params:old.params},'POST')
    },x=>{
      const existing=cells[index]
      updateCell(index,{run_id:x.run_id,
        previous_run_ids:[...new Set([...(existing.previous_run_ids||[]),run_id])]})
      onMessage('Model rerun saved. The notebook retains the earlier version for comparison.')
    })
  }
  const exportNotebook=()=>safeDownload((notebookTitle||'research_notebook')+'.json',
    JSON.stringify({title:notebookTitle,project_id:projectId,cells},null,2),'application/json')
  return <div className="rw-stack">
    <div className="rw-two">
      <Box title="Research projects">
        <p className="rw-help">Group related studies, model references, figures and reports. Organizing a project never creates duplicate market-price data.</p>
        <div className="rw-inline-actions"><input value={name} onChange={e=>setName(e.target.value)}
          placeholder="Project or notebook title"/>
          <button disabled={busy||saving} onClick={createProject}><Plus size={14}/> Project</button>
          <button disabled={busy||saving} onClick={createNotebook}><Plus size={14}/> Notebook</button></div>
        {projects.map(p=><button key={p.id} className={'rw-row '+(p.id===projectId?'active':'')}
          onClick={()=>{setProjectId(p.id);setNotebookId('');initialized.current=true}}>
          <Folder size={17}/><span><strong>{p.title}</strong><small>{p.id}</small></span></button>)}
        {!projects.length&&<Empty title="No projects yet">Create a project for a research question or thesis chapter.</Empty>}
        <label className="rw-file-button"><Upload size={15}/> Import portable project ZIP
          <input hidden type="file" accept=".zip" onChange={e=>{
            const file=e.target.files?.[0];if(file)void importPortable(file);e.target.value=''}}/>
        </label>
        {project&&<div className="rw-project-detail">
          <Field label="Research question / goal" value={goal} onChange={setGoal}/>
          <label className="rw-field"><span>Hypothesis and scope</span>
            <textarea rows={4} value={description} onChange={e=>setDescription(e.target.value)}/></label>
          <button disabled={busy} onClick={saveProject}><Save size={14}/> Save project details</button>
          <div className="rw-button-group">
            <a className="rw-download-link" href={'/api/workspace/projects/'+project.id+'/bundle.zip'} download>
              <Download size={15}/> Export portable project ZIP</a>
          </div>
          <p className="rw-help">Portable project bundles contain settings, figures and metrics-only run summaries. Licensed OHLCV and tokens are excluded; imported runs need reconnection to observed datasets.</p>
        </div>}
      </Box>
      <Box title="Project notebooks">
        {(projectId?projectNotebooks:notebooks).map(item=><button className={'rw-row '+(notebookId===item.id?'active':'')}
          key={item.id} onClick={()=>pickNotebook(item)}>
          <BookOpen size={17}/><span><strong>{item.title}</strong>
            <small>{Array.isArray(item.payload.cells)?item.payload.cells.length:0} notebook cells</small></span>
        </button>)}
        {!(projectId?projectNotebooks:notebooks).length&&
          <Empty title="No notebook selected">Create one or choose another project.</Empty>}
        <p className="rw-help">Notebook cells are stored as data and run references. No executable Python or arbitrary HTML is accepted.</p>
      </Box>
    </div>
    {notebookId&&selectedNotebook&&<Box title="Research notebook editor" side={
      <span className="rw-pill">{saving?'Saving…':dirty?'Unsaved edits':'Saved'}</span>}>
      <Field label="Notebook name" value={notebookTitle} onChange={v=>{
        revision.current+=1;setNotebookTitle(v);setDirty(true)
      }}/>
      <div className="rw-button-group">
        <button onClick={()=>addCell('markdown')}><Plus size={14}/> Text / equations</button>
        <button onClick={()=>addCell('run')} disabled={!runs.some(r=>r.kind==='model_run')}>
          <Plus size={14}/> Saved model run</button>
        <button onClick={()=>addCell('chart')} disabled={!charts.length}><Plus size={14}/> Saved chart figure</button>
        {!charts.length&&<button onClick={onOpenCompare}>
          <BarChart3 size={14}/> Create chart first</button>}
        <button onClick={()=>addCell('table')}><Plus size={14}/> Findings table</button>
      </div>
      <div className="rw-cell-stack">{cells.map((cell,i)=><div key={cell.id} className="rw-cell">
        <div className="rw-cell-head"><span>{String(i+1).padStart(2,'0')} / {cell.type}</span>
          <div className="rw-row-actions">
            <button aria-label="Move cell up" disabled={i===0} onClick={()=>{const next=[...cells];
              [next[i-1],next[i]]=[next[i],next[i-1]];alter(next)}}><ArrowLeft size={15}/></button>
            <button aria-label="Move cell down" disabled={i===cells.length-1} onClick={()=>{const next=[...cells];
              [next[i+1],next[i]]=[next[i],next[i+1]];alter(next)}}><ArrowRight size={15}/></button>
            <button aria-label="Delete cell" onClick={()=>alter(cells.filter((_,n)=>i!==n))}><Trash2 size={15}/></button>
          </div></div>
        {cell.type==='run'?<div className="rw-stack">
          <select value={cell.run_id||''} onChange={e=>updateCell(i,{run_id:e.target.value})}>
            <option value="">Select a saved model run</option>
            {runs.filter(r=>r.kind==='model_run').map(r=><option key={r.id} value={r.id}>{r.label}</option>)}
          </select>
          <div className="rw-button-group">
            <button disabled={busy||!cell.run_id} onClick={()=>rerunCell(i,cell.run_id||'')}>
              <RefreshCw size={14}/> Rerun saved model configuration</button>
          </div>
          {!!cell.previous_run_ids?.length&&<div className="rw-run-versions">
            <strong>Preserved earlier run versions:</strong>
            {cell.previous_run_ids.map(id=><button key={id} onClick={()=>updateCell(i,{run_id:id})}>
              {id} · Reopen</button>)}
          </div>}
          <p className="rw-help">Rerunning uses the saved parameters and an available local source. The earlier result is never overwritten.</p>
        </div>:cell.type==='chart'?<NotebookChartCell cell={cell} charts={charts}
          onChange={patch=>updateCell(i,patch)}/>:
          <textarea rows={cell.type==='markdown'?5:3} value={cell.content||''}
          onChange={e=>updateCell(i,{content:e.target.value})}
          placeholder="Add an observation, mathematical assumption, or explanation"/>}
      </div>)}
        {!cells.length&&<Empty title="Your notebook is blank">Add an interpretation, saved run or figure note.</Empty>}
      </div>
      <div className="rw-button-group">
        <button className="rw-primary" onClick={save} disabled={busy||saving}>
          <Save size={15}/> Save notebook</button>
        <button onClick={exportNotebook}><Download size={15}/> Export source JSON</button>
        <button disabled={busy||saving||dirty} onClick={()=>perform(
          ()=>api<{job_id:string;status:string}>('/workspace/reports',
            {notebook_id:notebookId,format:'html'},'POST'),
          j=>startJob(j,'Research report'))}>
          <FileText size={15}/> Generate PDF, HTML & Markdown report</button>
      </div>
      {dirty&&<p className="rw-help">Save pending changes before generating a report. Reports freeze the saved notebook version.</p>}
    </Box>}
    <Box title="Generated research reports">
      {records.filter(x=>x.kind==='report'&&!x.trashed).map(item=><div className="rw-list-item" key={item.id}>
        <div><strong>{item.title}</strong><small>Generated {String(item.payload.generated_utc||'').slice(0,16)}</small></div>
        <div className="rw-row-actions">
          <a href={'/api/workspace/reports/'+item.id+'/html'} download><ArrowDownToLine size={15}/> HTML</a>
          <a href={'/api/workspace/reports/'+item.id+'/markdown'} download><ArrowDownToLine size={15}/> MD</a>
          <a href={'/api/workspace/reports/'+item.id+'/pdf'} download><ArrowDownToLine size={15}/> PDF</a>
          <button title="Edit report" onClick={()=>void openReport(item)}><FileText size={15}/> Edit</button>
        </div></div>)}
      {!records.some(x=>x.kind==='report'&&!x.trashed)&&
        <Empty title="No research reports yet">Create one from a saved research notebook.</Empty>}
      {editingReport&&<div className="rw-report-editor">
        <label className="rw-field"><span>Edit report body (Markdown/plain text)</span>
          <textarea rows={17} value={reportBody} onChange={e=>setReportBody(e.target.value)}/></label>
        <div className="rw-button-group"><button className="rw-primary" disabled={busy} onClick={saveReport}>
          <Save size={14}/> Save report</button>
          <button onClick={()=>setEditingReport('')}><X size={14}/> Close editor</button></div>
        <p className="rw-help">Edits update the downloaded Markdown, HTML and PDF snapshots; saved mathematical model results remain immutable.</p>
      </div>}
    </Box>
  </div>
}

function AutomationPanel({datasets,selectedDataset,onSelectDataset,models,runs,busy,perform,startJob}:{
  datasets:Datum[];selectedDataset:string;onSelectDataset:(id:string)=>void;
  models:ModelSpec[];runs:RunOption[];busy:boolean;
  perform:<T,>(action:()=>Promise<T>,done?:(r:T)=>void)=>Promise<void>;
  startJob:(job:{job_id:string;status:string},caption:string)=>void
}){
  const [tool,setTool]=useState<'sweep'|'validation'|'scenario'|'repro'>('sweep')
  const [modelId,setModelId]=useState('gbm')
  const [parameter,setParameter]=useState('volatility')
  const [values,setValues]=useState(loadDraft('ql-rw-sweep-values','0.10, 0.20, 0.30'))
  const [metric,setMetric]=useState('')
  const [validation,setValidation]=useState({
    model:'min_variance',assets:8,train_window:180,test_step:20,
    max_weight:0.3,mode:'walk_forward',seed:2026})
  const [scenarioRun,setScenarioRun]=useState('')
  const [shocks,setShocks]=useState('RELIANCE=-0.05, TCS=-0.03')
  const [scenarioResult,setScenarioResult]=useState<Raw|null>(null)
  const [auditRun,setAuditRun]=useState('')
  const [repro,setRepro]=useState<Raw|null>(null)
  const chosen=models.find(x=>x.id===modelId)
  const numeric=(chosen?.parameters||[]).filter(p=>p.type==='number'||p.type==='integer')
  const historicalDatasets=dataOptions(datasets).filter(x=>x.value!=='synthetic')
  useEffect(()=>{window.localStorage.setItem('ql-rw-sweep-values',values)},[values])
  const chooseModel=(id:string)=>{
    setModelId(id);setMetric('')
    const m=models.find(x=>x.id===id)
    const p=m?.parameters.find(x=>x.type==='number')||m?.parameters.find(x=>x.type==='integer')
    if(p){
      setParameter(p.key)
      const val=Number(p.default)
      setValues([val*.8,val,val*1.2].map(x=>Number(x.toFixed(4))).join(', '))
    }
  }
  const runSweep=()=>{
    const nums=values.split(/[,\n]/).map(s=>Number(s.trim())).filter(v=>Number.isFinite(v))
    if(nums.length<2||nums.length>16||!chosen)return
    const params=Object.fromEntries(chosen.parameters.map(p=>[p.key,p.default]))
    perform(()=>api<{job_id:string;status:string}>('/workspace/sweep',{
      model_id:modelId,dataset_id:chosen.mode==='historical'?selectedDataset:null,
      params,parameter,values:nums,metric_label:metric},'POST'),
      r=>startJob(r,'Parameter sweep · '+chosen.title))
  }
  const runValidation=()=>perform(()=>api<{job_id:string;status:string}>('/workspace/validate',{
    dataset_id:selectedDataset,...validation},'POST'),r=>startJob(r,'Chronological validation'))
  const inspectRepro=(recompute:boolean)=>perform(
    ()=>api<Raw>('/workspace/reproducibility/'+encodeURIComponent(auditRun)+
          '?recompute='+String(recompute)),setRepro)
  const stress=()=>{
    const pairs=shocks.split(/[,\n]/).map(s=>s.trim()).filter(Boolean)
    const parsed:Record<string,number>={}
    for(const pair of pairs){
      const chunks=pair.split('=')
      if(chunks.length!==2||!chunks[0].trim()||!Number.isFinite(Number(chunks[1]))){
        window.alert('Use SYMBOL=-0.05, OTHER=-0.03 (decimal returns)');return}
      parsed[chunks[0].trim()]=Number(chunks[1])
    }
    perform(()=>api<Raw>('/workspace/scenario',{run_id:scenarioRun,shocks:parsed},'POST'),
      setScenarioResult)
  }
  return <div className="rw-stack">
    <Box title="Reproducible research automation">
      <div className="rw-segments">{(['sweep','validation','scenario','repro'] as const).map(v=>
        <button key={v} className={tool===v?'active':''} onClick={()=>setTool(v)}>
          {v==='sweep'?'Parameter sweeps':v==='validation'?'Walk-forward / holdout':
            v==='scenario'?'Scenario analysis':'Reproducibility audit'}
        </button>)}</div>
      <p className="rw-help">Research jobs run inside the local Python process using saved market data. They never place orders or submit broker requests.</p>
    </Box>
    {tool==='sweep'&&<div className="rw-two">
      <Box title="Parameter sweep">
        <Select label="Mathematical model" value={modelId} onChange={chooseModel}
          options={models.map(x=>({value:x.id,label:x.title+' · '+x.group}))}/>
        {chosen?.mode==='historical'&&<Select label="Observed dataset" value={selectedDataset}
          onChange={onSelectDataset} options={dataOptions(datasets)}/>}
        <Select label="Parameter to vary" value={parameter} onChange={setParameter}
          options={numeric.map(p=>({value:p.key,label:p.key.replaceAll('_',' ')}))}/>
        <Field label="2–16 distinct values, separated by commas" value={values} onChange={setValues}
          placeholder="0.10, 0.20, 0.30"/>
        <Field label="Metric name (leave blank to choose first common metric)"
          value={metric} onChange={setMetric}/>
        <button className="rw-primary" disabled={busy||!parameter} onClick={runSweep}>
          <Workflow size={16}/> Run model sweep</button>
        <p className="rw-caution">This is a parameter-sensitivity study. Comparing in-sample results does not demonstrate out-of-sample alpha.</p>
      </Box>
      <Box title="What QuantLab runs">
        <p>Every requested parameter value creates a real Python model execution with validated bounds, source lineage and saved outputs.</p>
        <p>Numerical outcomes are collected on a parameter-response graph, and each run is recorded in the results library for later comparison.</p>
        <div className="rw-insight">Suggested use: compare stochastic volatility, mean-reversion parameters, simulation horizons, portfolio constraints or statistical assumptions.</div>
      </Box>
    </div>}
    {tool==='validation'&&<div className="rw-two">
      <Box title="Time-ordered portfolio validation">
        <Select label="Observed market dataset" value={historicalDatasets.some(x=>x.value===selectedDataset)?selectedDataset:''}
          onChange={onSelectDataset} options={[{value:'',label:'Select actual historical prices…'},...historicalDatasets]}/>
        {selectedDataset==='synthetic'&&<p className="rw-caution">The synthetic example is excluded from historical validation. Prepare observed Dhan or uploaded prices first.</p>}
        <Select label="Portfolio allocation" value={validation.model}
          onChange={v=>setValidation({...validation,model:v})}
          options={['equal','inverse_volatility','min_variance','risk_parity','max_diversification']
            .map(v=>({value:v,label:v.replaceAll('_',' ')}))}/>
        <Select label="Validation design" value={validation.mode}
          onChange={v=>setValidation({...validation,mode:v})}
          options={[{value:'walk_forward',label:'Rolling recalibration and forward evaluation'},
            {value:'single_holdout',label:'One untouched chronological holdout'}]}/>
        <div className="rw-form-grid">
          <Field label="Assets (2–18)" type="number" value={String(validation.assets)}
            onChange={v=>setValidation({...validation,assets:Number(v)})}/>
          <Field label="Train observations" type="number" value={String(validation.train_window)}
            onChange={v=>setValidation({...validation,train_window:Number(v)})}/>
          <Field label="Test step" type="number" value={String(validation.test_step)}
            onChange={v=>setValidation({...validation,test_step:Number(v)})}/>
          <Field label="Max weight" type="number" value={String(validation.max_weight)}
            onChange={v=>setValidation({...validation,max_weight:Number(v)})}/>
        </div>
        <button className="rw-primary" disabled={busy||!historicalDatasets.some(x=>x.value===selectedDataset)} onClick={runValidation}>
          <History size={15}/> Run chronological validation</button>
      </Box>
      <Box title="Built-in research protections">
        <div className="rw-checks">
          <p><Check size={15}/> Training observations strictly precede holdout observations.</p>
          <p><Check size={15}/> Portfolio weights are computed only from the training window.</p>
          <p><Check size={15}/> Equal-weight benchmark is calculated on the same holdout dates.</p>
          <p><Check size={15}/> Block-bootstrap confidence interval on active returns.</p>
          <p><Check size={15}/> Returns, fold dates, allocations and uncertainty are saved.</p>
        </div>
        <p className="rw-caution">Corporate actions, dividends, PIT selection, transaction costs and prospective fills still need independent evidence before investment-performance claims.</p>
      </Box>
    </div>}
    {tool==='repro'&&<div className="rw-two">
      <Box title="Saved model reproducibility checker">
        <Select label="Frozen model result" value={auditRun} onChange={v=>{setAuditRun(v);setRepro(null)}}
          options={[{value:'',label:'Choose saved model run'},...runs.filter(r=>r.kind==='model_run')
            .map(r=>({value:r.id,label:r.label}))]}/>
        <p className="rw-help">First verify the original price-file SHA-256. Then optionally recompute numerical figures using the saved model settings. Reports identify the original and current Git commit and Python/numerical library versions.</p>
        <div className="rw-button-group">
          <button disabled={busy||!auditRun} onClick={()=>inspectRepro(false)}>
            <ShieldCheck size={15}/> Check source data & versions</button>
          <button className="rw-primary" disabled={busy||!auditRun}
            onClick={()=>inspectRepro(true)}><RefreshCw size={15}/> Recompute and compare figures</button>
        </div>
      </Box>
      <Box title="Reproducibility evidence">
        {repro?<><NumberStats data={[
          {label:'Verification',value:String(repro.verification_status||'Unverified')},
          {label:'Source unchanged',value:String(repro.source_unchanged??'No observed source')},
          {label:'Environment unchanged',value:String(repro.environment_unchanged??'Legacy run')},
          {label:'Figure equality',value:String(repro.recomputed_figure_match??'Not recomputed')},
        ]}/>
        <p className="rw-note">{String(repro.message||'')}</p>
        <p className="rw-caution">{String(repro.warning||'Inspect numerical and data provenance.')}</p>
        <button onClick={()=>safeDownload('quantlab_reproducibility_'+auditRun+'.json',
          JSON.stringify(repro,null,2),'application/json')}>
          <Download size={14}/> Export reproducibility evidence</button>
        </>:<Empty title="No audit recorded">Select a saved model to check its original source and reproduce charts.</Empty>}
      </Box>
    </div>}
    {tool==='scenario'&&<div className="rw-two">
      <Box title="Hypothetical portfolio stress">
        <Select label="Saved empirical model" value={scenarioRun} onChange={setScenarioRun}
          options={[{value:'',label:'Choose empirical model result'},...runs
            .filter(r=>r.kind==='model_run').map(r=>({value:r.id,label:r.label}))]}/>
        <Field label="Scenario shocks, decimal return by symbol" value={shocks} onChange={setShocks}
          placeholder="SYMBOL=-0.05, ANOTHER=-0.10"/>
        <button className="rw-primary" disabled={busy||!scenarioRun}
          onClick={stress}><SlidersHorizontal size={15}/> Calculate scenario</button>
        <p className="rw-help">Symbols must exactly match the asset names recorded in the saved model run. If optimized portfolio weights are unavailable, the tool transparently uses an illustrative equal-weight basket.</p>
      </Box>
      <Box title="Computed shock decomposition">
        {scenarioResult?<><NumberStats data={[{label:'Portfolio shock',
          value:(Number(scenarioResult.portfolio_shock_return)*100).toFixed(2)+'%'},
          {label:'Basis',value:String(scenarioResult.basis)}]}/>
          <div className="rw-scroll"><table><thead><tr><th>Asset</th><th>Weight</th><th>Shock</th><th>Contribution</th></tr></thead>
            <tbody>{(scenarioResult.rows as {asset:string;weight:number;hypothetical_return:number;contribution:number}[]).map(r=>
            <tr key={r.asset}><td>{r.asset}</td><td>{fmt(r.weight)}</td>
              <td>{fmt(r.hypothetical_return)}</td><td>{fmt(r.contribution)}</td></tr>)}</tbody>
          </table></div><p className="rw-caution">{String(scenarioResult.warning)}</p></>:
          <Empty title="Choose shocks and run the model">No hypothetical scenario has been calculated.</Empty>}
      </Box>
    </div>}
  </div>
}

type DuplicateInventory={scanned_dataset_views:number;scanned_bytes:number;
  identical_groups:{signature_sha256:string;datasets:{dataset_id:string;title:string;
    file_bytes:number;file_count:number;dependencies:number;
    can_trash_without_dependencies:boolean}[];
    potential_view_bytes_reclaimable:number;safe_action:string}[];
  skipped:{dataset_id:string;reason:string}[];warning:string}
function QualityPanel({datasets,selectedDataset,onSelectDataset,onOpenDhan,onOpenLibrary}:{
  datasets:Datum[];selectedDataset:string;onSelectDataset:(id:string)=>void;
  onOpenDhan:()=>void;onOpenLibrary:()=>void
}){
  const [quality,setQuality]=useState<Raw|null>(null)
  const [disk,setDisk]=useState<{bytes:Record<string,number>;total_bytes:number}|null>(null)
  const [duplicates,setDuplicates]=useState<DuplicateInventory|null>(null)
  const [dupBusy,setDupBusy]=useState(false)
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')
  const inspect=async()=>{
    if(!selectedDataset)return
    setBusy(true);setError('')
    try{
      const [q,s]=await Promise.all([api<Raw>('/workspace/quality/'+encodeURIComponent(selectedDataset)),
        api<{bytes:Record<string,number>;total_bytes:number}>('/workspace/storage')])
      setQuality(q);setDisk(s)
    }catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setBusy(false)}
  }
  return <div className="rw-stack">
    <Box title="Market-data evidence audit">
      <p className="rw-help">Inspect actual observations and possible quality issues. No missing sessions are manufactured and extreme moves are marked for review rather than automatically corrected.</p>
      <div className="rw-form-grid"><Select label="Observed dataset" value={selectedDataset}
        onChange={v=>{onSelectDataset(v);setQuality(null)}} options={dataOptions(datasets)}/>
        <div className="rw-inline-actions"><button className="rw-primary" disabled={busy||!selectedDataset} onClick={()=>void inspect()}>
          {busy?<LoaderCircle size={15}/>:<ShieldCheck size={15}/>} Audit dataset</button>
          <button onClick={onOpenDhan}><Database size={15}/> Open data manager</button></div></div>
      {error&&<p className="rw-error">{error}</p>}
    </Box>
    {quality&&<Box title={'Data-quality findings · '+String(quality.label||quality.dataset_id)}>
      <NumberStats data={[
        {label:'Observed dates',value:Number(quality.price_dates||0)},
        {label:'Asset columns',value:Number(quality.asset_count||0)},
        {label:'Duplicate dates',value:Number(quality.duplicate_dates||0)},
        {label:'Invalid dates',value:Number(quality.invalid_dates||0)},
        {label:'Latest date',value:String(quality.latest_observed_date||'Unavailable')},
        {label:'Assets not checked',value:Number(quality.unassessed_assets||0)},
        {label:'Weekdays since last observation',value:String(quality.weekdays_since_latest??'Unknown')},
        {label:'Possible weekday gaps',value:String(quality.weekdays_missing_in_daily_span??'Not audited')},
      ]}/>
      {quality.recent_market_data===false&&<p className="rw-caution">
        This dataset ends more than five weekdays before the current date.
        That may be intentional for an older research window. If current market prices are needed,
        check the shared Dhan coverage and download only missing observations.
      </p>}
      {typeof quality.issues==='object'&&quality.issues!==null&&<div className="rw-stats">
        {Object.entries(quality.issues as Record<string,number>).map(([name,count])=>
          <div key={name}><small>{name.replaceAll('_',' ')}</small><strong>{count}</strong></div>)}
      </div>}
      <div className="rw-scroll"><table><thead><tr>
        <th>Security</th><th>Prices</th><th>Missing</th><th>Non-positive</th>
        <th>Extreme returns</th><th>Last 10 flat</th></tr></thead><tbody>
          {(quality.assets as {symbol:string;prices:number;missing_prices:number;
          invalid_prices:number;returns_gt_40pct:number;last_10_constant:boolean}[]||[]).map(row=>
            <tr key={row.symbol}><td>{row.symbol}</td><td>{row.prices}</td>
              <td>{row.missing_prices}</td><td>{row.invalid_prices}</td>
              <td>{row.returns_gt_40pct}</td><td>{row.last_10_constant?'Review':'No'}</td></tr>)}
        </tbody></table></div>
      <p className="rw-caution">{String(quality.warning||'This audit does not establish investability.')}</p>
      <button onClick={()=>safeDownload('quantlab_quality_'+selectedDataset+'.json',
        JSON.stringify(quality,null,2),'application/json')}><Download size={15}/> Export audit JSON</button>
    </Box>}
    <Box title="Find exact duplicate prepared datasets">
      <p className="rw-help">QuantLab compares user-owned prepared dataset views
        by the SHA-256 of their actual allowlisted files. This does not merge,
        overwrite or delete source data. Protected original Dhan candles remain reusable.</p>
      <button type="button" disabled={dupBusy} onClick={()=>{
        setDupBusy(true);setError('')
        void api<DuplicateInventory>('/workspace/data-maintenance/duplicates')
          .then(setDuplicates)
          .catch(e=>setError(e instanceof Error?e.message:String(e)))
          .finally(()=>setDupBusy(false))
      }}>{dupBusy?<LoaderCircle size={15}/>:<ShieldCheck size={15}/>}
        Scan for exact duplicates (read-only)</button>
      {duplicates&&<div className="rw-stack">
        <p className="rw-note">{duplicates.scanned_dataset_views} prepared views inspected.
          {' '}{duplicates.identical_groups.length} groups with identical file hashes.
          Checked {(duplicates.scanned_bytes/(1024*1024)).toFixed(1)} MB.</p>
        {duplicates.identical_groups.map(group=><div className="rw-caution"
          key={group.signature_sha256}><strong>{group.datasets.length} byte-identical
          {' '}prepared views · potential redundant view storage
          {' '}{(group.potential_view_bytes_reclaimable/(1024*1024)).toFixed(2)} MB</strong>
          <p>{group.safe_action}</p>
          {group.datasets.map(row=><div key={row.dataset_id} className="rw-list-item">
            <div><strong>{row.title}</strong><small>{row.dataset_id} ·
              {row.dependencies} dependent saved items ·
              {(row.file_bytes/(1024*1024)).toFixed(2)} MB</small></div>
            <button type="button" onClick={()=>{onSelectDataset(row.dataset_id);onOpenLibrary()}}>
              Inspect dependencies & management <ArrowRight size={14}/></button>
          </div>)}</div>)}
        {!duplicates.identical_groups.length&&<p className="rw-help">No complete byte-identical
          user-owned prepared views found in the bounded scan.</p>}
        {!!duplicates.skipped.length&&<p className="rw-caution">Some files were not hashed.
          Review source sizes or file links before asserting uniqueness.</p>}
      </div>}
    </Box>
    {disk&&<Box title="Local disk usage">
      <NumberStats data={[{label:'Total measured',value:(disk.total_bytes/(1024*1024)).toFixed(1)+' MB'}]}/>
      <div className="rw-list">{Object.entries(disk.bytes).map(([label,bytes])=><div className="rw-list-item" key={label}>
        <div><strong>{label.replaceAll('_',' ')}</strong></div><span>{(bytes/(1024*1024)).toFixed(2)} MB</span>
      </div>)}</div>
      <p className="rw-help">Trash consumes disk space until permanently purged. Raw Dhan history is protected and reused across index universes.</p>
    </Box>}
  </div>
}

function JobsPanel({jobs,busy,perform,onPage}:{
  jobs:Job[];busy:boolean;
  perform:<T,>(action:()=>Promise<T>,done?:(r:T)=>void)=>Promise<void>;
  onPage:(page:Page)=>void
}){
  const [selected,setSelected]=useState('')
  const item=jobs.find(j=>j.id===selected)||jobs[0]
  const cancel=(job:Job)=>perform(()=>api<Raw>('/workspace/jobs/'+job.id+'/cancel',{},'POST'))
  const plot=item?.result?.plot as ResearchPlotData|undefined
  const stats=item?.result?.metrics as Raw|undefined
  return <div className="rw-stack">
    <Box title="Local computation queue" side={<span className="rw-pill">
      {jobs.filter(j=>['running','queued'].includes(j.status)).length} active</span>}>
      <p className="rw-help">QuantLab runs computations in the local Python engine. Supported model sweeps and chronological validation can be cancelled safely between finished numerical steps; queued jobs can be cancelled before starting. Unsupportable mid-solver interruptions are not promised.</p>
      <div className="rw-list">{jobs.map(j=><div className={'rw-list-item '+(j.id===item?.id?'active':'')}
        key={j.id}><button className="rw-plain" onClick={()=>setSelected(j.id)}>
          <strong>{j.kind.replaceAll('_',' ')}</strong><small>{j.id} · {j.created_utc?.slice(0,16)||''}</small></button>
        <span className={'rw-pill '+j.status}>{j.status}</span>
        {(j.status==='queued'||(j.status==='running'&&j.cancellable))&&
          <button disabled={busy} onClick={()=>cancel(j)}><X size={14}/>
            {j.status==='running'?'Request safe cancellation':'Cancel queued'}</button>}
        {(j.status==='error'||j.status==='cancelled')&&
          ['workspace_parameter_sweep','workspace_grid_sweep','workspace_validation',
           'workspace_report'].includes(j.kind)&&<button disabled={busy}
          onClick={()=>perform(()=>api<Raw>('/workspace/jobs/'+j.id+'/retry',{},'POST'))}>
          <RotateCcw size={14}/> Retry</button>}
      </div>)}
      {!jobs.length&&<Empty title="No jobs recorded">Download history, parameter sweeps, and report creation will appear here.</Empty>}</div>
    </Box>
    {item&&<Box title="Selected job details">
      <NumberStats data={[{label:'Status',value:item.status},
        {label:'Operation',value:item.kind},{label:'Job ID',value:item.id}]}/>
      {typeof item.percent==='number'&&
        <div className="rw-job-progress">
          <div><strong>{item.stage||'Research in progress'}</strong>
            <span>{item.percent.toFixed(0)}%</span></div>
          <progress aria-label="Research job progress" max="100" value={item.percent}/>
        </div>}
      {item.error&&<p className="rw-error">{item.error}</p>}
      {item.status==='interrupted'&&<p className="rw-caution">
        The previous Python process exited while this job was active. Reopen the saved study or rerun its configuration; do not mistake this status for a completed research result.</p>}
      {item.result&&<><div className="rw-button-group">
        <button onClick={()=>safeDownload(item.id+'.json',JSON.stringify(item.result,null,2),'application/json')}>
          <Download size={15}/> Download results JSON</button>
        <button onClick={()=>onPage('library')}><Folder size={15}/> Saved library</button>
      </div>
      {stats&&<NumberStats data={Object.entries(stats).slice(0,8).map(([k,v])=>({
        label:k.replaceAll('_',' '),value:typeof v==='number'?fmt(v):String(v)
      }))}/>}
      {plot&&<ResearchPlot plot={plot}/>}
      {(typeof item.result.returns_csv_url==='string'||
        (item.kind==='workspace_validation'&&typeof item.result.study_id==='string'))&&
        <a className="rw-download-link"
          href={(typeof item.result.returns_csv_url==='string'?item.result.returns_csv_url:
            '/api/workspace/studies/'+item.result.study_id+'/returns.csv') as string} download>
          <Download size={15}/> Download complete holdout-return CSV</a>}
      {typeof item.result.message==='string'&&<p className="rw-success">{item.result.message}</p>}
      {item.result.warning&&<p className="rw-caution">{String(item.result.warning)}</p>}
      </>}
    </Box>}
  </div>
}


function DashboardPanel({runs,records,busy,perform,onMessage,onCompare}:{
  runs:RunOption[];records:Item[];busy:boolean;
  perform:<T,>(action:()=>Promise<T>,done?:(r:T)=>void)=>Promise<void>;
  onMessage:(value:string)=>void;onCompare:()=>void
}){
  const [pinned,setPinned]=useState<string[]>(()=>{
    try{const parsed=JSON.parse(window.localStorage.getItem('ql-rw-pinned-runs')||'[]')
      return Array.isArray(parsed)?parsed.filter(x=>typeof x==='string').slice(0,6):[]}
    catch{return []}
  })
  const [dashboardTitle,setDashboardTitle]=useState('My QuantLab research dashboard')
  const [summaries,setSummaries]=useState<Record<string,{title:string;metrics:{label:string;value:unknown;unit:string}[];
    plots:ResearchPlotData[]}>>({})
  useEffect(()=>{window.localStorage.setItem('ql-rw-pinned-runs',JSON.stringify(pinned))},[pinned])
  useEffect(()=>{
    let active=true
    const targets=pinned.filter(id=>runs.some(r=>r.id===id&&r.kind==='model_run'))
    if(!targets.length){setSummaries({});return}
    void Promise.all(targets.map(id=>api<{title:string;metrics:{label:string;value:unknown;unit:string}[];
      plots:ResearchPlotData[]}>('/lab/runs/'+id)
      .then(data=>({id,data})).catch(()=>null))).then(rows=>{
        if(active)setSummaries(Object.fromEntries(rows.filter((x):x is
          {id:string;data:{title:string;metrics:{label:string;value:unknown;unit:string}[];
            plots:ResearchPlotData[]}}=>!!x).map(x=>[x.id,x.data])))
      })
    return()=>{active=false}
  },[pinned.join(','),runs])
  const toggle=(id:string)=>setPinned(old=>old.includes(id)?
    old.filter(x=>x!==id):old.length<6?[...old,id]:old)
  const save=()=>perform(()=>api<Item>('/workspace/records',{
    kind:'dashboard',title:dashboardTitle,payload:{pinned_runs:pinned},
    tags:['dashboard']},'POST'),()=>onMessage('Dashboard layout saved'))
  const restore=(item:Item)=>{
    const pins=item.payload.pinned_runs
    if(Array.isArray(pins))setPinned(pins.filter(x=>typeof x==='string').slice(0,6) as string[])
    setDashboardTitle(item.title);onMessage('Dashboard layout restored')
  }
  return <Box title="My custom research dashboard" side={<span className="rw-pill">{pinned.length} pinned models</span>}>
    <p className="rw-help">Pin up to six immutable saved model results. Your selection autosaves locally; you can also give the dashboard a reusable name.</p>
    <div className="rw-form-grid">
      <label className="rw-field"><span>Pin a saved model</span>
        <select value="" onChange={e=>{if(e.target.value)toggle(e.target.value)}}>
          <option value="">Choose saved model run…</option>
          {runs.filter(r=>r.kind==='model_run'&&!pinned.includes(r.id)).map(r=>
            <option key={r.id} value={r.id}>{r.label}</option>)}
        </select></label>
      <Field label="Dashboard title" value={dashboardTitle} onChange={setDashboardTitle}/>
    </div>
    <div className="rw-dashboard-grid">{pinned.map(id=>{
      const result=summaries[id]
      return <div className="rw-dashboard-card" key={id}>
        <div className="rw-cell-head"><span>{result?.title||id}</span>
          <button title="Unpin result" onClick={()=>toggle(id)}><X size={14}/></button></div>
        {result?<><div className="rw-mini-stats">{result.metrics.slice(0,3).map((m,i)=><div key={i}>
          <small>{m.label}</small><strong>{String(m.value??'Unavailable')}</strong></div>)}</div>
          {result.plots[0]&&result.plots[0].kind!=='surface3d'&&
            <ResearchPlot plot={result.plots[0]}/>}</>:
          <p className="rw-help">Loading saved computations…</p>}
      </div>
    })}</div>
    {!pinned.length&&<Empty title="No pinned results">Choose saved results to build a personal home dashboard.</Empty>}
    <div className="rw-button-group">
      <button className="rw-primary" disabled={busy||!pinned.length} onClick={save}><Save size={14}/> Save dashboard</button>
      <button onClick={onCompare}><BarChart3 size={14}/> Open comparison studio</button>
    </div>
    {records.filter(x=>x.kind==='dashboard'&&!x.trashed).length>0&&<div className="rw-saved-dashboards">
      <h4>Saved dashboards</h4>
      {records.filter(x=>x.kind==='dashboard'&&!x.trashed).map(item=>
        <button className="rw-row" key={item.id} onClick={()=>restore(item)}>
          <span><strong>{item.title}</strong><small>{item.updated_utc.slice(0,16)}</small></span>
          <RotateCcw size={14}/></button>)}
    </div>}
  </Box>
}

function SettingsTransfer({onMessage}:{onMessage:(message:string)=>void}){
  const exportSettings=()=>{
    const entries:Record<string,string>={}
    for(let i=0;i<window.localStorage.length;i++){
      const key=window.localStorage.key(i)
      if(key&&key.startsWith('ql-')&&!key.toUpperCase().includes('TOKEN')){
        const value=window.localStorage.getItem(key)
        if(value!==null&&value.length<150000)entries[key]=value
      }
    }
    safeDownload('quantlab_preferences.json',JSON.stringify({
      version:1,source:'QuantLab local UI preferences',entries},null,2),'application/json')
    onMessage('Preferences exported without broker credentials')
  }
  const importSettings=async(file:File)=>{
    if(file.size>250000){onMessage('Preferences file is too large');return}
    try{
      const decoded=JSON.parse(await file.text()) as {version:number;entries:Record<string,string>}
      if(decoded.version!==1||!decoded.entries||typeof decoded.entries!=='object')
        throw new Error('Unsupported QuantLab preferences format')
      for(const [key,value] of Object.entries(decoded.entries)){
        if(!key.startsWith('ql-')||key.toUpperCase().includes('TOKEN')||
           typeof value!=='string'||value.length>150000)continue
        window.localStorage.setItem(key,value)
      }
      onMessage('Preferences imported. Reload the workstation to apply them.')
    }catch(e){onMessage(e instanceof Error?e.message:String(e))}
  }
  return <Box title="Research workspace settings">
    <p className="rw-help">Export and import layout preferences, model setup drafts, dashboard pins and chart settings on this browser. Actual observations and model-run artifacts remain local Python files.</p>
    <div className="rw-button-group"><button onClick={exportSettings}>
      <Download size={15}/> Export preferences JSON</button>
      <label className="rw-file-button"><Upload size={15}/> Import preferences JSON
        <input hidden type="file" accept=".json,application/json" onChange={e=>{
          const file=e.target.files?.[0];if(file)void importSettings(file);e.target.value=''}}/></label>
    </div>
  </Box>
}

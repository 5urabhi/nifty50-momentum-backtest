import {useCallback,useEffect,useMemo,useRef,useState} from 'react'
import {Archive,ArrowDownToLine,ArrowLeft,ArrowRight,BarChart3,BookOpen,Check,
  CheckCircle2,ChevronDown,Copy,Database,Download,FileText,Folder,Heart,
  History,Layers3,LoaderCircle,Plus,RefreshCw,RotateCcw,Save,Search,
  Settings2,ShieldCheck,SlidersHorizontal,Trash2,Undo2,Upload,Workflow,X} from 'lucide-react'
import ResearchPlot,{type ResearchPlotData} from './ResearchPlots'
import './research-workspace.css'

type Raw = Record<string,unknown>
type Page='home'|'library'|'compare'|'projects'|'automation'|'quality'|'jobs'
type RecordKind='configuration'|'project'|'notebook'|'chart'|'comparison'|'dashboard'|'note'|'report'|'study'
type ResourceKind='dataset'|'model_run'|'research_run'
type Item={id:string;kind:RecordKind;title:string;payload:Raw;tags:string[];
  favorite:boolean;archived:boolean;trashed:boolean;updated_utc:string;created_utc:string}
type Resource={id:string;kind:ResourceKind;title:string;summary:string;
  protected:boolean;archived:boolean;trashed:boolean}
type Datum={id:string;label:string;has_prices:boolean;ready:boolean}
type ModelRun={id:string;model_id:string;title:string;group:string;mode:string;
  dataset_id?:string|null;figures:number;generated_utc?:string}
type IndexRun={id:string;name:string;dataset_id?:string;created_utc?:string}
type RunOption={key:string;kind:'model_run'|'research_run';id:string;label:string;model?:string;figures:number}
type Job={id:string;kind:string;status:string;result?:Raw;error?:string;
  created_utc?:string}
type ModelSpec={id:string;title:string;group:string;mode:string;parameters:{
  key:string;default:number|string;type:string;min?:number;max?:number}[]}
type NotebookCell={id:string;type:'markdown'|'run'|'chart'|'table';content?:string;run_id?:string}
type Props={datasets:Datum[];selectedDataset:string;onSelectDataset:(id:string)=>void;
  onOpenDhan:()=>void;onOpenModels:()=>void;onDataChanged:()=>void}
const PAGES:{id:Page;label:string;sub:string}[]=[
  {id:'home',label:'Start',sub:'Resume and guided workflows'},
  {id:'library',label:'Library',sub:'Datasets, models, results'},
  {id:'compare',label:'Compare & Graph',sub:'Overlay and chart studio'},
  {id:'projects',label:'Projects & Notes',sub:'Notebooks and reports'},
  {id:'automation',label:'Research Tools',sub:'Sweeps, validation, shocks'},
  {id:'quality',label:'Data Quality',sub:'Coverage and provenance'},
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
  onOpenDhan,onOpenModels,onDataChanged}:Props){
  const [page,setPage]=useState<Page>('home')
  const [library,setLibrary]=useState<Item[]>([])
  const [resources,setResources]=useState<Resource[]>([])
  const [models,setModels]=useState<ModelSpec[]>([])
  const [runs,setRuns]=useState<RunOption[]>([])
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
      const [records,items,saved,index,registry,queue]=await Promise.all([
        api<{records:Item[]}>('/workspace/records?archived=true'),
        api<{resources:Resource[]}>('/workspace/resources'),
        api<{runs:ModelRun[]}>('/lab/runs'),
        api<{runs:IndexRun[]}>('/runs'),
        api<{models:ModelSpec[]}>('/lab/catalog'),
        api<{jobs:Job[]}>('/workspace/jobs')])
      setLibrary(records.records)
      setResources(items.resources)
      setModels(registry.models)
      setRuns([
        ...saved.runs.map(x=>({key:'model_run:'+x.id,kind:'model_run' as const,id:x.id,
            label:x.title+' · '+x.id.slice(0,8),model:x.model_id,figures:x.figures})),
        ...index.runs.map(x=>({key:'research_run:'+x.id,kind:'research_run' as const,
            id:x.id,label:x.name+' · '+x.id.slice(0,8),figures:1}))])
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
  const perform=async<T,>(action:()=>Promise<T>,then?:(value:T)=>void)=>{
    setBusy(true);setError(null)
    try{const result=await action();then?.(result);await reload()}
    catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setBusy(false)}
  }
  const openSearch=(x:{kind:string;id:string;location:string})=>{
    setSearchOpen(false);setQuery('')
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
    {page==='home'&&<div className="rw-two">
      <Box title="Resume research">
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
          <button onClick={()=>setPage('projects')}><BookOpen size={20}/><strong>4 · Publish findings</strong><small>Store notes and create a reproducible report.</small><ArrowRight size={15}/></button>
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
    </div>}
    {page==='library'&&<LibraryPanel items={library} resources={resources} busy={busy}
      perform={perform} onChanged={onDataChanged} onOpenModels={onOpenModels}
      onOpenDhan={onOpenDhan} onMessage={setMessage}/>}
    {page==='compare'&&<ComparePanel runs={runs} items={library} busy={busy}
      perform={perform} onMessage={setMessage}/>}
    {page==='projects'&&<ProjectsPanel records={library} runs={runs} busy={busy}
      perform={perform} onMessage={setMessage} startJob={start}/>}
    {page==='automation'&&<AutomationPanel datasets={datasets} selectedDataset={selectedDataset}
      onSelectDataset={onSelectDataset} models={models} runs={runs} busy={busy}
      perform={perform} startJob={start}/>}
    {page==='quality'&&<QualityPanel datasets={datasets} selectedDataset={selectedDataset}
      onSelectDataset={onSelectDataset} onOpenDhan={onOpenDhan}/>}
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
  const visibleResources=resources.filter(x=>(filter==='all'||x.kind===filter)&&
    (showArchived||!x.archived)&&
    (x.title+' '+x.summary).toLowerCase().includes(search.toLowerCase()))
  const visibleRecords=items.filter(x=>(filter==='all'||x.kind===filter)&&
    (mode==='trash'?x.trashed:!x.trashed)&&
    (showArchived||mode==='trash'||!x.archived)&&
    (x.title+' '+x.tags.join(' ')).toLowerCase().includes(search.toLowerCase()))
  const resourceOperation=(resource:Resource,operation:string)=>{
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
          <button key={v} className={mode===v?'active':''} onClick={()=>{setMode(v);setFilter('all');setDetail(null)}}>
            {v==='resources'?'Datasets & results':v==='saved'?'Saved work':'Trash'}</button>)}</div>
        <input className="rw-search-field" value={search} onChange={e=>setSearch(e.target.value)} placeholder="Filter by name or tag"/>
        <select value={filter} onChange={e=>setFilter(e.target.value)}>
          <option value="all">All kinds</option>
          {(mode==='resources'?['dataset','model_run','research_run']:
            ['configuration','chart','comparison','project','notebook','report','note','study','dashboard'])
            .map(v=><option key={v} value={v}>{v.replaceAll('_',' ')}</option>)}
        </select>
        <label className="rw-inline"><input type="checkbox" checked={showArchived}
          onChange={e=>setShowArchived(e.target.checked)}/> Show archived</label>
      </div>
      {mode==='resources'?
        <div className="rw-list">{visibleResources.map(r=><div key={r.kind+r.id} className="rw-list-item">
          <div><strong>{r.title}</strong><small>{r.kind} · {r.id} {r.protected?' · Protected source':''}</small>
            <p>{r.summary.slice(0,180)}</p></div>
          <div className="rw-row-actions">
            <button onClick={()=>setDetail(r)} aria-label={'Details '+r.title}><BookOpen size={15}/></button>
            <button title={r.archived?'Unarchive':'Archive'} disabled={busy}
              onClick={()=>resourceOperation(r,r.archived?'unarchive':'archive')}><Archive size={15}/></button>
            {!r.protected&&<button title="Move to Trash" disabled={busy}
              onClick={()=>resourceOperation(r,'trash')}><Trash2 size={15}/></button>}
          </div></div>)}
          {!visibleResources.length&&<Empty title="No matching resources">Try another filter or include archived items.</Empty>}
        </div>:
        <><div className="rw-toolbar">
          {!!selected.length&&<><strong>{selected.length} selected</strong>
            {(['archive','favorite','trash','restore'] as const).filter(v=>mode==='trash'?v==='restore':v!=='restore')
              .map(v=><button key={v} onClick={()=>batch(v)} disabled={busy}>{v}</button>)}</>}
        </div>
        <div className="rw-list">{visibleRecords.map(item=><div className="rw-list-item" key={item.id}>
          <input type="checkbox" checked={selected.includes(item.id)} aria-label={'Select '+item.title}
            onChange={e=>setSelected(s=>e.target.checked?[...s,item.id]:s.filter(v=>v!==item.id))}/>
          <div><strong>{item.title}</strong><small>{item.kind} · {item.updated_utc.slice(0,16)} · {item.tags.join(', ')||'No tags'}</small></div>
          <div className="rw-row-actions">
            <button title="Inspect" onClick={()=>{setDetail(item);setNewTitle(item.title)}}><BookOpen size={15}/></button>
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
        <div className="rw-inline-actions"><button disabled={busy} onClick={()=>perform(
          ()=>api<Item>('/workspace/records/'+detail.id,{title:newTitle},'PATCH'),
          updated=>{setDetail(updated);onMessage('Title updated')})}><Save size={15}/> Save title</button>
          <button onClick={()=>safeDownload(detail.id+'.json',JSON.stringify(detail,null,2),'application/json')}>
            <Download size={15}/> Export JSON</button></div></div>
        <pre className="rw-json">{JSON.stringify(detail.payload,null,2)}</pre></>:
      <><p>Resource identity: {detail.kind}:{detail.id}</p>
        <p>Archive hides this entry from the active workspace. Trash can only move independently derived datasets or saved results, never canonical Dhan source data. References prevent unsafe deletion.</p>
        <button onClick={()=>perform(()=>api<{dependencies:Raw[]}>(
          '/workspace/resources/dependencies?kind='+detail.kind+'&item_id='+encodeURIComponent(detail.id)),
          x=>onMessage(x.dependencies.length?x.dependencies.length+' saved references found':'No saved library dependencies found'))}>
          <ShieldCheck size={15}/> Check dependencies</button></>}
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
  const [kind,setKind]=useState('line2d')
  const [from,setFrom]=useState('0')
  const [to,setTo]=useState('100')
  const [comparison,setComparison]=useState<Raw|null>(null)
  const [saved,setSaved]=useState('')
  const [savedTemplate,setSavedTemplate]=useState('')
  const [overlay,setOverlay]=useState<'overlay'|'split'>('overlay')
  const history=useRef<{title:string;annotation:string;kind:string}[]>([])
  useEffect(()=>{window.localStorage.setItem('ql-rw-chart-title',title)},[title])
  useEffect(()=>{window.localStorage.setItem('ql-rw-chart-note',annotation)},[annotation])
  const edit=(next:{title?:string;annotation?:string;kind?:string})=>{
    history.current.push({title,annotation,kind})
    setTitle(next.title??title);setAnnotation(next.annotation??annotation);setKind(next.kind??kind)
  }
  const undo=()=>{
    const last=history.current.pop()
    if(last){setTitle(last.title);setAnnotation(last.annotation);setKind(last.kind)}
  }
  const toggle=(key:string)=>{
    setSelection(s=>s.includes(key)?s.filter(v=>v!==key):s.length>=8?s:[...s,key])
    setPlot(null);setComparison(null)
  }
  const chosen=selection.map(key=>runs.find(run=>run.key===key)).filter(
    (x):x is RunOption=>!!x)
  const selections=chosen.map(run=>({kind:run.kind,run_id:run.id,plot_index:0}))
  const build=()=>perform(()=>api<Raw>('/workspace/compare',{
    title,selections,normalize:normalization,alignment},'POST'),
    res=>{setPlot(res.plot as ResearchPlotData);setComparison(res);onMessage('Compatible saved results aligned. Inspect axes before reporting.')})
  const saveComparison=()=>perform(()=>api<Item>('/workspace/records',{
    kind:'comparison',title,payload:{selections,normalize:normalization,alignment,
      annotation,created_chart:comparison?.plot||null},tags:['comparison']},'POST'),
    savedItem=>{setSaved(savedItem.id);onMessage('Comparison workspace saved')})
  const saveChart=()=>perform(()=>api<Item>('/workspace/records',{
    kind:'chart',title,payload:{source_comparison:saved||null,plot:displayPlot,
      annotation,layout:{kind,from,to,overlay}},tags:['chart']},'POST'),
    res=>{setSavedTemplate(res.id);onMessage('Graph layout saved')})
  const loadComparison=(item:Item)=>{
    const configs=item.payload.selections
    if(!Array.isArray(configs))return
    const values=(configs as {kind:string;run_id:string}[]).map(x=>x.kind+':'+x.run_id)
    setSelection(values);setTitle(item.title)
    setNormalization(String(item.payload.normalize||'none'))
    setAlignment(String(item.payload.alignment||'intersection'))
    setAnnotation(String(item.payload.annotation||''));setPlot(null);setComparison(null)
  }
  const displayPlot=useMemo(()=>{
    if(!plot)return null
    const size=plot.x?.length||0
    const lo=Math.max(0,Math.floor(size*Number(from||0)/100))
    const hi=Math.min(size,Math.ceil(size*Number(to||100)/100))
    return {...plot,title,kind:kind==='bar2d'?'bar2d':'line2d',
      x:plot.x?.slice(lo,hi),
      traces:plot.traces?.map(trace=>({...trace,y:trace.y.slice(lo,hi)}))}
  },[plot,title,kind,from,to])
  const exportSVG=()=>{
    const graph=document.querySelector('.rw-graph-preview .ql-svg-chart, .rw-graph-preview .ql-surface svg') as SVGElement|null
    if(!graph){onMessage('SVG export is available for a rendered graph.');return}
    const serialized=new XMLSerializer().serializeToString(graph)
    safeDownload('quantlab_comparison.svg',serialized,'image/svg+xml')
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
          <span><strong>{r.label}</strong><small>{r.kind} · {r.model||'index experiment'}</small></span></label>)}
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
          <Select label="Layout" value={overlay} onChange={v=>setOverlay(v as 'overlay'|'split')}
            options={[{value:'overlay',label:'Same graph'},{value:'split',label:'Separate curves'}]}/></div>
        <div className="rw-form-grid">
          <Field label="Show from (%)" type="number" value={from} onChange={setFrom}/>
          <Field label="Show through (%)" type="number" value={to} onChange={setTo}/>
        </div>
        <div className="rw-button-group">
          <button onClick={undo} disabled={!history.current.length}><Undo2 size={14}/> Undo edit</button>
          <button onClick={saveComparison} disabled={!comparison||busy}><Save size={14}/> Save comparison</button>
          <button onClick={saveChart} disabled={!displayPlot||busy}><Save size={14}/> Save graph</button>
        </div>
        <div className="rw-button-group"><button disabled={!displayPlot} onClick={exportCSV}>
          <Download size={14}/> CSV</button>
          <button disabled={!displayPlot} onClick={exportSVG}><Download size={14}/> SVG</button>
          <button disabled={!displayPlot} onClick={()=>displayPlot&&safeDownload(
            'quantlab_comparison.json',JSON.stringify({plot:displayPlot,annotation},null,2),'application/json')}>
            <Download size={14}/> JSON</button></div>
        {(saved||savedTemplate)&&<p className="rw-success">Saved {savedTemplate||saved} in the research library.</p>}
      </Box>
    </div>
    {!!displayPlot&&<div className="rw-graph-preview">
      {overlay==='overlay'?<ResearchPlot plot={displayPlot}/>:<div className="rw-grid-plots">
        {(displayPlot.traces||[]).map((trace,i)=><ResearchPlot key={i}
          plot={{...displayPlot,title:trace.name,traces:[trace]}}/>)}</div>}
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
    </Box>
  </div>
}

function ProjectsPanel({records,runs,busy,perform,onMessage,startJob}:{
  records:Item[];runs:RunOption[];busy:boolean;
  perform:<T,>(action:()=>Promise<T>,done?:(r:T)=>void)=>Promise<void>;
  onMessage:(text:string)=>void;
  startJob:(job:{job_id:string;status:string},caption:string)=>void
}){
  const projects=records.filter(r=>r.kind==='project'&&!r.trashed)
  const notebooks=records.filter(r=>r.kind==='notebook'&&!r.trashed)
  const [name,setName]=useState('')
  const [projectId,setProjectId]=useState('')
  const [notebookId,setNotebookId]=useState('')
  const [cells,setCells]=useState<NotebookCell[]>([])
  const [dirty,setDirty]=useState(false)
  const [saving,setSaving]=useState(false)
  const [notebookTitle,setNotebookTitle]=useState('')
  const [noteText,setNoteText]=useState('')
  const initialized=useRef(false)
  const selectedNotebook=notebooks.find(n=>n.id===notebookId)
  const projectNotebooks=notebooks.filter(n=>String(n.payload.project_id||'')===projectId)
  const pickNotebook=(item:Item)=>{
    setNotebookId(item.id);setProjectId(String(item.payload.project_id||projectId))
    setNotebookTitle(item.title)
    setCells(Array.isArray(item.payload.cells)?item.payload.cells as NotebookCell[]:[])
    setDirty(false);initialized.current=true
  }
  useEffect(()=>{
    if(selectedNotebook||initialized.current)return
    if(notebooks.length)pickNotebook(notebooks[0])
  },[notebooks,selectedNotebook])
  useEffect(()=>{
    if(!dirty||!notebookId)return
    const timer=window.setTimeout(()=>{
      setSaving(true)
      void api<Item>('/workspace/records/'+notebookId,
        {title:notebookTitle,payload:{project_id:projectId,cells}},'PATCH')
        .then(()=>{setDirty(false);onMessage('Notebook autosaved')})
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
  const alter=(newCells:NotebookCell[])=>{setCells(newCells);setDirty(true)}
  const addCell=(type:NotebookCell['type'])=>{
    const initial:NotebookCell={id:'cell_'+Date.now().toString(36),type,
      content:type==='markdown'?'Research observation…':'',
      run_id:type==='run'?runs.find(r=>r.kind==='model_run')?.id:undefined}
    alter([...cells,initial])
  }
  const updateCell=(index:number,patch:Partial<NotebookCell>)=>alter(cells.map((c,i)=>
    i===index?{...c,...patch}:c))
  const save=()=>{if(!notebookId)return;perform(()=>api<Item>('/workspace/records/'+notebookId,
      {title:notebookTitle,payload:{project_id:projectId,cells}},'PATCH'),()=>{
        setDirty(false);onMessage('Notebook saved')})}
  const exportNotebook=()=>safeDownload((notebookTitle||'research_notebook')+'.json',
    JSON.stringify({title:notebookTitle,project_id:projectId,cells},null,2),'application/json')
  return <div className="rw-stack">
    <div className="rw-two">
      <Box title="Research projects">
        <p className="rw-help">Group related studies, model references, figures and reports. Organizing a project never creates duplicate market-price data.</p>
        <div className="rw-inline-actions"><input value={name} onChange={e=>setName(e.target.value)}
          placeholder="Project or notebook title"/>
          <button disabled={busy} onClick={createProject}><Plus size={14}/> Project</button>
          <button disabled={busy} onClick={createNotebook}><Plus size={14}/> Notebook</button></div>
        {projects.map(p=><button key={p.id} className={'rw-row '+(p.id===projectId?'active':'')}
          onClick={()=>{setProjectId(p.id);setNotebookId('');initialized.current=true}}>
          <Folder size={17}/><span><strong>{p.title}</strong><small>{p.id}</small></span></button>)}
        {!projects.length&&<Empty title="No projects yet">Create a project for a research question or thesis chapter.</Empty>}
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
      <Field label="Notebook name" value={notebookTitle} onChange={v=>{setNotebookTitle(v);setDirty(true)}}/>
      <div className="rw-button-group">
        <button onClick={()=>addCell('markdown')}><Plus size={14}/> Text / equations</button>
        <button onClick={()=>addCell('run')} disabled={!runs.some(r=>r.kind==='model_run')}>
          <Plus size={14}/> Saved model run</button>
        <button onClick={()=>addCell('chart')}><Plus size={14}/> Figure notes</button>
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
        {cell.type==='run'?<select value={cell.run_id||''}
          onChange={e=>updateCell(i,{run_id:e.target.value})}>
          <option value="">Select a saved model run</option>
          {runs.filter(r=>r.kind==='model_run').map(r=><option key={r.id} value={r.id}>{r.label}</option>)}
        </select>:<textarea rows={cell.type==='markdown'?5:3} value={cell.content||''}
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
          <FileText size={15}/> Generate HTML & Markdown report</button>
      </div>
      {dirty&&<p className="rw-help">Save pending changes before generating a report. Reports freeze the saved notebook version.</p>}
    </Box>}
    <Box title="Generated research reports">
      {records.filter(x=>x.kind==='report'&&!x.trashed).map(item=><div className="rw-list-item" key={item.id}>
        <div><strong>{item.title}</strong><small>Generated {String(item.payload.generated_utc||'').slice(0,16)}</small></div>
        <div className="rw-row-actions">
          <a href={'/api/workspace/reports/'+item.id+'/html'} download><ArrowDownToLine size={15}/> HTML</a>
          <a href={'/api/workspace/reports/'+item.id+'/markdown'} download><ArrowDownToLine size={15}/> MD</a>
        </div></div>)}
      {!records.some(x=>x.kind==='report'&&!x.trashed)&&
        <Empty title="No research reports yet">Create one from a saved research notebook.</Empty>}
    </Box>
  </div>
}

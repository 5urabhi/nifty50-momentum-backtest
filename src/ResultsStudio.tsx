import {useCallback,useEffect,useMemo,useRef,useState} from 'react'
import {Activity,ArrowRight,BarChart3,BookOpen,ChevronDown,Download,
  FlaskConical,Layers3,LoaderCircle,RefreshCw,Save,Search,ShieldAlert,
  ShieldCheck,SlidersHorizontal,X} from 'lucide-react'
import ResearchPlot,{type ResearchPlotData} from './ResearchPlots'
import './results-studio.css'

type Row=Record<string,unknown>
type Kind='model_run'|'research_run'
type Saved={key:string;kind:Kind;id:string;title:string;mode:string;group:string;figures:number;
  dataset_id?:string|null;created?:string}
type ModelList={id:string;title:string;mode:string;group:string;model_id:string;figures:number;
  dataset_id?:string|null;generated_utc?:string}
type IndexList={id:string;name:string;dataset_kind:string;dataset_id?:string;created_utc?:string}
type ModelDetail={run_id:string;model_id:string;title:string;group:string;mode:string;
  formula:string;params:Row;source?:{dataset_id:string;dataset_label:string;source_file:string;
  frequency:string;observations:number;from_date:string;to_date:string;assets:string[]}|null;
  source_sha256?:string;metrics:{label:string;value:unknown;unit:string}[];
  plots:ResearchPlotData[];table:Row[];notes:string[];limitations:string[];
  generated_utc?:string}
type IndexDetail={id:string;meta:{config:Row;metrics_by_split:Record<string,Row>;
  coverage:Row;limitations?:string[];first_price_date?:string;last_price_date?:string;
  generated_utc?:string;input_sha256?:Row};source:Row;returns:Row[];
  latest_weights:{name:string;weight:number}[];rank_ic:Row[];factor_exposures:Row[];
  concentration:Row[];rolling:Row[];cost_sensitivity:Row[];robustness:Row[];
  methodologies:Row[];audit:Row;data_quality:Row;artifacts:string[]}
type Explanation={explanation:string;formula?:string;limitations?:string[];
  warning?:string;assumptions?:string[]}
type CompareResult={plot?:ResearchPlotData;plots?:ResearchPlotData[];warning?:string;
  sources?:Row[];title:string}
type Figure={group:string;plot:ResearchPlotData;insight:string}
type View='brief'|'figures'|'diagnostics'|'robustness'|'evidence'|'compare'
type Props={selectedIndexRunId:string;onSelectIndexRun:(run:string)=>void;
  onModels:()=>void;onExperiments:()=>void;onWorkspace:()=>void;onData:()=>void;onReports:()=>void}
const VIEWS:{id:View;label:string}[]=[
  {id:'brief',label:'Research brief'},{id:'figures',label:'Interactive figures'},
  {id:'diagnostics',label:'Diagnostics'},{id:'robustness',label:'Robustness'},
  {id:'evidence',label:'Sources & methods'},{id:'compare',label:'Compare runs'}
]
const finite=(value:unknown):number|null=>{
  if(value===null||value===undefined||value==='')return null
  const n=typeof value==='number'?value:typeof value==='string'?Number(value):NaN
  return Number.isFinite(n)?n:null
}
const pretty=(v:unknown,digits=3)=>typeof v==='number'&&Number.isFinite(v)
  ?v.toLocaleString('en-US',{maximumFractionDigits:digits}):String(v??'Not recorded')
const label=(v:string)=>v.replaceAll('_',' ').replace(/\b\w/g,s=>s.toUpperCase())
const errorText=async(r:Response)=>{
  try{const v=await r.json() as {detail?:unknown};if(typeof v.detail==='string')return v.detail}catch{}
  return 'Research engine responded with HTTP '+r.status
}
async function fetchJSON<T>(path:string,body?:Row):Promise<T>{
  let r:Response
  try{r=await fetch('/api'+path,{credentials:'same-origin',
    ...(body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})})}
  catch{throw new Error('Local Python engine unreachable. Start QuantLab with bash run.sh.')}
  if(!r.ok)throw new Error(await errorText(r))
  return await r.json() as T
}
function saveFile(name:string,value:string,type:string){
  const url=URL.createObjectURL(new Blob([value],{type}))
  const a=document.createElement('a');a.href=url;a.download=name
  document.body.append(a);a.click();a.remove()
  window.setTimeout(()=>URL.revokeObjectURL(url),1000)
}
const csvCell=(v:unknown)=>'"'+String(v??'').replaceAll('"','""')+'"'
function exportTable(name:string,rows:Row[]){
  if(!rows.length)return
  const columns=[...new Set(rows.flatMap(Object.keys))]
  const csv=[columns.map(csvCell).join(','),...rows.map(row=>columns.map(c=>csvCell(row[c])).join(','))].join('\n')
  saveFile(name,csv,'text/csv')
}
function DataTable({rows,name}:{rows:Row[];name:string}){
  if(!rows.length)return <div className="rs-empty">No saved numerical observations for this analysis. Nothing has been filled in.</div>
  const columns=[...new Set(rows.flatMap(Object.keys))].slice(0,12)
  return <div className="rs-table-block"><div className="rs-table-head">
    <small>{rows.length} saved rows · {columns.length} visible columns</small>
    <button type="button" onClick={()=>exportTable(name+'.csv',rows)}><Download size={14}/> All rows CSV</button>
  </div><div className="rs-table-scroll"><table><thead><tr>{columns.map(c=><th key={c}>{label(c)}</th>)}</tr></thead>
    <tbody>{rows.slice(0,75).map((r,i)=><tr key={i}>{columns.map(c=>
      <td key={c} title={String(r[c]??'')}>{typeof r[c]==='number'?pretty(r[c],5):String(r[c]??'—')}</td>)}</tr>)}</tbody></table></div>
    {rows.length>75&&<small>Previewing 75 rows. CSV exports every saved row in this response.</small>}
  </div>
}
function numericSeries(rows:Row[],title:string,cap=5):ResearchPlotData|null{
  if(rows.length<2)return null
  const columns=[...new Set(rows.flatMap(Object.keys))]
  const xKey=['date','month','period','timestamp','rebalance_date'].find(k=>columns.includes(k))
  const candidates=columns.filter(k=>k!==xKey&&
    rows.reduce((n,r)=>n+(finite(r[k])!==null?1:0),0)>=2).slice(0,cap)
  if(!candidates.length)return null
  const trimmed=rows.slice(0,400)
  return {kind:'line2d',title,x:trimmed.map((r,i)=>String(xKey?r[xKey]??i+1:i+1)),
    x_label:xKey?label(xKey):'Saved observation index',y_label:'Source-reported value (see column)',
    traces:candidates.map(k=>({name:label(k),y:trimmed.map(r=>finite(r[k]))}))}
}
function indexFigures(detail:IndexDetail):Figure[]{
  const frames:Figure[]=[]
  const observed=[] as {date:string;strategy:number;benchmark:number;
    active:number;ddS:number;ddB:number}[]
  let s=100,b=100,highS=100,highB=100
  for(const row of detail.returns){
    const sr=finite(row.strategy_net),br=finite(row.benchmark)
    if(sr===null||br===null||sr<=-1||br<=-1)continue
    s*=1+sr;b*=1+br;highS=Math.max(s,highS);highB=Math.max(b,highB)
    observed.push({date:String(row.date??observed.length+1),strategy:s,benchmark:b,
      active:(sr-br)*100,ddS:100*(s/highS-1),ddB:100*(b/highB-1)})
  }
  if(observed.length>=2){
    const x=observed.map(o=>o.date)
    frames.push({group:'Performance',insight:'Cumulative product of the saved net returns. The base is 100, not invested currency.',
      plot:{kind:'line2d',title:'Net cumulative wealth against benchmark',x,
        x_label:'Saved trading month',y_label:'Index level · base 100',
        traces:[{name:'Strategy net',y:observed.map(o=>o.strategy)},
          {name:'Benchmark',y:observed.map(o=>o.benchmark)}]}})
    frames.push({group:'Performance',insight:'Monthly strategy minus benchmark, measured in percentage points.',
      plot:{kind:'bar2d',title:'Active return by observation',x,
        x_label:'Saved trading month',y_label:'Excess return · percentage points',
        traces:[{name:'Net active return',y:observed.map(o=>o.active)}]}})
    frames.push({group:'Risk',insight:'Drawdown relative to the previous cumulative peak of each saved series.',
      plot:{kind:'line2d',title:'Underwater analysis · strategy vs benchmark',x,
        x_label:'Saved trading month',y_label:'Drawdown · percent',
        traces:[{name:'Strategy',y:observed.map(o=>o.ddS)},
          {name:'Benchmark',y:observed.map(o=>o.ddB)}]}})
  }
  const sources:[string,string,Row[],string][]=[
    ['Factors','Factor rank information coefficient',detail.rank_ic,'Descriptive factor diagnostic; not a significance test.'],
    ['Factors','Time-varying factor exposure',detail.factor_exposures,'Exposure changes require economic interpretation.'],
    ['Risk','Rolling relative risk',detail.rolling,'Only saved rolling observations are displayed.'],
    ['Risk','Concentration through time',detail.concentration,'Review issuer concentration alongside effective holdings.'],
    ['Robustness','Transaction-cost sensitivity',detail.cost_sensitivity,'In-sample sensitivity does not establish performance robustness.'],
    ['Robustness','Parameter robustness grid',detail.robustness,'Each point reflects a saved configuration, not a prospective evaluation.'],
  ]
  for(const [group,title,rows,insight] of sources){
    const plot=numericSeries(rows,title,6)
    if(plot)frames.push({group,plot,insight})
  }
  if(detail.latest_weights.length>=2){
    const top=detail.latest_weights.slice(0,16)
    frames.push({group:'Construction',insight:'Largest saved post-rebalance positions; partial selection, not a complete constituent audit.',
      plot:{kind:'bar2d',title:'Largest portfolio weights',x:top.map(x=>x.name),
        x_label:'Constituent',y_label:'Portfolio weight · fraction',
        traces:[{name:'Weight',y:top.map(x=>x.weight)}]}})
  }
  return frames
}
function descriptiveIndex(rows:Row[]):{name:string;value:string;help:string}[]{
  const valid=rows.flatMap(r=>{
    const s=finite(r.strategy_net),b=finite(r.benchmark)
    return s!==null&&b!==null&&s>-1&&b>-1?[{s,b,active:s-b}]:[]
  })
  if(valid.length<3)return []
  const average=(values:number[])=>values.reduce((a,b)=>a+b,0)/values.length
  const sd=(values:number[])=>{const mean=average(values)
    return Math.sqrt(values.reduce((a,b)=>a+(b-mean)**2,0)/(values.length-1))}
  const a=valid.map(x=>x.active)
  return [
    {name:'Paired monthly samples',value:String(valid.length),help:'Full saved return sequence with both strategy and benchmark observed.'},
    {name:'Mean monthly active return',value:pretty(100*average(a),3)+' pp',help:'Arithmetic average; not a causal estimate.'},
    {name:'Realized tracking error',value:pretty(100*Math.sqrt(12)*sd(a),3)+'%',help:'Sample standard deviation of monthly active returns × sqrt(12).'},
    {name:'Monthly beat rate',value:pretty(100*a.filter(v=>v>0).length/valid.length,1)+'%',
      help:'Fraction of saved months with net strategy return above benchmark.'},
  ]
}
function FigureCard({figure,mode,runKey}:{figure:Figure;mode:string;runKey:string}){
  const [windowSize,setWindowSize]=useState('100')
  const [hidden,setHidden]=useState<string[]>([])
  const holder=useRef<HTMLDivElement|null>(null)
  const p=figure.plot
  const canCrop=p.kind!=='surface3d'&&p.kind!=='heatmap2d'&&(p.x?.length||0)>8
  const visible=useMemo(()=>{
    if(!canCrop)return p
    const size=p.x?.length||0
    const start=Math.max(0,size-Math.ceil(size*Number(windowSize)/100))
    return {...p,x:p.x?.slice(start),y:p.y?.slice(start),
      band:p.band?{lower:p.band.lower.slice(start),upper:p.band.upper.slice(start)}:undefined,
      traces:p.traces?.filter(t=>!hidden.includes(t.name)).map(t=>({...t,y:t.y.slice(start)}))}
  },[p,canCrop,windowSize,hidden])
  const exportFigure=(extension:'svg'|'csv'|'json')=>{
    const base='quantlab_'+runKey.replace(/[^a-z0-9_-]/gi,'_')+'_'+p.title.replace(/[^a-z0-9_-]/gi,'_').slice(0,45)
    if(extension==='json')saveFile(base+'.json',JSON.stringify({plot:p,group:figure.group,insight:figure.insight},null,2),'application/json')
    if(extension==='csv'&&visible.x?.length&&visible.traces?.length){
      const rows=visible.x.map((x,i)=>({x,...Object.fromEntries((visible.traces||[]).map(t=>[t.name,t.y[i]]))}))
      exportTable(base,rows)
    }
    if(extension==='svg'){
      const svg=holder.current?.querySelector('svg')
      if(svg)saveFile(base+'.svg',new XMLSerializer().serializeToString(svg),'image/svg+xml')
    }
  }
  return <article className="rs-figure" ref={holder}>
    <header><span className="rs-kicker">{figure.group} / {p.kind.replaceAll('2d','2D').replaceAll('3d','3D')}</span>
      <div className="rs-figure-actions">{canCrop&&<select value={windowSize}
        aria-label={'Displayed range for '+p.title} onChange={e=>setWindowSize(e.target.value)}>
        <option value="100">All observations</option><option value="50">Last 50%</option><option value="25">Last 25%</option></select>}
        <button title="Export SVG" onClick={()=>exportFigure('svg')}><Download size={14}/> SVG</button>
        <button title="Export data" onClick={()=>exportFigure('csv')} disabled={!p.x||!p.traces?.length}>CSV</button>
        <button title="Export JSON" onClick={()=>exportFigure('json')}>JSON</button></div></header>
    {canCrop&&!!p.traces?.length&&<div className="rs-series" aria-label="Visible series">
      {p.traces.map(t=><button type="button" key={t.name}
        aria-pressed={!hidden.includes(t.name)} className={hidden.includes(t.name)?'muted':''}
        onClick={()=>setHidden(current=>current.includes(t.name)?current.filter(x=>x!==t.name):current.length>=p.traces!.length-1?current:[...current,t.name])}>{t.name}</button>)}</div>}
    <ResearchPlot plot={visible} provenance={mode}/>
    <p className="rs-figure-note"><Activity size={14}/> {figure.insight}</p>
  </article>
}
export default function ResultsStudio({selectedIndexRunId,onSelectIndexRun,onModels,
  onExperiments,onWorkspace,onData,onReports}:Props){
  const [runs,setRuns]=useState<Saved[]>([])
  const [selectedKey,setSelectedKey]=useState('')
  const [loadingList,setLoadingList]=useState(true)
  const [loadingDetail,setLoadingDetail]=useState(false)
  const [message,setMessage]=useState('')
  const [error,setError]=useState('')
  const [model,setModel]=useState<ModelDetail|null>(null)
  const [index,setIndex]=useState<IndexDetail|null>(null)
  const [tab,setTab]=useState<View>('brief')
  const [search,setSearch]=useState('')
  const [group,setGroup]=useState('All figures')
  const [splitName,setSplitName]=useState('')
  const [explainLevel,setExplainLevel]=useState('researcher')
  const [explain,setExplain]=useState<Explanation|null>(null)
  const [quality,setQuality]=useState<Row|null>(null)
  const [qualityBusy,setQualityBusy]=useState(false)
  const [selection,setSelection]=useState<string[]>([])
  const [plotIndex,setPlotIndex]=useState<Record<string,number>>({})
  const [comparison,setComparison]=useState<CompareResult|null>(null)
  const [comparing,setComparing]=useState(false)
  const [layout,setLayout]=useState('overlay')
  const [normalize,setNormalize]=useState('none')
  const [alignment,setAlignment]=useState('intersection')
  const [saved,setSaved]=useState('')
  const [offset,setOffset]=useState({model:0,index:0})
  const [older,setOlder]=useState({model:true,index:true})
  const [paging,setPaging]=useState(false)
  const refresh=useCallback(async(reset=true)=>{
    try{
      const [models,indices]=await Promise.all([
        fetchJSON<{runs:ModelList[]}>('/lab/runs?limit=100&offset='+(reset?0:offset.model)),
        fetchJSON<{runs:IndexList[]}>('/runs?limit=100&offset='+(reset?0:offset.index))])
      const fetched:Saved[]=[
        ...models.runs.map(r=>({key:'model_run:'+r.id,kind:'model_run' as const,id:r.id,title:r.title,
          mode:r.mode,group:r.group,figures:r.figures,dataset_id:r.dataset_id,created:r.generated_utc})),
        ...indices.runs.map(r=>({key:'research_run:'+r.id,kind:'research_run' as const,id:r.id,
          title:r.name,mode:r.dataset_kind==='synthetic'?'synthetic':'historical',
          group:'Multi-Factor Index',figures:1,dataset_id:r.dataset_id,created:r.created_utc}))].sort(
          (a,b)=>(b.created||'').localeCompare(a.created||''))
      setRuns(old=>reset?fetched:[...old,...fetched.filter(r=>!old.some(x=>x.key===r.key))])
      setOffset(old=>reset?{model:models.runs.length,index:indices.runs.length}:
        {model:old.model+models.runs.length,index:old.index+indices.runs.length})
      setOlder({model:models.runs.length===100,index:indices.runs.length===100})
      setError('')
    }catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setLoadingList(false);setPaging(false)}
  },[offset.model,offset.index])
  useEffect(()=>{void refresh()},[]) // initial load; refresh button resets the current paging window
  useEffect(()=>{if(selectedIndexRunId)setSelectedKey('research_run:'+selectedIndexRunId)},[selectedIndexRunId])
  useEffect(()=>{if(!selectedKey&&runs.length)setSelectedKey(runs[0].key)},[selectedKey,runs])
  const active=runs.find(r=>r.key===selectedKey)
  useEffect(()=>{
    let alive=true;setModel(null);setIndex(null);setQuality(null);setExplain(null);setSplitName('');setGroup('All figures')
    if(!active)return
    setLoadingDetail(true);setError('')
    const url=active.kind==='model_run'?'/lab/runs/':'/runs/'
    void fetchJSON<ModelDetail|IndexDetail>(url+encodeURIComponent(active.id)).then(result=>{
      if(!alive)return
      if(active.kind==='model_run')setModel(result as ModelDetail)
      else setIndex(result as IndexDetail)
    }).catch(e=>{if(alive)setError(e instanceof Error?e.message:String(e))})
      .finally(()=>{if(alive)setLoadingDetail(false)})
    return()=>{alive=false}
  },[active?.key])
  useEffect(()=>{
    let alive=true;setExplain(null)
    if(!active)return
    void fetchJSON<Explanation>('/workspace/explain/'+active.kind+'/'+encodeURIComponent(active.id)+
      '?level='+explainLevel).then(r=>{if(alive)setExplain(r)}).catch(()=>{})
    return()=>{alive=false}
  },[active?.key,explainLevel])
  const sourceKind=index?String(index.source.dataset_kind||'unknown'):mode
  const dataId=model?.source?.dataset_id||String(index?.source.dataset_id||active?.dataset_id||'')
  const evidence=sourceKind==='synthetic'?'SEEDED SYNTHETIC DEMONSTRATION':
    sourceKind==='theoretical'?'THEORETICAL / ASSUMED INPUTS':
    sourceKind==='historical'?'OBSERVED HISTORICAL / UNVERIFIED':
    'SOURCE CLASSIFICATION INCOMPLETE'
  const allFigures=useMemo(()=>model?model.plots.map(plot=>({
    group:plot.kind==='surface3d'?'3D mathematical surfaces':
      plot.kind==='heatmap2d'?'Heatmaps':model.group,
    plot,insight:'Numerical output saved by the Python model. Interpret the axes, estimation assumptions and evidence classification.'})):
    index?indexFigures(index):[],[model,index])
  const groups=['All figures',...new Set(allFigures.map(x=>x.group))]
  const figures=allFigures.filter(x=>group==='All figures'||x.group===group)
  const splits=Object.entries(index?.meta.metrics_by_split||{})
  const chosenSplit=splits.find(([name])=>name===splitName)||splits[splits.length-1]
  const primaryMetrics=useMemo(()=>{
    if(model)return model.metrics.map(m=>({name:m.label,value:m.value,unit:m.unit}))
    if(!chosenSplit)return []
    return Object.entries(chosenSplit[1]).filter(([_,v])=>finite(v)!==null).map(([name,value])=>
      ({name:label(name),value,unit:/cagr|drawdown|tracking_error|volatility|return|turnover|hit_rate/.test(name)?'decimal fraction':'reported unit'}))
  },[model,chosenSplit?.[0],index])
  const topMetrics=primaryMetrics.slice(0,5)
  const diagnostics=index?descriptiveIndex(index.returns):[]
  const limitations=(model?.limitations||index?.meta.limitations||[])
  const info=active?.kind==='model_run'?model?.source:null
  const runDetails=model||index
  const selectedForCompare=runs.filter(r=>selection.includes(r.key))
  const doCompare=async()=>{
    setComparing(true);setError('');setComparison(null)
    try{
      const body={title:'QuantLab saved-run comparison',
        selections:selectedForCompare.map(r=>({kind:r.kind,run_id:r.id,plot_index:plotIndex[r.key]||0})),
        normalize,alignment,layout}
      const result=await fetchJSON<CompareResult>('/workspace/compare',body)
      setComparison(result)
    }catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setComparing(false)}
  }
  const saveComparison=async()=>{
    if(!comparison)return
    setComparing(true);setError('')
    try{
      const response=await fetchJSON<{id:string}>('/workspace/records',{
        kind:'comparison',title:comparison.title,
        payload:{selections:selectedForCompare.map(r=>({kind:r.kind,run_id:r.id,plot_index:plotIndex[r.key]||0})),
          normalize,alignment,layout,plot:comparison.plot||null,plots:comparison.plots||[]},
        tags:['results-studio']})
      setSaved(response.id);setMessage('Comparison saved to your Research Workspace library.')
    }catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setComparing(false)}
  }
  const qualityCheck=async()=>{
    if(!dataId)return
    setQualityBusy(true);setError('')
    try{setQuality(await fetchJSON<Row>('/workspace/quality/'+encodeURIComponent(dataId)))}
    catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setQualityBusy(false)}
  }
  const toggleCompare=(key:string)=>{
    setComparison(null);setSaved('')
    setSelection(old=>old.includes(key)?old.filter(x=>x!==key):old.length>=8?old:[...old,key])
  }
  const runList=runs.filter(r=>(r.title+' '+r.group+' '+r.id).toLowerCase().includes(search.toLowerCase()))
  return <div className="rs-root">
    <section className="rs-hero">
      <div><span className="rs-kicker"><Layers3 size={13}/> QUANTLAB / RESULTS INTELLIGENCE</span>
        <h2>Every result, explained.<br/><em>Every claim, traceable.</em></h2>
        <p>Explore the exact saved outputs of your mathematical and index models. Compare evidence, interrogate figures and inspect missing validation before publishing.</p>
      </div>
      <div className="rs-hero-actions"><button type="button" onClick={()=>void refresh(true)}>
        <RefreshCw size={15}/> Refresh saved runs</button><button type="button" className="rs-primary" onClick={onExperiments}>
        <FlaskConical size={15}/> New experiment</button></div>
    </section>
    <div className="rs-step"><span>01 SELECT RUN</span><ArrowRight size={13}/><span>02 EXPLORE RESULTS</span>
      <ArrowRight size={13}/><span>03 VALIDATE & COMPARE</span><ArrowRight size={13}/><span>04 EXPORT EVIDENCE</span></div>
    <section className="rs-explorer">
      <aside className="rs-run-picker"><header><h3>Saved experiments</h3><span>{runs.length}</span></header>
        <label className="rs-search"><Search size={15}/><input value={search} onChange={e=>setSearch(e.target.value)}
          aria-label="Filter saved experiments" placeholder="Find a model or run…"/></label>
        <div className="rs-run-list">{loadingList?<div className="rs-empty"><LoaderCircle size={18}/> Reading local results…</div>:
          runList.map(r=><button key={r.key} type="button"
            className={r.key===selectedKey?'active':''} aria-current={r.key===selectedKey?'true':undefined}
            onClick={()=>{setSelectedKey(r.key);setTab('brief');setComparison(null);
              if(r.kind==='research_run')onSelectIndexRun(r.id)}}>
            <span className="rs-run-icon">{r.kind==='model_run'?<Activity size={15}/>:<BarChart3 size={15}/>}</span>
            <span className="rs-run-text"><strong>{r.title}</strong><small>{r.group}</small>
              <small>{r.mode==='synthetic'?'SYNTHETIC DEMO':r.mode==='theoretical'?'THEORETICAL':'OBSERVED / UNVERIFIED'} · {r.id.slice(0,13)}</small></span>
            <ChevronDown size={13}/></button>)}
          {!loadingList&&!runList.length&&<div className="rs-empty">No saved run matches the filter.</div>}</div>
        {(older.model||older.index)&&<button className="rs-load" disabled={paging}
          onClick={()=>{setPaging(true);void refresh(false)}}>{paging?'Loading archives…':'Load older saved runs'}</button>}
        <button className="rs-load" onClick={onWorkspace}>Manage, archive or delete results <ArrowRight size={14}/></button>
      </aside>
      <div className="rs-main">
        {!active&&!loadingList?<section className="rs-panel rs-welcome"><Layers3 size={34}/>
          <h3>Make your first research result</h3><p>Only completed saved Python runs appear here; QuantLab never supplies a decorative performance series.</p>
          <div><button className="rs-primary" onClick={onModels}>Run mathematical model</button>
          <button onClick={onExperiments}>Run index experiment</button></div></section>:
        <>{loadingDetail&&<div className="rs-loading" role="status"><LoaderCircle size={17}/> Loading saved numerical artifacts…</div>}
          {error&&<div className="rs-error" role="alert"><ShieldAlert size={16}/>{error}
            <button onClick={()=>setError('')} aria-label="Dismiss error"><X size={15}/></button></div>}
          {active&&runDetails&&<><section className="rs-identity"><div>
            <span className="rs-kicker">{active.kind==='model_run'?'MATHEMATICAL MODEL':'MULTI-FACTOR INDEX EXPERIMENT'} · {active.group}</span>
            <h3>{active.title}</h3><p>{active.id} · {active.created?new Date(active.created).toLocaleString():'Saved date not recorded'}</p>
          </div><div className="rs-identity-right"><span className={'rs-evidence '+(sourceKind==='synthetic'?'demo':sourceKind==='theoretical'?'theory':'observed')}>{evidence}</span>
            <button onClick={()=>saveFile('quantlab_'+active.id+'_result.json',
              JSON.stringify(runDetails,null,2),'application/json')}><Download size={14}/> Exact run JSON</button></div></section>
          <nav className="rs-tabs" aria-label="Research results sections">{VIEWS.map(v=>
            <button key={v.id} className={tab===v.id?'active':''}
              aria-current={tab===v.id?'page':undefined} onClick={()=>setTab(v.id)}>{v.label}</button>)}</nav>
          {tab==='brief'&&<div className="rs-stack">
            <div className="rs-kpi-grid">{topMetrics.length?topMetrics.map(m=><article key={m.name}>
              <small>{m.name}</small><strong>{typeof m.value==='number'?pretty(m.value,4):String(m.value??'—')}</strong>
              <span>{m.unit==='decimal fraction'?'Decimal fraction · inspect units':m.unit||'Saved measurement'}</span>
            </article>):<div className="rs-empty">No numerical metrics saved for this run.</div>}</div>
            <div className="rs-two"><section className="rs-panel"><div className="rs-panel-heading"><h3>Research interpretation</h3>
              <select aria-label="Explanation depth" value={explainLevel} onChange={e=>setExplainLevel(e.target.value)}>
                <option value="beginner">Beginner</option><option value="researcher">Researcher</option>
                <option value="mathematical">Mathematical</option></select></div>
              {explain?<><p className="rs-narrative">{explain.explanation}</p>
                {explainLevel==='mathematical'&&explain.formula&&<pre className="rs-formula">{explain.formula}</pre>}
                <p className="rs-small">{explain.warning}</p></>:<p className="rs-small">Research explanation unavailable for this saved run.</p>}
              <div className="rs-check"><ShieldCheck size={16}/> An archived computation is not proof of statistical significance or investable performance.</div>
            </section><section className="rs-panel"><h3>Evidence snapshot</h3>
              <dl className="rs-facts"><div><dt>Evidence class</dt><dd>{evidence}</dd></div>
                <div><dt>Saved figure count</dt><dd>{allFigures.length}</dd></div>
                <div><dt>Dataset ID</dt><dd>{dataId||'Not applicable / not recorded'}</dd></div>
                {info&&<div><dt>Common observations</dt><dd>{info.observations}</dd></div>}
                {index&&<div><dt>Sample window</dt><dd>{index.meta.first_price_date||'—'} → {index.meta.last_price_date||'—'}</dd></div>}
                {model?.source_sha256&&<div><dt>SHA-256 (source)</dt><dd>{model.source_sha256.slice(0,20)}…</dd></div>}
              </dl><button className="rs-link" onClick={()=>setTab('evidence')}>Inspect complete lineage <ArrowRight size={14}/></button>
            </section></div>
            {allFigures.length>0&&<div className="rs-panel"><div className="rs-panel-heading"><h3>Featured computed figure</h3><button onClick={()=>setTab('figures')}>View {allFigures.length} figures <ArrowRight size={14}/></button></div>
              <FigureCard key={active.key+'-featured'} figure={allFigures[0]} runKey={active.id} mode={sourceKind}/></div>}
            {limitations.length>0&&<section className="rs-panel rs-warnings"><h3>Known interpretation limits</h3>
              {limitations.slice(0,6).map((l,i)=><p key={i}><ShieldAlert size={14}/>{l}</p>)}</section>}
          </div>}
          {tab==='figures'&&<div className="rs-stack"><section className="rs-panel">
            <div className="rs-panel-heading"><div><h3>Model-specific figure gallery</h3>
              <p className="rs-small">Hover for source values; focus a chart and use arrow keys. Rotate 3D surfaces with your pointer.</p></div>
              <select aria-label="Figure family" value={group} onChange={e=>setGroup(e.target.value)}>
                {groups.map(g=><option key={g} value={g}>{g}</option>)}</select></div>
            <div className="rs-figures">{figures.map((f,i)=><FigureCard key={active.key+'-'+group+'-'+i}
              figure={f} mode={sourceKind} runKey={active.id}/>)}
              {!figures.length&&<div className="rs-empty">This run has no saved figures in the selected category. Numerical tables may still be available.</div>}</div>
          </section></div>}
          {tab==='diagnostics'&&<div className="rs-stack">
            {diagnostics.length>0&&<div className="rs-kpi-grid">{diagnostics.map(s=><article key={s.name} title={s.help}>
              <small>{s.name}</small><strong>{s.value}</strong><span>{s.help}</span></article>)}</div>}
            <div className="rs-panel"><h3>{model?'Model-calculated diagnostics':'Saved train / validation / test metrics'}</h3>
              {index&&<div className="rs-panel-heading"><p className="rs-small">Use the actual reported split; these estimates are not all interchangeable.</p>
                <select aria-label="Reported validation split" value={chosenSplit?.[0]||''} onChange={e=>setSplitName(e.target.value)}>
                  {splits.map(([name])=><option key={name} value={name}>{label(name)}</option>)}</select></div>}
              <DataTable name="quantlab_model_metrics" rows={model?model.metrics.map(m=>({metric:m.label,value:m.value,unit:m.unit})):
                chosenSplit?Object.entries(chosenSplit[1]).map(([name,value])=>({metric:label(name),value})):[]}/></div>
            {!!model?.table.length&&<section className="rs-panel"><h3>Model output table</h3><DataTable rows={model.table} name="quantlab_model_table"/></section>}
            {!!index?.rank_ic.length&&<section className="rs-panel"><h3>Factor diagnostics</h3><DataTable rows={index.rank_ic} name="quantlab_rank_ic"/></section>}
            {!!index?.rolling.length&&<section className="rs-panel"><h3>Rolling validation</h3><DataTable rows={index.rolling} name="quantlab_rolling"/></section>}
            <div className="rs-warning">Descriptive sample statistics are not p-values or confidence intervals. For hypothesis tests and block bootstrap intervals, open Research Workspace → Statistics & Diagnostics / Research Tools.</div>
            <button className="rs-action" onClick={onWorkspace}><SlidersHorizontal size={15}/> Open statistical diagnostics & validation <ArrowRight size={14}/></button>
          </div>}
          {tab==='robustness'&&<div className="rs-stack">
            {index?.robustness.length?<section className="rs-panel"><h3>Parameter sensitivity · executed rows</h3>
              <DataTable rows={index.robustness} name="quantlab_robustness"/></section>:null}
            {index?.cost_sensitivity.length?<section className="rs-panel"><h3>Transaction costs · executed rows</h3>
              <DataTable rows={index.cost_sensitivity} name="quantlab_cost_sensitivity"/></section>:null}
            {allFigures.filter(f=>f.group==='Robustness').map((f,i)=><FigureCard key={active.key+'-robustness-'+i}
              figure={f} mode={sourceKind} runKey={active.id}/>)}
            {!index?.robustness.length&&!index?.cost_sensitivity.length&&
              <section className="rs-panel rs-welcome"><ShieldAlert size={28}/><h3>No robustness study attached to this saved result</h3>
                <p>Do not infer a successful stress test from a fitted model. Use the existing Python parameter-sweep, chronological holdout and bootstrap tools to produce new saved evidence.</p>
                <button className="rs-primary" onClick={onWorkspace}>Open Research Tools <ArrowRight size={15}/></button>
              </section>}
          </div>}
          {tab==='evidence'&&<div className="rs-stack"><div className="rs-two">
            <section className="rs-panel"><h3>Provenance and source files</h3>
              <dl className="rs-facts"><div><dt>Evidence classification</dt><dd>{evidence}</dd></div>
                <div><dt>Dataset</dt><dd>{info?.dataset_label||dataId||'Not applicable'}</dd></div>
                <div><dt>File</dt><dd>{info?.source_file||'See saved manifest'}</dd></div>
                <div><dt>Frequency</dt><dd>{info?.frequency||'See saved manifest'}</dd></div>
                <div><dt>From / through</dt><dd>{info?info.from_date+' → '+info.to_date:(index?.meta.first_price_date||'—')+' → '+(index?.meta.last_price_date||'—')}</dd></div>
                <div><dt>Source checksum</dt><dd>{model?.source_sha256||'Inspect manifest hashes below'}</dd></div>
              </dl><button onClick={onData} className="rs-link">Open Data Library <ArrowRight size={14}/></button></section>
            <section className="rs-panel"><h3>Source integrity check</h3><p className="rs-small">Inspect data quality using the real Python dataset, without silently filling missing prices.</p>
              <button className="rs-action" disabled={!dataId||qualityBusy} onClick={()=>void qualityCheck()}>
                {qualityBusy?<LoaderCircle size={15}/>:<ShieldCheck size={15}/>} Inspect saved source</button>
              {quality&&<pre className="rs-json">{JSON.stringify(quality,null,2)}</pre>}
              {!dataId&&<p className="rs-warning">Theoretical runs have no observed dataset to validate.</p>}</section></div>
            <section className="rs-panel"><h3>Exact parameters and governing mathematics</h3>
              {model?.formula&&<pre className="rs-formula">{model.formula}</pre>}
              <DataTable rows={Object.entries(model?.params||index?.meta.config||{}).map(([parameter,value])=>({parameter,
                value:typeof value==='object'?JSON.stringify(value):value}))} name="quantlab_parameters"/></section>
            {index&&<section className="rs-panel"><h3>Dataset audit and coverage</h3>
              <pre className="rs-json">{JSON.stringify({coverage:index.meta.coverage,
                audit:index.audit,data_quality:index.data_quality,source_hashes:index.meta.input_sha256},null,2)}</pre></section>}
            <button className="rs-action" onClick={onReports}><BookOpen size={15}/> Build / inspect research report <ArrowRight size={14}/></button>
          </div>}
          {tab==='compare'&&<div className="rs-stack"><div className="rs-two">
            <section className="rs-panel"><h3>Select 2–8 completed runs</h3>
              <p className="rs-small">Overlay requires the same evidence class and compatible axes; incompatible models can be shown in separate panels.</p>
              <div className="rs-compare-list">{runs.map(r=><div key={r.key}>
                <label><input type="checkbox" checked={selection.includes(r.key)} onChange={()=>toggleCompare(r.key)}/>
                  <span><strong>{r.title}</strong><small>{r.group} · {r.mode}</small></span></label>
                {selection.includes(r.key)&&r.figures>1&&<select
                  aria-label={'Figure for '+r.title} value={plotIndex[r.key]||0}
                  onChange={e=>{setPlotIndex(p=>({...p,[r.key]:Number(e.target.value)}));setComparison(null)}}>
                  {Array.from({length:r.figures},(_,i)=><option key={i} value={i}>Figure {i+1}</option>)}</select>}
              </div>)}</div></section>
            <section className="rs-panel"><h3>Comparison design</h3>
              <label className="rs-field">Layout<select value={layout} onChange={e=>{setLayout(e.target.value);setComparison(null)}}>
                <option value="overlay">Same-axis overlay (strict)</option><option value="split">Independent panels</option></select></label>
              <label className="rs-field">Normalization<select value={normalize} onChange={e=>{setNormalize(e.target.value);setComparison(null)}}>
                <option value="none">Original units</option><option value="base100">Base 100</option>
                <option value="zscore">Z-score</option></select></label>
              <label className="rs-field">Observation alignment<select value={alignment} onChange={e=>{setAlignment(e.target.value);setComparison(null)}}>
                <option value="intersection">Shared observations only</option>
                <option value="union">Union (missing remains blank)</option></select></label>
              <button className="rs-primary" disabled={selection.length<2||comparing} onClick={()=>void doCompare()}>
                {comparing?<LoaderCircle size={15}/>:<BarChart3 size={15}/>} Compare selected runs</button>
              {comparison&&<button className="rs-action" disabled={comparing} onClick={()=>void saveComparison()}>
                <Save size={14}/> Save reproducible comparison</button>}
              {saved&&<p className="rs-small">Saved comparison ID: {saved}</p>}
            </section></div>
            {comparison&&<section className="rs-panel rs-compare-output"><h3>{comparison.title}</h3>
              {comparison.plot&&<FigureCard key={'comparison-'+selection.join('-')} mode="historical"
                runKey="comparison" figure={{group:'Comparison',plot:comparison.plot,insight:'Aligned saved numerical outputs. Normalization changes interpretation.'}}/>}
              {comparison.plots&&<div className="rs-figures">{comparison.plots.map((plot,i)=><FigureCard
                key={i} mode={selectedForCompare[i]?.mode||'unknown'} runKey="comparison"
                figure={{group:'Independent panel',plot,insight:'Separate scale and provenance. Do not compare raw heights across units.'}}/>)}</div>}
              <p className="rs-warning">{comparison.warning}</p>
              {!!comparison.sources?.length&&<DataTable rows={comparison.sources} name="quantlab_comparison_sources"/></section>}
            <button onClick={onWorkspace} className="rs-link">Advanced Compare & Graph Studio <ArrowRight size={14}/></button>
          </div>}
        </>}</>}
      </div>
    </section>
    {message&&<div className="rs-toast" role="status">{message}<button onClick={()=>setMessage('')}><X size={14}/></button></div>}
  </div>
}

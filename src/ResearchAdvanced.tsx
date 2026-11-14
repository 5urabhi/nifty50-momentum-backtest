import {useEffect,useMemo,useState} from 'react'
import {BarChart3,Download,LoaderCircle,Play,Save,ShieldCheck} from 'lucide-react'
import ResearchPlot,{type ResearchPlotData,type ResearchTrace} from './ResearchPlots'

type Json=Record<string,unknown>
type Dataset={id:string;label:string;has_prices:boolean}
type RecordItem={id:string;kind:string;title:string;payload:Json;trashed:boolean}
type Source={dataset_id:string;dataset:string;source_sha256:string;source_file:string;frequency:string;
  price_currency?:string;currency_declared_by_user?:boolean;currency_verified_by_source?:boolean}
type PlotOutput={plot:ResearchPlotData;source:Source;sample_observations:number;displayed_observations:number;
  settings:Json;warning:string}
type Columns={source:Source;columns:string[];total_columns:number;total_dates:number}
type Diagnostics={asset:string;statistics:Record<string,number|null>;
  interpretation:Record<string,string>;warning:string}
type Attribution={target:string;factor_proxies:{factor_proxy:string;beta:number;standard_error:number;
  t_stat:number;nominal_p_value:number}[];train_observations:number;holdout_observations:number;
  holdout_r2_vs_train_mean:number|null;plot:ResearchPlotData;warning:string}
type Inference={studies:{study_id:string;name:string;observations:number;active_mean:number;
  nominal_p_value:number|null;holm_adjusted_p_value?:number;
  bootstrap_mean_ci95:number[];newey_west_se:number}[];warning:string}
type Props={datasets:Dataset[];selectedDataset:string;onSelectDataset:(s:string)=>void;
  records:RecordItem[];onMessage:(s:string)=>void;onError:(s:string)=>void;onChanged:()=>void}
const COLORS=['#66e3c3','#ffca83','#78a8ff','#ce9dff','#ff8c9b','#a2f6e2']
const fmt=(v:unknown)=>typeof v==='number'&&Number.isFinite(v)?v.toLocaleString(undefined,{maximumFractionDigits:5}):String(v??'N/A')
async function request<T>(path:string,body?:object){
  const r=await fetch('/api/workspace/'+path,body?{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(body)}:undefined)
  if(!r.ok){const e=await r.json().catch(()=>({detail:'Calculation failed'})) as {detail?:string}
    throw new Error(e.detail||'Calculation failed')}
  return r.json() as Promise<T>
}
function save(name:string,text:string,mime:string){
  const url=URL.createObjectURL(new Blob([text],{type:mime}))
  const a=document.createElement('a');a.href=url;a.download=name
  document.body.appendChild(a);a.click();a.remove()
  window.setTimeout(()=>URL.revokeObjectURL(url),500)
}
function Field({title,value,onChange,type='text'}:{title:string;value:string;
  onChange:(s:string)=>void;type?:string}){
  return <label className="rw-field"><span>{title}</span>
    <input type={type} value={value} onChange={e=>onChange(e.target.value)}/></label>
}
function Choice({title,value,onChange,options}:{title:string;value:string;
  onChange:(s:string)=>void;options:{id:string;name:string}[]}){
  return <label className="rw-field"><span>{title}</span><select value={value}
    onChange={e=>onChange(e.target.value)}>{options.map(x=>
      <option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
}
const opt=(a:string[])=>a.map(id=>({id,name:id.replaceAll('_',' ')}))
function FigureDownload({plot,source}:{plot:ResearchPlotData;source:Source}){
  const svg=()=>{const e=document.querySelector('.ra-result svg') as SVGElement|null
    return e?new XMLSerializer().serializeToString(e):null}
  const html=()=>{
    const raw=svg();if(!raw)return
    const title=plot.title.replace(/[<>&"']/g,'')
    const script="(()=>{const e=document.querySelector('svg'),r=document.querySelector('#reset');if(!e||!r)return;"
      +"const origin=e.getAttribute('viewBox'),read=()=>e.getAttribute('viewBox').split(' ').map(Number);"
      +"let start=null;e.addEventListener('wheel',v=>{v.preventDefault();const b=read(),f=v.deltaY>0?1.1:.9;"
      +"const w=Math.min(4000,Math.max(70,b[2]*f)),h=w*b[3]/b[2];"
      +"e.setAttribute('viewBox',[b[0]+(b[2]-w)/2,b[1]+(b[3]-h)/2,w,h].join(' '))},{passive:false});"
      +"e.addEventListener('pointerdown',v=>{start={x:v.clientX,y:v.clientY,b:read()};e.setPointerCapture(v.pointerId)});"
      +"e.addEventListener('pointermove',v=>{if(!start)return;const b=start.b,bb=e.getBoundingClientRect();"
      +"e.setAttribute('viewBox',[b[0]-(v.clientX-start.x)*b[2]/bb.width,"
      +"b[1]-(v.clientY-start.y)*b[3]/bb.height,b[2],b[3]].join(' '))});"
      +"e.addEventListener('pointerup',()=>start=null);r.addEventListener('click',()=>e.setAttribute('viewBox',origin))})();"
    save('quantlab_figure.html','<!doctype html><html lang="en"><meta charset="utf-8"><title>'+title+
      '</title><style>body{font:16px system-ui;background:#071723;color:#cbebea;margin:3em auto;max-width:1050px;padding:1em}svg{max-width:100%;height:auto}button{padding:.7em}</style><h1>'+title+
      '</h1><p>Saved numerical view. Drag to pan, wheel to zoom, hover points for values.</p><button id="reset">Reset view</button><main>'+raw+
      '</main><script>'+script+'</script></html>','text/html')
  }
  const csv=()=>{
    if(!plot.x)return
    const traces=plot.traces||[]
    const escape=(x:unknown)=>'"'+String(x??'').replaceAll('"','""')+'"'
    const rows=[[(plot.x_label||'X'),...traces.map(t=>t.name+' ['+(plot.y_label||'units unspecified')+']')].map(escape).join(','),
      ...plot.x.map((x,i)=>[x,...traces.map(t=>t.y[i])].map(escape).join(','))]
    save('quantlab_figure.csv',rows.join('\n'),'text/csv')
  }
  const png=()=>{
    const raw=svg();if(!raw)return
    const url=URL.createObjectURL(new Blob([raw],{type:'image/svg+xml'})),image=new Image()
    image.onload=()=>{
      const canvas=document.createElement('canvas');canvas.width=1320;canvas.height=710
      const ctx=canvas.getContext('2d')
      if(ctx){ctx.fillStyle='#091927';ctx.fillRect(0,0,1320,710);ctx.drawImage(image,0,0,1320,710)
        canvas.toBlob(blob=>{if(!blob)return;const link=URL.createObjectURL(blob)
          const a=document.createElement('a');a.href=link;a.download='quantlab_figure.png';a.click()
          window.setTimeout(()=>URL.revokeObjectURL(link),800)},'image/png')}
      URL.revokeObjectURL(url)
    }
    image.onerror=()=>URL.revokeObjectURL(url);image.src=url
  }
  return <div className="rw-button-group">
    <button onClick={()=>{const s=svg();if(s)save('quantlab_figure.svg',s,'image/svg+xml')}}><Download size={14}/> SVG</button>
    <button onClick={png}><Download size={14}/> PNG</button>
    <button onClick={csv} disabled={!plot.x||!plot.traces?.length}><Download size={14}/> CSV</button>
    <button onClick={()=>save('quantlab_figure.json',JSON.stringify({plot,source},null,2),'application/json')}><Download size={14}/> JSON</button>
    <button onClick={html} disabled={plot.kind==='surface3d'}><Download size={14}/> Interactive HTML</button>
  </div>
}
function PlotBuilder({datasets,selectedDataset,onSelectDataset,records,onMessage,onError,onChanged}:Props){
  const [columns,setColumns]=useState<Columns|null>(null)
  const [fields,setFields]=useState<string[]>([])
  const [kind,setKind]=useState('line')
  const [transform,setTransform]=useState('return')
  const [priceCurrency,setPriceCurrency]=useState('unspecified')
  const [first,setFirst]=useState('')
  const [last,setLast]=useState('')
  const [lookback,setLookback]=useState('20')
  const [title,setTitle]=useState('Observed research graph')
  const [caption,setCaption]=useState('')
  const [plot,setPlot]=useState<PlotOutput|null>(null)
  const [hidden,setHidden]=useState<string[]>([])
  const [colors,setColors]=useState<Record<string,string>>({})
  const [logY,setLogY]=useState(false)
  const [xAxis,setXAxis]=useState('')
  const [yAxis,setYAxis]=useState('')
  const [marker,setMarker]=useState('')
  const [markerLabel,setMarkerLabel]=useState('')
  const [regionStart,setRegionStart]=useState('')
  const [regionEnd,setRegionEnd]=useState('')
  const [regionLabel,setRegionLabel]=useState('')
  const [projects,setProjects]=useState<{id:string;title:string}[]>([])
  const [project,setProject]=useState('')
  const [savedChart,setSavedChart]=useState('')
  const [notebook,setNotebook]=useState('')
  const [busy,setBusy]=useState(false)
  useEffect(()=>{
    let active=true;setColumns(null);setPlot(null);setFields([])
    if(selectedDataset)void request<Columns>('plot-builder/columns/'+encodeURIComponent(selectedDataset))
      .then(x=>{if(active){setColumns(x);setFields(x.columns.slice(0,2))}})
      .catch(e=>{if(active)onError(e instanceof Error?e.message:String(e))})
    return()=>{active=false}
  },[selectedDataset,onError])
  useEffect(()=>{void request<{records:{id:string;title:string}[]}>('records?kind=project')
    .then(r=>setProjects(r.records)).catch(()=>{})},[])
  const toggle=(v:string)=>{
    const next=fields.includes(v)?fields.filter(k=>k!==v):
      fields.length<18?[...fields,v]:fields
    setFields(next)
    if((['histogram','kde','qq'].includes(kind)&&next.length!==1)||
       (kind==='scatter'&&next.length!==2)||
       (kind==='correlation'&&next.length<2))setKind('line')
  }
  const allowedKinds=['line','scatter','histogram','kde','qq','drawdown','cumulative',
    'rolling_volatility','correlation'].filter(v=>
      ['histogram','kde','qq'].includes(v)?fields.length===1:
      v==='scatter'?fields.length===2:v==='correlation'?fields.length>=2:true)
  const suggested=fields.length===1?['line','histogram','kde','qq','rolling_volatility']:
    fields.length===2?['line','scatter','correlation','rolling_volatility']:
    ['line','correlation','rolling_volatility']
  const build=async()=>{
    setBusy(true)
    try{
      const result=await request<PlotOutput>('plot-builder',{dataset_id:selectedDataset,fields,
        kind,transform,price_currency:priceCurrency,first:first||null,last:last||null,lookback:Number(lookback),title})
      setPlot(result);setColors({});setHidden([]);setLogY(false)
      setXAxis(result.plot.x_label||'');setYAxis(result.plot.y_label||'')
      onMessage('Observed figure ready. The canonical dataset has not been modified.')
    }catch(e){onError(e instanceof Error?e.message:String(e))}
    finally{setBusy(false)}
  }
  const display=useMemo(()=>{
    if(!plot)return null
    const traces=(plot.plot.traces||[]).filter(t=>!hidden.includes(t.name))
      .map((t,i):ResearchTrace=>({...t,color:colors[t.name]||COLORS[i%COLORS.length],
        y:t.y.map(v=>!logY?v:v!==null&&v>0?Math.log10(v):null)}))
    return {...plot.plot,title,x_label:xAxis||plot.plot.x_label,
      y_label:logY?'log10('+yAxis+')':yAxis||plot.plot.y_label,
      traces,
      annotations:marker&&markerLabel&&plot.plot.x?.some(x=>String(x)===marker)?
        [{x:marker,label:markerLabel}]:[],
      regions:regionStart&&regionEnd&&regionLabel&&plot.plot.x?.some(x=>String(x)===regionStart)&&
        plot.plot.x?.some(x=>String(x)===regionEnd)?
        [{start:regionStart,end:regionEnd,label:regionLabel}]:[]}
  },[plot,title,xAxis,yAxis,hidden,colors,logY,marker,markerLabel,
      regionStart,regionEnd,regionLabel])
  const persist=async()=>{
    if(!display||!plot)return
    setBusy(true)
    try{
      const item=await request<{id:string}>('records',{kind:'chart',title,
        payload:{plot:display,annotation:caption,project_id:project||null,
          source:plot.source,settings:plot.settings,sample_observations:plot.sample_observations},
        tags:['plot-builder']})
      setSavedChart(item.id)
      onChanged();onMessage('Graph and source checksum saved to the research library.')
    }catch(e){onError(e instanceof Error?e.message:String(e))}
    finally{setBusy(false)}
  }
  const attach=async()=>{
    if(!savedChart||!notebook)return
    setBusy(true)
    try{
      await request('notebooks/'+encodeURIComponent(notebook)+'/attach',
        {kind:'chart',source_id:savedChart})
      onChanged();onMessage('Saved graph added directly to your report notebook.')
    }catch(e){onError(e instanceof Error?e.message:String(e))}
    finally{setBusy(false)}
  }
  return <div className="rw-stack">
    <div className="rw-two">
      <section className="rw-box">
        <header className="rw-box-head"><h3>General-purpose Plot Builder</h3></header>
        <p className="rw-help">Choose the actual numeric columns and dates. No fake observations or duplicated market-data files.</p>
        <Choice title="Observed market dataset" value={selectedDataset} onChange={onSelectDataset}
          options={[{id:'',name:'Select a dataset'},...datasets.filter(d=>d.has_prices&&d.id!=='synthetic')
            .map(d=>({id:d.id,name:d.label}))]}/>
        {selectedDataset&&!columns&&<p>Inspecting available columns…</p>}
        {columns&&<><p className="rw-help">{columns.total_columns} available columns · {columns.total_dates} saved prices</p>
          <div className="ra-column-picker">{columns.columns.map(c=><label key={c}>
            <input type="checkbox" checked={fields.includes(c)} onChange={()=>toggle(c)}/>{c}</label>)}</div></>}
        <div className="rw-form-grid">
          <Choice title="Graph type" value={kind} onChange={setKind} options={opt(allowedKinds)}/>
          <p className="rw-help">Recommended for {fields.length} selected series: {suggested
            .filter(x=>allowedKinds.includes(x)).map(x=>x.replaceAll('_',' ')).join(', ')}.
            Incompatible plot types are disabled.</p>
          <Choice title="Transformation" value={transform} onChange={setTransform}
            options={opt(['price','return','log_return','base100','zscore'])}/>
          <Choice title="Price currency (user declared)" value={priceCurrency}
            onChange={setPriceCurrency} options={[
              {id:'unspecified',name:'Unknown / no currency label'},
              {id:'INR',name:'₹ INR'},{id:'USD',name:'$ USD'},
              {id:'EUR',name:'€ EUR'},{id:'GBP',name:'£ GBP'}]}/>
          <Field title="Start date" value={first} onChange={setFirst} type="date"/>
          <Field title="End date" value={last} onChange={setLast} type="date"/>
          <Field title="Rolling observations" value={lookback} onChange={setLookback} type="number"/>
          <Field title="Title" value={title} onChange={setTitle}/>
        </div>
        <button className="rw-primary" disabled={busy||!columns||!fields.length}
          onClick={()=>void build()}>{busy?<LoaderCircle size={15}/>:<Play size={15}/>} Plot selected observations</button>
        <p className="rw-help">Price currency is declared by the user, not verified by the provider. Raw return and volatility values remain decimal fractions (0.01 means 1%); Sharpe and beta are unitless. Base-100 index points are not money.</p>
        <p className="rw-help">Scatter: exactly two columns. Histogram, KDE and Q–Q: one column. Correlation: at least two columns. Missing returns are never forward-filled.</p>
      </section>
      <section className="rw-box">
        <header className="rw-box-head"><h3>Graph Studio · Edit & annotate</h3></header>
        {!display?<p className="rw-help">Create a plot first to edit its display, notes, colors and source-linked saved layout.</p>:
        <><div className="rw-form-grid">
          <Field title="X-axis label" value={xAxis} onChange={setXAxis}/>
          <Field title="Y-axis label" value={yAxis} onChange={setYAxis}/>
          <Field title="X marker (actual observed date/value)" value={marker} onChange={setMarker}/>
          <Field title="Marker caption" value={markerLabel} onChange={setMarkerLabel}/>
          <Field title="Highlight region first observed X value" value={regionStart}
            onChange={setRegionStart}/>
          <Field title="Highlight region last observed X value" value={regionEnd}
            onChange={setRegionEnd}/>
          <Field title="Highlighted region caption" value={regionLabel}
            onChange={setRegionLabel}/>
        </div>
        <label className="rw-inline"><input type="checkbox" checked={logY} onChange={e=>setLogY(e.target.checked)}/>
          Log10 transform positive Y; omit nonpositive points</label>
        <div className="ra-traces">{(plot?.plot.traces||[]).map(t=><label className="ra-trace" key={t.name}>
          <span><input type="checkbox" checked={!hidden.includes(t.name)}
            onChange={e=>setHidden(old=>e.target.checked?old.filter(x=>x!==t.name):[...old,t.name])}/>{t.name}</span>
          <input type="color" value={colors[t.name]||'#66e3c3'} aria-label={'Color '+t.name}
            onChange={e=>setColors(old=>({...old,[t.name]:e.target.value}))}/></label>)}</div>
        <label className="rw-field"><span>Interpretation and findings</span><textarea rows={4}
          value={caption} onChange={e=>setCaption(e.target.value)}/></label>
        <Choice title="Save under research project" value={project} onChange={setProject}
          options={[{id:'',name:'Unassigned'},...projects.map(p=>({id:p.id,name:p.title}))]}/>
        <button className="rw-primary" disabled={busy} onClick={()=>void persist()}><Save size={15}/> Save chart</button>
        {savedChart&&<div className="rw-form-grid">
          <Choice title="Add saved chart to report notebook" value={notebook} onChange={setNotebook}
            options={[{id:'',name:'Choose notebook'},...records
              .filter(x=>x.kind==='notebook'&&!x.trashed)
              .map(x=>({id:x.id,name:x.title}))]}/>
          <div className="rw-inline-actions"><button disabled={busy||!notebook}
            onClick={()=>void attach()}><Save size={14}/> Add to report</button></div>
        </div>}</>}
      </section>
    </div>
    {display&&plot&&<section className="rw-box ra-result">
      <ResearchPlot plot={display}/>{caption&&<p className="rw-note">{caption}</p>}
      <p className="rw-help"><ShieldCheck size={14}/> {plot.source.dataset} · SHA-256 {plot.source.source_sha256.slice(0,16)}… · {plot.sample_observations} observations, {plot.displayed_observations} displayed</p>
      <FigureDownload plot={display} source={plot.source}/>
      <p className="rw-caution">{plot.warning}</p>
    </section>}
  </div>
}
function StatisticPanel({datasets,selectedDataset,onSelectDataset,records,onError,onMessage}:Props){
  const [view,setView]=useState<'diagnostics'|'attribution'|'inference'>('diagnostics')
  const [columns,setColumns]=useState<string[]>([])
  const [asset,setAsset]=useState('')
  const [target,setTarget]=useState('')
  const [factorNames,setFactorNames]=useState<string[]>([])
  const [studies,setStudies]=useState<string[]>([])
  const [train,setTrain]=useState('.70')
  const [analysis,setAnalysis]=useState<Diagnostics|Attribution|Inference|null>(null)
  const [busy,setBusy]=useState(false)
  useEffect(()=>{
    let active=true;setColumns([]);setAnalysis(null)
    if(selectedDataset)void request<Columns>('plot-builder/columns/'+encodeURIComponent(selectedDataset))
      .then(r=>{if(active){setColumns(r.columns);setAsset(r.columns[0]||'');
        setTarget(r.columns[0]||'');setFactorNames(r.columns.slice(1,3))}}).catch(()=>{})
    return()=>{active=false}
  },[selectedDataset])
  const toggle=(x:string,current:string[],set:(v:string[])=>void,max:number)=>
    set(current.includes(x)?current.filter(y=>y!==x):current.length<max?[...current,x]:current)
  const compute=async()=>{
    setBusy(true)
    try{
      const next=view==='diagnostics'?
        await request<Diagnostics>('diagnostics',{dataset_id:selectedDataset,asset}):
        view==='attribution'?
        await request<Attribution>('factor-attribution',{dataset_id:selectedDataset,target,
          factors:factorNames,training_fraction:Number(train)}):
        await request<Inference>('significance',{study_ids:studies,seed:2026})
      setAnalysis(next);onMessage('Statistical result ready, with assumptions and limitations.')
    }catch(e){onError(e instanceof Error?e.message:String(e))}
    finally{setBusy(false)}
  }
  const saved=records.filter(r=>r.kind==='study'&&!r.trashed&&
    typeof r.payload.test_observations==='number')
  return <div className="rw-stack">
    <section className="rw-box">
      <header className="rw-box-head"><h3>Statistical Significance & Diagnostics Center</h3></header>
      <div className="rw-segments">{(['diagnostics','attribution','inference'] as const).map(x=>
        <button key={x} className={view===x?'active':''} onClick={()=>{setView(x);setAnalysis(null)}}>
          {x==='diagnostics'?'Model diagnostics':x==='attribution'?'Return-series factor proxies':'Significance & uncertainty'}</button>)}</div>
      {view!=='inference'&&<Choice title="Observed dataset" value={selectedDataset} onChange={onSelectDataset}
        options={[{id:'',name:'Select a dataset'},...datasets.filter(d=>d.has_prices&&d.id!=='synthetic')
          .map(d=>({id:d.id,name:d.label}))]}/>}
      {view==='diagnostics'&&<Choice title="Observed price series" value={asset} onChange={setAsset}
        options={opt(columns)}/>}
      {view==='attribution'&&<>
        <Choice title="Target price series" value={target} onChange={setTarget} options={opt(columns)}/>
        <p className="rw-help">Select 1–6 other observed series to act as regression proxies, not publication-dated fundamental factors.</p>
        <div className="ra-column-picker">{columns.filter(v=>v!==target).map(v=>
          <label key={v}><input type="checkbox" checked={factorNames.includes(v)}
            onChange={()=>toggle(v,factorNames,setFactorNames,6)}/>{v}</label>)}</div>
        <Field title="Training share (0.50–0.85)" value={train} onChange={setTrain} type="number"/>
      </>}
      {view==='inference'&&<>
        <p className="rw-help">Select up to six independent saved chronological evaluation studies. QuantLab reports Newey–West standard errors, block-bootstrap intervals and Holm corrections.</p>
        <div className="ra-column-picker">{saved.map(item=><label key={item.id}>
          <input type="checkbox" checked={studies.includes(item.id)}
            onChange={()=>toggle(item.id,studies,setStudies,6)}/>{item.title}</label>)}</div>
        {!saved.length&&<p className="rw-caution">First run a chronological portfolio validation in Research Tools.</p>}
      </>}
      <button className="rw-primary" disabled={busy||(view!=='inference'&&!selectedDataset)||
        (view==='attribution'&&!factorNames.length)||(view==='inference'&&!studies.length)}
        onClick={()=>void compute()}>{busy?<LoaderCircle size={15}/>:<Play size={15}/>}
        Calculate actual statistical evidence</button>
    </section>
    {view==='diagnostics'&&analysis&&'statistics' in analysis&&
      <section className="rw-box"><h3>Observed diagnostics · {analysis.asset}</h3>
        <div className="rw-stats">{Object.entries(analysis.statistics).map(([k,v])=>
          <div key={k}><small>{k.replaceAll('_',' ')}</small><strong>{fmt(v)}</strong></div>)}</div>
        {Object.entries(analysis.interpretation).map(([k,v])=><p className="rw-note" key={k}>
          <strong>{k.replaceAll('_',' ')}</strong> · {v}</p>)}
        <p className="rw-caution">{analysis.warning}</p>
        <button onClick={()=>save('quantlab_diagnostics.json',JSON.stringify(analysis,null,2),'application/json')}>
          <Download size={14}/> Export diagnostics</button>
      </section>}
    {view==='attribution'&&analysis&&'factor_proxies' in analysis&&
      <section className="rw-box"><h3>Chronological factor-proxy attribution · {analysis.target}</h3>
        <div className="rw-stats"><div><small>Training rows</small><strong>{analysis.train_observations}</strong></div>
          <div><small>Later holdout rows</small><strong>{analysis.holdout_observations}</strong></div>
          <div><small>Holdout R²</small><strong>{fmt(analysis.holdout_r2_vs_train_mean)}</strong></div></div>
        <div className="rw-scroll"><table><thead><tr><th>Proxy</th><th>Beta</th><th>Standard error</th><th>t statistic</th><th>Nominal p</th></tr></thead>
          <tbody>{analysis.factor_proxies.map(r=><tr key={r.factor_proxy}><td>{r.factor_proxy}</td>
            <td>{fmt(r.beta)}</td><td>{fmt(r.standard_error)}</td><td>{fmt(r.t_stat)}</td>
            <td>{fmt(r.nominal_p_value)}</td></tr>)}</tbody></table></div>
        <ResearchPlot plot={analysis.plot}/><p className="rw-caution">{analysis.warning}</p>
        <button onClick={()=>save('quantlab_factor_proxies.json',JSON.stringify(analysis,null,2),'application/json')}>
          <Download size={14}/> Export attribution</button>
      </section>}
    {view==='inference'&&analysis&&'studies' in analysis&&
      <section className="rw-box"><h3>Risk-adjusted inference and multiple-testing control</h3>
        <div className="rw-scroll"><table><thead><tr><th>Study</th><th>N</th><th>Active mean</th>
          <th>HAC standard error</th><th>Nominal p</th><th>Holm p</th><th>Bootstrap interval</th></tr></thead><tbody>
          {analysis.studies.map(r=><tr key={r.study_id}><td>{r.name}</td><td>{r.observations}</td>
            <td>{fmt(r.active_mean)}</td><td>{fmt(r.newey_west_se)}</td>
            <td>{fmt(r.nominal_p_value)}</td><td>{fmt(r.holm_adjusted_p_value)}</td>
            <td>{r.bootstrap_mean_ci95.map(fmt).join(' – ')}</td></tr>)}
        </tbody></table></div><p className="rw-caution">{analysis.warning}</p>
        <button onClick={()=>save('quantlab_inference.json',JSON.stringify(analysis,null,2),'application/json')}>
          <Download size={14}/> Export inference</button></section>}
  </div>
}
export default function ResearchAdvanced(props:Props){
  const [view,setView]=useState<'plot'|'statistics'>('plot')
  return <div className="rw-stack">
    <div className="rw-segments"><button className={view==='plot'?'active':''} onClick={()=>setView('plot')}>
      <BarChart3 size={15}/> General Plot Builder</button>
      <button className={view==='statistics'?'active':''} onClick={()=>setView('statistics')}>
        <ShieldCheck size={15}/> Statistics & Diagnostics</button></div>
    {view==='plot'?<PlotBuilder {...props}/>:<StatisticPanel {...props}/>}
  </div>
}

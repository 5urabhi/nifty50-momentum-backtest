import {useEffect, useMemo, useRef, useState} from 'react'

export type ResearchTrace={name:string;y:(number|null)[];color?:string}
export type ResearchPlotData={
  kind:string;title:string;x?:(string|number)[];y?:number[];
  traces?:ResearchTrace[];x_label?:string;y_label?:string;
  z_label?:string;z?:number[][];band?:{lower:number[];upper:number[]};
  labels?:string[];row_labels?:string[];scale?:string;values?:number[][];threshold?:number;
  annotations?:{x:string|number;label:string}[];
  regions?:{start:string|number;end:string|number;label:string}[]
}
const COLORS=['#66e3c3','#ffca83','#78a8ff','#ce9dff','#ff8c9b','#a2f6e2']
const finite=(n:unknown):n is number=>typeof n==='number'&&Number.isFinite(n)
const fmt=(v:number)=>Math.abs(v)<.001&&v!==0?v.toExponential(1):Math.abs(v)>1000?v.toLocaleString('en-US',{maximumFractionDigits:0}):v.toLocaleString('en-US',{maximumFractionDigits:3})
const clamp=(v:number,l:number,h:number)=>Math.min(h,Math.max(l,v))
const GRID_LEFT=70,GRID_RIGHT=830,GRID_TOP=22,GRID_BOTTOM=280
function yBounds(plot:ResearchPlotData){
  const ys=(plot.traces||[]).flatMap(t=>t.y).filter(finite)
  if(plot.kind==='scatter2d'&&plot.y)ys.push(...plot.y.filter(finite))
  if(plot.band){ys.push(...plot.band.lower.filter(finite),...plot.band.upper.filter(finite))}
  if(!ys.length)return [0,1] as const
  let lo=Math.min(...ys),hi=Math.max(...ys)
  if(lo===hi){lo-=Math.max(.01,Math.abs(lo)*.07);hi+=Math.max(.01,Math.abs(hi)*.07)}
  const pad=(hi-lo)*.07
  return [lo-pad,hi+pad] as const
}
function Canvas2D({plot,syncHover=true}:{plot:ResearchPlotData;syncHover?:boolean}){
  const x=plot.x||[]
  const [activeIndex,setActiveIndex]=useState<number|null>(null)
  const [pinned,setPinned]=useState(false)
  useEffect(()=>{
    if(!syncHover)return
    const handler=(event:Event)=>{
      const target=(event as CustomEvent<{x:string|null}>).detail?.x
      if(pinned)return
      if(target===null){setActiveIndex(null);return}
      if(typeof target==='string'){
        const match=x.findIndex(v=>String(v)===target)
        if(match>=0)setActiveIndex(match)
      }
    }
    window.addEventListener('quantlab:chart-cursor',handler)
    return()=>window.removeEventListener('quantlab:chart-cursor',handler)
  },[syncHover,pinned,plot.x])
  const emitCursor=(index:number|null)=>{
    if(!syncHover)return
    window.dispatchEvent(new CustomEvent('quantlab:chart-cursor',{
      detail:{x:index===null?null:String(x[index])}}))
  }
  const width=GRID_RIGHT-GRID_LEFT,height=GRID_BOTTOM-GRID_TOP
  const [lo,hi]=useMemo(()=>yBounds(plot),[plot])
  const xp=(i:number)=>GRID_LEFT+(x.length<2?.5:i/(x.length-1))*width
  const yp=(value:number)=>GRID_BOTTOM-(value-lo)/(hi-lo)*height
  const traces=plot.traces||[]
  const numerical=x.every(finite)
  const [minX,maxX]=numerical&&x.length>1?[Math.min(...(x as number[])),Math.max(...(x as number[]))]:[0,1]
  const xcoord=(i:number)=>numerical&&maxX>minX
    ?GRID_LEFT+(Number(x[i])-minX)/(maxX-minX)*width:xp(i)
  const isBar=plot.kind==='bar2d'||plot.kind==='histogram2d'
  const path=(v:(number|null)[])=>v.map((y,i)=>{
    if(!finite(y))return null
    return (i&&finite(v[i-1])?'L':'M')+xcoord(i).toFixed(2)+','+yp(y).toFixed(2)
  }).filter(Boolean).join(' ')
  const ticks=[0,.25,.5,.75,1]
  return <div className="ql-plot">
    <svg viewBox="0 0 880 350" className="ql-svg-chart" role="img" tabIndex={0}
      aria-label={plot.title+'; '+(plot.x_label||'x axis')+' versus '+(plot.y_label||'y axis')+
        '. Hover for values or use keyboard arrows.'}
      onPointerMove={event=>{
        if(!x.length)return
        const rect=event.currentTarget.getBoundingClientRect()
        const mouse=(event.clientX-rect.left)/rect.width*880
        let nearest=0,best=Number.POSITIVE_INFINITY
        for(let i=0;i<x.length;i++){
          const diff=Math.abs(xcoord(i)-mouse)
          if(diff<best){best=diff;nearest=i}
        }
        if(nearest!==activeIndex){
          setActiveIndex(nearest);emitCursor(nearest)
        }
      }}
      onPointerLeave={()=>{if(!pinned){setActiveIndex(null);emitCursor(null)}}}
      onClick={()=>setPinned(old=>!old)}
      onFocus={()=>setActiveIndex(x.length?x.length-1:null)}
      onBlur={()=>setActiveIndex(null)}
      onKeyDown={event=>{
        if(event.key==='ArrowLeft'||event.key==='ArrowRight'){
          event.preventDefault()
          const next=Math.max(0,Math.min(x.length-1,
            (activeIndex??x.length-1)+(event.key==='ArrowRight'?1:-1)))
          setActiveIndex(next);emitCursor(next)
        }
        if(event.key==='Enter'||event.key===' '){
          event.preventDefault();setPinned(old=>!old)
        }
        if(event.key==='Escape'){event.preventDefault();setPinned(false);setActiveIndex(null)}
        if(event.key==='Home'){event.preventDefault();setActiveIndex(0)}
        if(event.key==='End'){event.preventDefault();setActiveIndex(x.length-1)}
      }}>
      {ticks.map(t=><g key={t}>
        <line x1={GRID_LEFT} x2={GRID_RIGHT} y1={GRID_TOP+t*height} y2={GRID_TOP+t*height}
          stroke="#304353" strokeDasharray="3 7" opacity=".8"/>
        <text x="60" y={GRID_TOP+t*height+4} fill="#8fa3b4" fontSize="11" textAnchor="end">{fmt(hi-t*(hi-lo))}</text>
      </g>)}
      {(plot.regions||[]).slice(0,3).map((region,i)=>{
        const start=x.findIndex(v=>String(v)===String(region.start))
        const end=x.findIndex(v=>String(v)===String(region.end))
        if(start<0||end<start)return null
        const x1=xcoord(start),x2=xcoord(end)
        return <g key={i}>
          <rect x={x1} y={GRID_TOP} width={Math.max(1,x2-x1)} height={height}
            fill="#7dc4f5" opacity=".12"/>
          <text x={Math.min(GRID_RIGHT-110,x1+4)} y={GRID_TOP+12+i*13}
            fill="#a9deff" fontSize="9">{region.label.slice(0,25)}</text>
        </g>
      })}
      {plot.band?.lower&&plot.band.upper&&plot.band.lower.length===x.length&&
        <polygon points={[
          ...plot.band.upper.map((v,i)=>xcoord(i)+','+yp(v)),
          ...plot.band.lower.map((v,i)=>xcoord(i)+','+yp(v)).reverse(),
        ].join(' ')} fill="#58dfbf" opacity=".13"/>}
      {plot.kind==='scatter2d'&&plot.y?.length===x.length?
        plot.y.map((y,i)=><circle key={i} cx={xcoord(i)} cy={yp(y)} r="3.3" fill={COLORS[0]} opacity=".7">
          <title>{String(x[i])+' : '+fmt(y)}</title>
        </circle>)
      :isBar?traces.flatMap((trace,t)=>trace.y.map((v,i)=>{
        if(!finite(v))return null
        const center=xcoord(i)
        const bw=Math.min(28,width/Math.max(4,x.length)*(0.78/Math.max(1,traces.length)))
        const start=center+(t-(traces.length-1)/2)*bw
        const base=yp(Math.max(lo,Math.min(hi,0)))
        return <rect key={t+'-'+i} x={start-bw*.46} y={Math.min(base,yp(v))}
          width={bw*.92} height={Math.max(1,Math.abs(base-yp(v)))}
          fill={trace.color||COLORS[t%COLORS.length]} opacity=".8">
          <title>{trace.name+' · '+String(x[i])+' · '+fmt(v)}</title>
        </rect>
      })):
      traces.map((trace,t)=><g key={trace.name}>
        <path d={path(trace.y)} fill="none" stroke={trace.color||COLORS[t%COLORS.length]}
          strokeWidth="2.5" strokeLinejoin="round" vectorEffect="non-scaling-stroke"/>
        {trace.y.length<=24&&trace.y.map((v,i)=>finite(v)?<circle key={i}
          cx={xcoord(i)} cy={yp(v)} r="3" fill={trace.color||COLORS[t%COLORS.length]}>
          <title>{trace.name+' · '+String(x[i])+' · '+fmt(v)}</title>
        </circle>:null)}
      </g>)}
      {plot.threshold!==undefined&&finite(plot.threshold)&&numerical&&maxX>minX&&
         plot.threshold>=minX&&plot.threshold<=maxX&&<>
        <line x1={GRID_LEFT+(plot.threshold-minX)/(maxX-minX)*width}
              x2={GRID_LEFT+(plot.threshold-minX)/(maxX-minX)*width}
              y1={GRID_TOP} y2={GRID_BOTTOM}
              stroke="#ffa466" strokeDasharray="7 5" strokeWidth="1.5"/>
        <text x={GRID_LEFT+(plot.threshold-minX)/(maxX-minX)*width+5} y={GRID_TOP+12}
              fill="#ffc890" fontSize="10">Loss quantile</text>
      </>}
      {(plot.annotations||[]).slice(0,8).map((note,index)=>{
        const idx=x.findIndex(v=>String(v)===String(note.x))
        if(idx<0)return null
        const at=xcoord(idx)
        return <g key={index}>
          <line x1={at} x2={at} y1={GRID_TOP} y2={GRID_BOTTOM}
            stroke="#f6c16a" strokeDasharray="4 5" strokeWidth="1.4"/>
          <rect x={Math.min(at+5,GRID_RIGHT-160)} y={GRID_TOP+index*17}
            width="155" height="15" rx="3" fill="#153849" opacity=".9"/>
          <text x={Math.min(at+9,GRID_RIGHT-156)} y={GRID_TOP+11+index*17}
            fill="#ffe0a3" fontSize="9">{note.label.slice(0,24)}</text>
        </g>
      })}
      {activeIndex!==null&&x[activeIndex]!==undefined&&<g className="ql-active-observation">
        <line x1={xcoord(activeIndex)} x2={xcoord(activeIndex)}
          y1={GRID_TOP} y2={GRID_BOTTOM} stroke="#d3f8e9"
          strokeDasharray="4 5" strokeWidth="1.1"/>
        {plot.kind==='scatter2d'&&plot.y&&finite(plot.y[activeIndex])&&
          <circle cx={xcoord(activeIndex)} cy={yp(plot.y[activeIndex])}
            r="5" stroke="#d5fff0" strokeWidth="2" fill="#70dcca"/>}
        {!isBar&&plot.kind!=='scatter2d'&&traces.map((t,i)=>
          finite(t.y[activeIndex])?<circle key={t.name}
            cx={xcoord(activeIndex)} cy={yp(t.y[activeIndex] as number)}
            r="4.2" stroke="#06232e" strokeWidth="2"
            fill={t.color||COLORS[i%COLORS.length]}/>:null)}
        <rect x={GRID_RIGHT-250} y={GRID_TOP+4} rx="8" width="247"
          height={28+19*Math.min(4,plot.kind==='scatter2d'?1:traces.length)}
          fill="#092332" stroke="#6e9f9d" opacity=".96"/>
        <text x={GRID_RIGHT-240} y={GRID_TOP+22} fontSize="12" fill="#e0fffb">
          {String(x[activeIndex]).slice(0,30)}
        </text>
        {(plot.kind==='scatter2d'?[
          {name:plot.y_label||'Value',value:plot.y?.[activeIndex]},
        ]:traces.slice(0,4).map(t=>({name:t.name,value:t.y[activeIndex]})))
          .map((r,i)=><text key={r.name} x={GRID_RIGHT-240} y={GRID_TOP+41+i*19}
            fontSize="11" fill={COLORS[i%COLORS.length]}>
            {r.name.slice(0,18)+': '+(finite(r.value)?fmt(r.value):'missing')}
          </text>)}
      </g>}
      {[0,.25,.5,.75,1].map((t,i)=>{const idx=Math.min(x.length-1,Math.round(t*(x.length-1)))
        return idx>=0?<text key={i} x={xcoord(idx)} y="300" textAnchor={i===0?'start':i===4?'end':'middle'}
          fill="#8ca0b5" fontSize="10">{String(x[idx]).slice(0,14)}</text>:null
      })}
      <text x="450" y="336" textAnchor="middle" fill="#b1c1d0" fontSize="12">{plot.x_label}</text>
      <text x="18" y="152" fill="#b1c1d0" fontSize="11" textAnchor="middle"
        transform="rotate(-90,18,152)">{plot.y_label}</text>
    </svg>
    <p className="ql-plot-hover-help">Hover or touch to inspect · click (or press Enter) to
      {pinned?' unlock the cursor':' lock the cursor'} · arrow keys move between observations.
      {pinned?' Cursor pinned.':''}</p>
    <div className="ql-legend">{traces.map((t,i)=><span key={t.name}>
      <i style={{background:t.color||COLORS[i%COLORS.length]}}/>{t.name}
    </span>)}</div>
  </div>
}
function Heatmap({plot}:{plot:ResearchPlotData}){
  const labels=plot.labels||[]
  const values=plot.values||[]
  const rowLabels=plot.row_labels||labels
  const cols=labels.length,rows=rowLabels.length
  if(!cols||!rows||cols>25||rows>25||values.length!==rows||
    values.some(row=>row.length!==cols||row.some(v=>!finite(v))))
    return <p className="ql-muted">No valid bounded heatmap matrix to render.</p>
  const cell=Math.max(18,Math.min(48,Math.floor(590/Math.max(cols,rows))))
  const all=values.flat(),low=Math.min(...all),high=Math.max(...all),span=Math.max(1e-12,high-low)
  const correlation=plot.scale!=='sequential'
  const scale=(value:number)=>{
    const z=clamp(correlation?(value+1)/2:(value-low)/span,0,1)
    return 'rgb('+Math.round(37+(1-z)*60)+','+Math.round(110+z*94)+','+
      Math.round(151+z*29)+')'
  }
  return <div className="ql-heat-scroll"><svg width={90+cell*cols} height={82+cell*rows}
    role="img" aria-label={plot.title+' heatmap with '+rows+' rows and '+cols+' columns'}>
    {labels.map((label,i)=><text key={i} x={77+cell*i+cell/2} y="58"
      fill="#9bb7c8" fontSize="10" textAnchor="start"
      transform={'rotate(-40 '+(77+cell*i+cell/2)+' 58)'}>{label.slice(0,13)}</text>)}
    {rowLabels.map((label,i)=><text key={i} x="70" y={70+cell*i+cell/2}
      fill="#9bb7c8" fontSize="10" textAnchor="end">{label.slice(0,13)}</text>)}
    {values.flatMap((row,i)=>row.map((v,j)=><g key={i+'-'+j}>
      <rect x={77+j*cell} y={65+i*cell} width={cell-2} height={cell-2}
        fill={scale(v)} rx="2"><title>{rowLabels[i]+' × '+labels[j]+': '+fmt(v)}</title></rect>
      {cols<=10&&rows<=10&&<text x={77+j*cell+cell/2} y={65+i*cell+cell/2+4}
        textAnchor="middle" fontSize="10" fill="#071b25">{fmt(v)}</text>}
    </g>))}
  </svg><p className="ql-muted">{correlation?'Color represents correlation from -1 to +1.':
    'Color is scaled between the finite minimum ('+fmt(low)+') and maximum ('+fmt(high)+').'}
    {' '}Hover for exact source-computed values.</p></div>
}
type Point3={x:number;y:number;depth:number}
function Surface3D({plot}:{plot:ResearchPlotData}){
  const [azimuth,setAzimuth]=useState(-42)
  const [elevation,setElevation]=useState(26)
  const [zoom,setZoom]=useState(1)
  const drag=useRef<{x:number;y:number;az:number;el:number}|null>(null)
  const xs=(plot.x||[]).map(Number),ys=(plot.y||[]).map(Number),zs=plot.z||[]
  const good=xs.length>=2&&ys.length>=2&&xs.length<=41&&ys.length<=41&&zs.length===ys.length&&zs.every(r=>r.length===xs.length)
  const mesh=useMemo(()=>{
    if(!good)return {polys:[] as {key:string;points:string;depth:number;color:string;value:number}[],axes:[] as Point3[]}
    const vals=zs.flat(),zmin=Math.min(...vals),zmax=Math.max(...vals),zr=Math.max(1e-9,zmax-zmin)
    const angle=azimuth*Math.PI/180,tilt=elevation*Math.PI/180
    const proj=(i:number,j:number,z:number):Point3=>{
      const a=(i/(xs.length-1)-.5)*2,b=(j/(ys.length-1)-.5)*2,c=((z-zmin)/zr-.5)*1.5
      const rX=Math.cos(angle)*a-Math.sin(angle)*b
      const rY=Math.sin(angle)*a+Math.cos(angle)*b
      return {x:435+zoom*178*rX,y:220-zoom*178*(Math.sin(tilt)*rY+Math.cos(tilt)*c),
              depth:Math.cos(tilt)*rY-Math.sin(tilt)*c}
    }
    const polygons=[]
    for(let j=0;j<ys.length-1;j++)for(let i=0;i<xs.length-1;i++){
      const z=[zs[j][i],zs[j][i+1],zs[j+1][i+1],zs[j+1][i]]
      const v=[proj(i,j,z[0]),proj(i+1,j,z[1]),proj(i+1,j+1,z[2]),proj(i,j+1,z[3])]
      const shade=clamp((z.reduce((a,b)=>a+b,0)/4-zmin)/zr,0,1)
      const hue=185-50*shade
      polygons.push({key:j+'-'+i,points:v.map(p=>p.x.toFixed(2)+','+p.y.toFixed(2)).join(' '),
        depth:v.reduce((a,b)=>a+b.depth,0)/4,color:`hsl(${hue} 58% ${27+38*shade}%)`,
        value:z.reduce((a,b)=>a+b,0)/4})
    }
    polygons.sort((a,b)=>a.depth-b.depth)
    return {polys:polygons,axes:[proj(0,0,zmin),proj(xs.length-1,0,zmin),
        proj(0,ys.length-1,zmin),proj(0,0,zmax)]}
  },[azimuth,elevation,zoom,xs.length,ys.length,JSON.stringify(zs),good])
  if(!good)return <p className="ql-muted">No valid numerical surface was returned.</p>
  const axes=mesh.axes
  return <div className="ql-surface">
    <div className="ql-graph-controls">
      <span>Drag to rotate · 3D mathematical surface</span>
      <button type="button" onClick={()=>setZoom(v=>clamp(v-.15,.55,1.45))}>−</button>
      <button type="button" onClick={()=>setZoom(v=>clamp(v+.15,.55,1.45))}>+</button>
      <button type="button" onClick={()=>{setAzimuth(-42);setElevation(26);setZoom(1)}}>Reset</button>
    </div>
    <svg viewBox="0 0 880 460" role="img" tabIndex={0}
      aria-label={'Interactive 3D surface: '+plot.title+'. Use arrow keys to rotate'}
      onKeyDown={e=>{
        if(e.key==='ArrowLeft'||e.key==='ArrowRight'){setAzimuth(v=>v+(e.key==='ArrowRight'?8:-8));e.preventDefault()}
        if(e.key==='ArrowUp'||e.key==='ArrowDown'){setElevation(v=>clamp(v+(e.key==='ArrowUp'?5:-5),5,75));e.preventDefault()}
      }}
      onPointerDown={e=>{drag.current={x:e.clientX,y:e.clientY,az:azimuth,el:elevation};e.currentTarget.setPointerCapture(e.pointerId)}}
      onPointerMove={e=>{if(!drag.current)return;setAzimuth(drag.current.az+(e.clientX-drag.current.x)*.36);setElevation(clamp(drag.current.el+(e.clientY-drag.current.y)*.28,5,75))}}
      onPointerUp={()=>{drag.current=null}} onPointerCancel={()=>{drag.current=null}}>
      <rect x="0" y="0" width="880" height="460" rx="8" fill="#0c1b2a"/>
      {mesh.polys.map(face=><polygon key={face.key} points={face.points}
        fill={face.color} fillOpacity=".87" stroke="#081d27" strokeOpacity=".6"
        strokeWidth=".65"><title>{plot.z_label+': '+fmt(face.value)}</title></polygon>)}
      {[[1,0],[2,0],[3,0]].map(([i,j])=><line key={i} x1={axes[i].x} y1={axes[i].y}
        x2={axes[j].x} y2={axes[j].y} stroke="#c3def0" strokeOpacity=".65" strokeWidth="1.6"/>)}
      {axes.slice(1).map((p,i)=><text key={i} x={p.x} y={p.y+(i===2?-9:20)}
        fontSize="12" textAnchor="middle" fill="#c6e7ee">{[plot.x_label,plot.y_label,plot.z_label][i]}</text>)}
    </svg>
    <div className="ql-plot-foot"><span>X: {fmt(xs[0])} → {fmt(xs[xs.length-1])}</span>
      <span>Y: {fmt(ys[0])} → {fmt(ys[ys.length-1])}</span>
      <span>Z: {fmt(Math.min(...zs.flat()))} → {fmt(Math.max(...zs.flat()))}</span></div>
  </div>
}
const csvCell=(value:unknown)=>{
  if(typeof value==='number'&&Number.isFinite(value))return String(value)
  const text=String(value??'')
  const safe=/^[=+@\\-]/.test(text)?"'"+text:text
  return '"'+safe.replaceAll('"','""')+'"'
}
function dataTable(plot:ResearchPlotData):{columns:string[];rows:unknown[][]}{
  if(plot.kind==='surface3d'){
    const xs=plot.x||[],ys=plot.y||[],z=plot.z||[]
    return {columns:[plot.x_label||'x',plot.y_label||'y',plot.z_label||'z'],
      rows:ys.flatMap((y,i)=>xs.map((x,j)=>[x,y,z[i]?.[j]??null]))}
  }
  if(plot.kind==='heatmap2d'){
    const xs=plot.labels||[],ys=plot.row_labels||xs,z=plot.values||[]
    return {columns:['Row','Column','Value'],
      rows:ys.flatMap((y,i)=>xs.map((x,j)=>[y,x,z[i]?.[j]??null]))}
  }
  const axes=plot.x||[]
  const traces=plot.traces||[]
  const columns=[plot.x_label||'X',
    ...(plot.kind==='scatter2d'?[plot.y_label||'Value']:traces.map(t=>t.name)),
    ...(plot.band?['95% fan lower','95% fan upper']:[])]
  return {columns,rows:axes.map((x,i)=>[
    x,...(plot.kind==='scatter2d'?[plot.y?.[i]??null]:traces.map(t=>t.y[i]??null)),
    ...(plot.band?[plot.band.lower[i]??null,plot.band.upper[i]??null]:[])
  ])}
}
function downloadFile(name:string,contents:string,mime:string){
  const url=URL.createObjectURL(new Blob([contents],{type:mime}))
  const anchor=document.createElement('a')
  anchor.href=url;anchor.download=name;document.body.appendChild(anchor)
  anchor.click();anchor.remove()
  URL.revokeObjectURL(url)
}
function safeName(name:string){
  return name.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'').slice(0,70)||'plot'
}
export default function ResearchPlot({plot,provenance}:{plot:ResearchPlotData;provenance?:string}){
  const chart=useRef<HTMLElement|null>(null)
  const [view,setView]=useState<{start:number;end:number}|null>(null)
  const [syncHover,setSyncHover]=useState(true)
  const n=plot.x?.length||0
  const zoomable=n>=8&&plot.kind!=='surface3d'&&plot.kind!=='heatmap2d'
  const left=view?.start??0,right=view?.end??n
  useEffect(()=>{setView(null)},[plot.title,n])
  const clampView=(start:number,span:number)=>{
    const size=Math.max(5,Math.min(n,span))
    const beginning=Math.max(0,Math.min(n-size,start))
    setView(size===n?null:{start:beginning,end:beginning+size})
  }
  const zoomIn=()=>clampView(right-Math.max(5,Math.ceil((right-left)/1.6)),
    Math.max(5,Math.ceil((right-left)/1.6)))
  const zoomOut=()=>clampView(right-Math.min(n,Math.ceil((right-left)*1.6)),
    Math.min(n,Math.ceil((right-left)*1.6)))
  const pan=(dir:-1|1)=>{
    const span=right-left,step=Math.max(1,Math.round(span/3))
    clampView(left+dir*step,span)
  }
  const visible=useMemo(()=>{
    if(!view||!zoomable)return plot
    return {...plot,x:plot.x?.slice(view.start,view.end),
      y:plot.y?.slice(view.start,view.end),
      traces:plot.traces?.map(t=>({...t,y:t.y.slice(view.start,view.end)})),
      band:plot.band?{lower:plot.band.lower.slice(view.start,view.end),
        upper:plot.band.upper.slice(view.start,view.end)}:undefined}
  },[plot,view,zoomable])
  const table=useMemo(()=>dataTable(plot),[plot])
  const saveSvg=()=>{
    const original=chart.current?.querySelector('svg')
    if(!original)return
    const copy=original.cloneNode(true) as SVGSVGElement
    copy.setAttribute('xmlns','http://www.w3.org/2000/svg')
    if(!copy.getAttribute('viewBox')){
      const w=Number(copy.getAttribute('width')||880)
      const h=Number(copy.getAttribute('height')||460)
      copy.setAttribute('viewBox',`0 0 ${w} ${h}`)
    }
    const description=document.createElementNS('http://www.w3.org/2000/svg','desc')
    description.textContent='QuantLab computed figure. Source class: '+String(provenance||'not specified')+
      '. Charts with synthetic paths are not observed market prices.'
    copy.insertBefore(description,copy.firstChild)
    downloadFile('quantlab-'+safeName(plot.title)+'.svg',
      new XMLSerializer().serializeToString(copy),'image/svg+xml;charset=utf-8')
  }
  const saveCsv=()=>{
    const contents=[table.columns.map(csvCell).join(','),
      ...table.rows.map(row=>row.map(csvCell).join(','))].join('\n')
    downloadFile('quantlab-'+safeName(plot.title)+'.csv',contents,'text/csv;charset=utf-8')
  }
  return <section className="ql-chart-card" ref={chart}>
    <div className="ql-chart-title-row"><h4>{plot.title}</h4>
      <div className="ql-chart-export">
        <button type="button" onClick={saveSvg} aria-label={'Export SVG of '+plot.title}>Export SVG</button>
        <button type="button" onClick={saveCsv} aria-label={'Export CSV of '+plot.title}>Export CSV</button>
      </div>
    </div>
    {zoomable&&<div className="ql-chart-viewport" role="group"
      aria-label={'Chart zoom and synchronized pointer for '+plot.title}>
      <button type="button" onClick={zoomIn} disabled={right-left<=5}
        aria-label={'Zoom in '+plot.title}>Zoom in +</button>
      <button type="button" onClick={zoomOut} disabled={!view}
        aria-label={'Zoom out '+plot.title}>Zoom out −</button>
      <button type="button" onClick={()=>pan(-1)} disabled={!view||left===0}
        aria-label={'Pan left '+plot.title}>◀ Earlier</button>
      <button type="button" onClick={()=>pan(1)} disabled={!view||right>=n}
        aria-label={'Pan right '+plot.title}>Later ▶</button>
      <button type="button" onClick={()=>setView(null)} disabled={!view}
        aria-label={'Reset zoom '+plot.title}>Reset</button>
      <label><input type="checkbox" checked={syncHover} onChange={e=>setSyncHover(e.target.checked)}/>
        Link crosshair by shared dates</label>
      <span>{right-left} of {n} observations visible · full-series CSV export</span>
    </div>}
    {plot.kind==='surface3d'?<Surface3D plot={plot}/>:
     plot.kind==='heatmap2d'?<Heatmap plot={plot}/>:
     <Canvas2D plot={visible} syncHover={syncHover}/>}
    <details className="ql-chart-data">
      <summary>Inspect plotted observations ({table.rows.length.toLocaleString('en-US')} rows)</summary>
      <div className="ql-table-scroll">
        <table><thead><tr>{table.columns.map((key,i)=><th key={i}>{key}</th>)}</tr></thead>
          <tbody>{table.rows.slice(0,40).map((row,i)=><tr key={i}>
            {row.map((cell,j)=><td key={j}>{cell===null?'Missing':String(cell)}</td>)}</tr>)}</tbody>
        </table>
      </div>
      {table.rows.length>40&&<p className="ql-note">Preview shows 40 rows.
        Export CSV contains all {table.rows.length.toLocaleString('en-US')} rows.</p>}
    </details>
    <p className="ql-muted">{provenance==='synthetic'?
      'SEEDED SIMULATION · ARTIFICIAL DATA · Reproducible hypothetical paths, not real market history.':
      provenance==='historical'?
      'HISTORICAL INPUT · Some graphs also contain seeded scenario paths. Check plot titles and methodological limits.':
      provenance==='market'?
      'ORIGINAL QUOTE INPUT · Computed prices, surfaces and payoff paths are MODEL outputs, not historical fills.':
      provenance==='theoretical'?
      'THEORETICAL MODEL · User-assumed inputs, not observed quotes.':
      'Source: Python research engine · computed values with explicit evidence classification.'}</p>
  </section>
}

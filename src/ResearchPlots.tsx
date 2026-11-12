import {useMemo, useRef, useState} from 'react'

export type ResearchTrace={name:string;y:(number|null)[];color?:string}
export type ResearchPlotData={
  kind:string;title:string;x?:(string|number)[];y?:number[];
  traces?:ResearchTrace[];x_label?:string;y_label?:string;
  z_label?:string;z?:number[][];band?:{lower:number[];upper:number[]};
  labels?:string[];values?:number[][];threshold?:number
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
function Canvas2D({plot}:{plot:ResearchPlotData}){
  const x=plot.x||[]
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
    <svg viewBox="0 0 880 350" className="ql-svg-chart" role="img"
      aria-label={plot.title+'; '+(plot.x_label||'x axis')+' versus '+(plot.y_label||'y axis')}>
      {ticks.map(t=><g key={t}>
        <line x1={GRID_LEFT} x2={GRID_RIGHT} y1={GRID_TOP+t*height} y2={GRID_TOP+t*height}
          stroke="#304353" strokeDasharray="3 7" opacity=".8"/>
        <text x="60" y={GRID_TOP+t*height+4} fill="#8fa3b4" fontSize="11" textAnchor="end">{fmt(hi-t*(hi-lo))}</text>
      </g>)}
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
      {plot.threshold!==undefined&&finite(plot.threshold)&&lo<=plot.threshold&&plot.threshold<=hi&&<>
        <line x1={GRID_LEFT} x2={GRID_RIGHT} y1={yp(plot.threshold)} y2={yp(plot.threshold)}
          stroke="#ffa466" strokeDasharray="7 5" strokeWidth="1.5"/>
        <text x={GRID_RIGHT-4} y={yp(plot.threshold)-6} fill="#ffc890" fontSize="10"
          textAnchor="end">Tail threshold</text>
      </>}
      {[0,.25,.5,.75,1].map((t,i)=>{const idx=Math.min(x.length-1,Math.round(t*(x.length-1)))
        return idx>=0?<text key={i} x={xcoord(idx)} y="300" textAnchor={i===0?'start':i===4?'end':'middle'}
          fill="#8ca0b5" fontSize="10">{String(x[idx]).slice(0,14)}</text>:null
      })}
      <text x="450" y="336" textAnchor="middle" fill="#b1c1d0" fontSize="12">{plot.x_label}</text>
      <text x="18" y="152" fill="#b1c1d0" fontSize="11" textAnchor="middle"
        transform="rotate(-90,18,152)">{plot.y_label}</text>
    </svg>
    <div className="ql-legend">{traces.map((t,i)=><span key={t.name}>
      <i style={{background:t.color||COLORS[i%COLORS.length]}}/>{t.name}
    </span>)}</div>
  </div>
}
function Heatmap({plot}:{plot:ResearchPlotData}){
  const labels=plot.labels||[]
  const values=plot.values||[]
  const n=labels.length
  if(!n||n>25)return <p className="ql-muted">No bounded matrix to render.</p>
  const cell=Math.min(48,Math.floor(600/n))
  const scale=(v:number)=>{const z=clamp((v+1)/2,0,1);return `rgb(${Math.round(37+(1-z)*60)},${Math.round(110+z*94)},${Math.round(151+z*29)})`}
  return <div className="ql-heat-scroll"><svg width={85+cell*n} height={75+cell*n}
    role="img" aria-label={plot.title+' correlation matrix of '+n+' assets'}>
    {labels.map((label,i)=><g key={label}>
      <text x={75+cell*i+cell/2} y="57" fill="#9bb7c8" fontSize="10" textAnchor="start"
        transform={`rotate(-40 ${75+cell*i+cell/2} 57)`}>{label.slice(0,12)}</text>
      <text x="68" y={70+cell*i+cell/2} fill="#9bb7c8" fontSize="10"
        textAnchor="end">{label.slice(0,13)}</text>
    </g>)}
    {values.flatMap((row,i)=>row.map((v,j)=><g key={i+'-'+j}>
      <rect x={75+j*cell} y={65+i*cell} width={cell-2} height={cell-2}
        fill={scale(v)} rx="2"><title>{labels[i]+' × '+labels[j]+': '+fmt(v)}</title></rect>
      {n<=10&&<text x={75+j*cell+cell/2} y={65+i*cell+cell/2+4}
        textAnchor="middle" fontSize="10" fill="#071b25">{fmt(v)}</text>}
    </g>))}
  </svg><p className="ql-muted">Color encodes correlation from −1 to +1. Hover for exact pairwise values.</p></div>
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
export default function ResearchPlot({plot}:{plot:ResearchPlotData}){
  return <section className="ql-chart-card"><h4>{plot.title}</h4>
    {plot.kind==='surface3d'?<Surface3D plot={plot}/>:
     plot.kind==='heatmap2d'?<Heatmap plot={plot}/>:
     <Canvas2D plot={plot}/>}
    <p className="ql-muted">Source: Python research engine · charts display computed observations or explicitly labeled theoretical scenarios.</p>
  </section>
}

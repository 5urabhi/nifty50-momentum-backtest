import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowDown, ArrowRight, BookOpen, CheckCircle2, ChevronLeft, ChevronRight,
  CirclePlay, ExternalLink, Github, Layers3, Pause, Play, RotateCcw,
  ShieldCheck, Sparkles, TrendingUp, Volume2, VolumeX
} from 'lucide-react'

const GITHUB='https://github.com/5urabhi/nifty50-momentum-backtest'
const factors = [
  { name: 'Momentum', symbol: 'MOM', color:'#4fe0c1', detail: 'Has recent relative strength persisted?', weight:0.28 },
  { name: 'Low volatility', symbol: 'LOW', color:'#85baf8', detail: 'Which stocks have been less volatile?', weight:0.22 },
  { name: 'Value', symbol: 'VAL', color:'#eebf82', detail: 'How expensive are fundamentals relative to price?', weight:0.20 },
  { name: 'Quality', symbol: 'QLT', color:'#c1a2ff', detail: 'How robust are profitability and operating margins?', weight:0.18 },
  { name: 'Size', symbol: 'SIZ', color:'#f294ad', detail: 'How does capitalization affect the opportunity set?', weight:0.12 },
]
const chapters = [
  {number:'01', tag:'THE QUESTION', title:'Can an index be designed, not just tracked?', kicker:'Hypothesis → evidence',
   copy:'Start with a transparent question. Define the universe, measure company characteristics using information available at the time, and compare the resulting rules against an appropriately matched benchmark.'},
  {number:'02', tag:'THE SIGNALS', title:'Five lenses. One composite signal.', kicker:'Cross-sectional factor research',
   copy:'Momentum, low volatility, value, quality, and size each describe a different potential source of exposure. Standardize, combine and rank—without looking into the future.'},
  {number:'03', tag:'THE CONSTRAINTS', title:'A compelling signal still needs a portfolio.', kicker:'From score to investable rules',
   copy:'An index methodology specifies weight caps, sector limits, a rebalance schedule and transaction costs. Strong individual signals can create undesirable concentrated portfolios.'},
  {number:'04', tag:'THE MATHEMATICS', title:'Risk is a surface, not a single number.', kicker:'Interactive model geometry',
   copy:'Explore how portfolio volatility changes across feasible allocations. This illustrative three-asset landscape comes from the covariance equation; it is not fitted market history.'},
  {number:'05', tag:'THE VALIDATION', title:'What survives outside the training sample?', kicker:'No shortcut to evidence',
   copy:'Compare models chronologically, measure drawdowns and turnover, test sensitivity, and reserve a frozen final period. Historical claims remain blocked until source data and corporate actions are independently reviewed.'},
]
type Published = {
  name?: string
  dataset_status?: string
  benchmark_name?: string
  metrics_by_split?: Record<string,Record<string,number|string|null>>
  limitations?: string[]
}
type ReturnRow={date:string;strategy_net:number;benchmark:number}

function normalCdf(x:number){
  const a=1/(1+.2316419*Math.abs(x))
  const poly=.319381530*a-.356563782*a*a+1.781477937*a**3-1.821255978*a**4+1.330274429*a**5
  const q=Math.exp(-x*x/2)/Math.sqrt(2*Math.PI)*poly
  return x>=0?1-q:q
}
function callPrice(s:number,k:number,v:number,t=1,r=.04){
  const d1=(Math.log(s/k)+(r+v*v/2)*t)/(v*Math.sqrt(t))
  const d2=d1-v*Math.sqrt(t)
  return s*normalCdf(d1)-k*Math.exp(-r*t)*normalCdf(d2)
}
function P({children}:{children:React.ReactNode}){return <p className="bodycopy">{children}</p>}
function Chip({children}:{children:React.ReactNode}){return <span className="chip">{children}</span>}

function UseReveal(){
  useEffect(()=>{
    const observer=new IntersectionObserver((entries)=>entries.forEach(e=>{
      if(e.isIntersecting){e.target.classList.add('shown');observer.unobserve(e.target)}
    }),{threshold:.09})
    document.querySelectorAll('.reveal').forEach(x=>observer.observe(x))
    return ()=>observer.disconnect()
  },[])
  return null
}
function FactorVisual({selected,setSelected}:{selected:number;setSelected:(v:number)=>void}){
  const score = factors.map((f,i)=>({
    ...f,score:[.78,.67,.83,.53,.59][i],weighted:[.78,.67,.83,.53,.59][i]*f.weight
  }))
  return <div className="visual factor-visual">
    <div className="visual-head"><span className="mono">FACTOR COMPOSITE / ILLUSTRATIVE</span><span className="live-pill"><i/> Interactive</span></div>
    <div className="factor-stack">{score.map((f,i)=><button key={f.name} className={'factor-row '+(selected===i?'active':'')} onClick={()=>setSelected(i)} type="button">
      <span className="factor-index mono">0{i+1}</span>
      <span className="factor-title">{f.name}</span>
      <span className="factor-track"><span style={{width:(f.score*100)+'%',background:f.color}}/></span>
      <span className="mono factor-score">{(f.score*100).toFixed(0)}</span>
    </button>)}</div>
    <div className="factor-explain"><span className="mono">SELECTED FACTOR</span><strong style={{color:factors[selected].color}}>{factors[selected].symbol}</strong><p>{factors[selected].detail}</p></div>
    <div className="formula-line"><span>Composite signal</span><strong>Σ w<sub>i</sub> × z<sub>i</sub></strong></div>
  </div>
}

function PortfolioVisual(){
  const [cap,setCap]=useState(.35)
  const unbounded=[.41,.30,.19,.10]
  const weights=useMemo(()=>{
    let w=unbounded.map(v=>Math.min(v,cap)),left=1-w.reduce((a,b)=>a+b,0)
    for(let j=0;j<5 && left>1e-9;j++){
      const free=w.map((v,i)=>({v,i})).filter(x=>x.v<cap-1e-9)
      if(!free.length) break
      for(const f of free){const amount=Math.min(left/free.length,cap-w[f.i]);w[f.i]+=amount}
      left=1-w.reduce((a,b)=>a+b,0)
    }
    return w
  },[cap])
  return <div className="visual portfolio-visual">
    <div className="visual-head"><span className="mono">WEIGHT CONSTRAINT EXPLAINER</span><span className="chip amber">Illustrative holdings</span></div>
    <div className="allocation-ring" style={{background:`conic-gradient(#43dfbd 0% ${weights[0]*100}%,#8bbaf6 ${weights[0]*100}% ${(weights[0]+weights[1])*100}%,#e9bd81 ${(weights[0]+weights[1])*100}% ${(weights[0]+weights[1]+weights[2])*100}%,#ac9ffa ${(weights[0]+weights[1]+weights[2])*100}% 100%)`}}>
      <div><span className="mono">TOP HOLDING</span><strong>{Math.round(weights[0]*100)}%</strong><small>of portfolio</small></div>
    </div>
    <div className="allocation-legend">{weights.map((w,i)=><div key={i}><i style={{background:['#43dfbd','#8bbaf6','#e9bd81','#ac9ffa'][i]}}/><span>Security {String.fromCharCode(65+i)}</span><b>{(w*100).toFixed(1)}%</b></div>)}</div>
    <div className="slider-wrap"><label htmlFor="cap">Individual holding cap <strong>{Math.round(cap*100)}%</strong></label>
      <input id="cap" type="range" min="25" max="50" step="1" value={cap*100} onChange={e=>setCap(Number(e.target.value)/100)}/>
      <small>Drag the slider to enforce a concentration limit.</small>
    </div>
  </div>
}
type Point={x:number;y:number;z:number;surfaceX:number;surfaceY:number}
function PortfolioSurface(){
  const [angle,setAngle]=useState(.65)
  const [tilt,setTilt]=useState(.4)
  const pointer=useRef<{x:number;y:number;angle:number;tilt:number}|null>(null)
  const vals=[.13,.20,.28], corr=[[1,.32,.15],[.32,1,.4],[.15,.4,1]]
  const vol=(a:number,b:number)=>{
    const w=[a,b,1-a-b];let variance=0
    for(let i=0;i<3;i++)for(let j=0;j<3;j++)variance+=w[i]*w[j]*vals[i]*vals[j]*corr[i][j]
    return Math.sqrt(Math.max(variance,0))
  }
  const project=(a:number,b:number,v:number):Point=>{
    const cx=a-.34,cy=b-.34,cz=(v-.17)*3.4
    const c=Math.cos(angle),s=Math.sin(angle)
    const xr=cx*c-cy*s,yr=cx*s+cy*c
    return {x:270+xr*355,y:217+yr*Math.sin(tilt)*225-cz*275,z:v,surfaceX:a,surfaceY:b}
  }
  const triangles=useMemo(()=>{
    const n=19,poly:{pts:string;depth:number;value:number}[]=[]
    const mesh:Array<Array<Point>>=[]
    for(let i=0;i<=n;i++){
      mesh[i]=[]
      for(let j=0;j<=n-i;j++)mesh[i][j]=project(i/n,j/n,vol(i/n,j/n))
    }
    for(let i=0;i<n;i++)for(let j=0;j<n-i;j++){
      const first=[mesh[i][j],mesh[i+1][j],mesh[i][j+1]]
      poly.push({pts:first.map(p=>p.x.toFixed(1)+','+p.y.toFixed(1)).join(' '),depth:(i+j)/n,value:(first[0].z+first[1].z+first[2].z)/3})
      if(i+j<n-1){const second=[mesh[i+1][j],mesh[i+1][j+1],mesh[i][j+1]]
        poly.push({pts:second.map(p=>p.x.toFixed(1)+','+p.y.toFixed(1)).join(' '),depth:(i+j+1)/n,value:(second[0].z+second[1].z+second[2].z)/3})}
    }
    return poly.sort((a,b)=>b.depth-a.depth)
  },[angle,tilt])
  const low=Math.min(...Array.from({length:41},(_,i)=>i/40).flatMap(a=>Array.from({length:41},(_,j)=>j/40).filter(b=>a+b<=1).map(b=>vol(a,b))))
  return <div className="visual surface-card">
    <div className="visual-head"><span className="mono">3D PORTFOLIO VOLATILITY / SYNTHETIC COVARIANCE</span><span className="live-pill"><i/> Drag to rotate</span></div>
    <svg role="img" aria-label="Interactive perspective projection of feasible three-asset portfolio volatility" viewBox="0 0 540 445" className="surface-svg"
      onPointerDown={e=>{e.currentTarget.setPointerCapture(e.pointerId);pointer.current={x:e.clientX,y:e.clientY,angle,tilt}}}
      onPointerMove={e=>{if(!pointer.current)return;setAngle(pointer.current.angle+(e.clientX-pointer.current.x)*.008);setTilt(Math.max(.1,Math.min(1.3,pointer.current.tilt+(e.clientY-pointer.current.y)*.006)))}}
      onPointerUp={()=>{pointer.current=null}} onPointerCancel={()=>{pointer.current=null}}>
      <defs><linearGradient id="surfaceGradient"><stop stopColor="#3778a6"/><stop offset="1" stopColor="#6ce7ba"/></linearGradient></defs>
      <path d="M66 358H480M66 358V75" stroke="#2a4052" strokeDasharray="4 8"/>
      {triangles.map((t,i)=><polygon key={i} points={t.pts}
        fill={`hsl(${175+(t.value-.11)*440} 62% ${29+(t.value-.11)*105}%)`} fillOpacity=".85" stroke="#8be9e0" strokeWidth=".27" strokeOpacity=".22"/>)}
      <text x="24" y="47" fill="#d8eaf1" fontSize="14" fontFamily="monospace">σ(w) = √(wᵀΣw)</text>
      <text x="27" y="392" fill="#8fa9ba" fontSize="12">WEIGHT A</text><text x="427" y="392" fill="#8fa9ba" fontSize="12">WEIGHT B</text>
      <text x="27" y="413" fill="#8fa9ba" fontSize="12">LOWEST GRID σ ≈ {(low*100).toFixed(1)}%</text>
    </svg>
    <div className="surface-actions"><span className="mono">3 ASSETS · FULLY INVESTED · LONG ONLY</span><button type="button" className="icon-button" aria-label="Reset 3D view" onClick={()=>{setAngle(.65);setTilt(.4)}}><RotateCcw size={16}/> Reset</button></div>
    <div className="math-note">An educational 3D projection from an illustrative positive-definite covariance matrix. No market calibration.</div>
  </div>
}
function AnimatedCurve({step}:{step:number}){
  const xs=Array.from({length:84},(_,i)=>i/83)
  const base=(t:number)=>(.52+.18*t+.07*Math.sin(6.4*t)+.025*Math.sin(20*t))
  const risk=(t:number)=>base(t)-(.06+.04*Math.sin(4*t))
  const points=(fn:(t:number)=>number)=>xs.map((x,i)=>`${64+x*625},${270-fn(x)*225}`).join(' ')
  return <div className="visual chart-visual">
    <div className="visual-head"><span className="mono">RESEARCH VALIDATION / CONCEPTUAL CHART</span><Chip>Illustrative — not backtest</Chip></div>
    <svg role="img" aria-label="Animated illustrative comparison of an index and benchmark with stress and holdout segments" viewBox="0 0 760 360">
      {[0,1,2,3,4].map(i=><g key={i}><line x1="63" y1={70+i*52} x2="716" y2={70+i*52} stroke="#294054" strokeDasharray="3 7"/><text x="22" y={74+i*52} fill="#7391a7" fontSize="12">{(1.6-i*.2).toFixed(1)}×</text></g>)}
      <rect x="514" y="56" width="201" height="227" fill="#e9be85" fillOpacity={step>0?.06:0}/>
      <text x="537" y="83" fontSize="12" fontWeight="600" fill="#e1bb86">FROZEN HOLDOUT</text>
      <polyline points={points(risk)} stroke="#e9bd8b" strokeWidth="3" fill="none" strokeLinecap="round" strokeLinejoin="round" className="draw-chart"/>
      <polyline points={points(base)} stroke="#56d9bb" strokeWidth="3.5" fill="none" strokeLinecap="round" strokeLinejoin="round" className="draw-chart"/>
      <line x1="515" y1="58" x2="515" y2="284" stroke="#bc9570" strokeDasharray="4 6"/>
      <text x="62" y="326" fill="#7898ab" fontSize="12">DEVELOPMENT</text><text x="335" y="326" fill="#7898ab" fontSize="12">VALIDATION</text>
    </svg>
    <div className="legend-inline"><span><i style={{background:'#56d9bb'}}/>Research index (illustrative)</span><span><i style={{background:'#e9bd8b'}}/>Benchmark (illustrative)</span></div>
    <div className="math-note">These lines explain the evaluation design. No historical returns are invented or claimed.</div>
  </div>
}
function MiniSurface(){
  const [v,setV]=useState(.24)
  const strikes=[65,75,85,95,105,115,125,135]
  return <div className="visual mini-surface">
    <div className="visual-head"><span className="mono">EUROPEAN CALL · CLOSED-FORM EXPLAINER</span><Chip>Theoretical</Chip></div>
    <svg viewBox="0 0 700 320" role="img" aria-label="Call price across option strikes using Black-Scholes">
      {[0,1,2,3,4].map(i=><line key={i} x1="54" y1={55+i*55} x2="655" y2={55+i*55} stroke="#294054" strokeDasharray="4 7"/>)}
      <path d={strikes.map((k,i)=>`${i===0?'M':'L'} ${70+i*81} ${274-callPrice(100,k,v)*4.1}`).join(' ')}
        stroke="#55dec0" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" fill="none" className="draw-chart"/>
      {strikes.map((k,i)=><circle key={k} cx={70+i*81} cy={274-callPrice(100,k,v)*4.1} r="4" fill="#81edd8"/>)}
      <text x="60" y="307" fill="#829eb0" fontSize="12">LOW STRIKE</text><text x="553" y="307" fill="#829eb0" fontSize="12">HIGH STRIKE</text>
      <text x="57" y="35" fill="#adc5d1" fontSize="13">THEORETICAL CALL PRICE</text>
    </svg>
    <div className="slider-wrap"><label htmlFor="vol">Annual volatility <strong>{Math.round(v*100)}%</strong></label>
    <input id="vol" type="range" min="8" max="65" value={Math.round(v*100)} onChange={e=>setV(Number(e.target.value)/100)}/></div>
    <div className="math-note">This chart is evaluated in the browser for illustration. Python remains the source of record for numerical acceptance.</div>
  </div>
}
function PublishedCard(){
  const [snapshot,setSnapshot]=useState<{data:Published;rows:ReturnRow[]}|null>(null)
  const [state,setState]=useState<'loading'|'absent'|'ready'>('loading')
  useEffect(()=>{
    let live=true
    Promise.all([fetch('/data/summary.json'),fetch('/data/returns.csv')]).then(async ([a,b])=>{
      if(!a.ok||!b.ok)throw Error('Not published')
      const data=await a.json() as Published
      const csv=await b.text()
      const lines=csv.trim().split(/\r?\n/)
      const cols=lines.shift()?.split(',')??[]
      const rows=lines.map(line=>{
        const parts=line.split(',')
        const r=Object.fromEntries(cols.map((c,i)=>[c,parts[i]]))
        return {date:r.date,strategy_net:Number(r.strategy_net),benchmark:Number(r.benchmark)}
      }).filter(r=>Number.isFinite(r.strategy_net)&&Number.isFinite(r.benchmark))
      if(live){setSnapshot({data,rows});setState('ready')}
    }).catch(()=>{if(live)setState('absent')})
    return()=>{live=false}
  },[])
  if(state==='loading')return <div className="evidence-empty">Checking for an approved research snapshot…</div>
  if(!snapshot)return <div className="evidence-empty"><ShieldCheck size={24}/><strong>Historical results are not published</strong><p>No independently reviewed point-in-time research snapshot has been exported. The mathematical visualizations above are explicitly educational.</p><a href={GITHUB+'/blob/research/multi-factor-equity-index/docs/EMPIRICAL_DATA_GUIDE.md'} target="_blank" rel="noreferrer">Read the empirical validation protocol <ArrowRight size={14}/></a></div>
  const {data,rows}=snapshot
  const metrics=Object.entries(data.metrics_by_split??{})
  const last=metrics.at(-1)
  const status=data.dataset_status??'unverified'
  const fmt=(n:unknown)=>typeof n==='number'&&Number.isFinite(n)?(n*100).toFixed(2)+'%':'—'
  const path=(key:'strategy_net'|'benchmark')=>{
    let wealth=1
    const values=rows.map(r=>(wealth*=1+r[key]))
    const all=rows.reduce((arr,r)=>[...arr,r.strategy_net,r.benchmark],[] as number[])
    void all
    const min=Math.min(1,...values),max=Math.max(1,...values)
    return values.map((v,i)=>`${i?'L':'M'} ${24+i*650/Math.max(1,values.length-1)} ${210-(v-min)/(max-min||1)*175}`).join(' ')
  }
  return <div className="published">
    <div className="data-alert">PUBLIC SNAPSHOT · {status.replaceAll('_',' ').toUpperCase()} · Source data not independently audited by this website.</div>
    <div className="pub-grid"><div><span>Model / sample</span><strong>{data.name??'Research export'}</strong></div><div><span>Latest-split annualized return</span><strong>{fmt(last?.[1].strategy_cagr)}</strong></div><div><span>Tracking error</span><strong>{fmt(last?.[1].tracking_error)}</strong></div></div>
    <svg viewBox="0 0 710 245" className="pub-chart" role="img" aria-label="Approved export: strategy and benchmark cumulative return lines"><path d={path('strategy_net')} stroke="#58e1c2" fill="none" strokeWidth="3"/><path d={path('benchmark')} stroke="#e6c28a" fill="none" strokeWidth="3"/></svg>
    <div className="legend-inline"><span><i style={{background:'#58e1c2'}}/>Strategy</span><span><i style={{background:'#e6c28a'}}/>Supplied benchmark</span></div>
    <small>Public aggregate snapshot only. No raw holdings or broker credentials are loaded.</small>
  </div>
}
function ChapterNav({index,setIndex}:{index:number;setIndex:(v:number)=>void}){
  return <div className="chapter-controls"><button type="button" onClick={()=>setIndex(Math.max(0,index-1))} disabled={index===0} aria-label="Previous chapter"><ChevronLeft/></button><div>{chapters.map((_,i)=><button key={i} type="button" className={'chapter-dot '+(i===index?'active':'')} aria-label={`Go to chapter ${i+1}`} onClick={()=>setIndex(i)}/>)}</div><button type="button" aria-label="Next chapter" onClick={()=>setIndex(Math.min(chapters.length-1,index+1))} disabled={index===chapters.length-1}><ChevronRight/></button></div>
}
function MotionStory(){
  const [chapter,setChapter]=useState(0)
  const [playing,setPlaying]=useState(false)
  const [factor,setFactor]=useState(0)
  const current=chapters[chapter]
  useEffect(()=>{
    if(!playing)return
    const timer=setInterval(()=>setChapter(v=>(v+1)%chapters.length),8200)
    return()=>clearInterval(timer)
  },[playing])
  return <section id="story" className="story-section">
    <div className="section-heading reveal"><Chip>EXPLAINER MODE</Chip><h2>Mathematics that <em>moves.</em></h2>
      <p>Five short visual chapters. Tap through like a research documentary, or let the story play.</p></div>
    <div className="story-shell reveal">
      <div className="story-copy">
        <div className="story-kicker"><span>{current.number} / 05</span><span>{current.tag}</span></div>
        <div className="story-body" key={chapter}><span className="eyebrow">{current.kicker}</span>
          <h3>{current.title}</h3><P>{current.copy}</P>
          <div className="chapter-formula">{chapter===0?'H₀: no reliable excess return':chapter===1?'zᵢ = (xᵢ − μ) / σ':chapter===2?'Σwᵢ = 1  ·  0 ≤ wᵢ ≤ cap':chapter===3?'σₚ = √(wᵀ Σ w)':'train → validate → frozen test'}</div>
        </div>
        <div className="story-actions"><button className="primary-button" type="button" onClick={()=>setPlaying(!playing)}>{playing?<Pause size={16}/>:<Play size={16}/>} {playing?'Pause story':'Play story'}</button><span className="mono">CHAPTER {chapter+1} OF 5</span></div>
        <ChapterNav index={chapter} setIndex={setChapter}/>
      </div>
      <div className="story-stage" key={'visual'+chapter}>
        {chapter===0?<MiniSurface/>:chapter===1?<FactorVisual selected={factor} setSelected={setFactor}/>:chapter===2?<PortfolioVisual/>:chapter===3?<PortfolioSurface/>:<AnimatedCurve step={chapter}/>}
      </div>
    </div>
  </section>
}
const modelTiles=[
  {id:'01',group:'FACTOR RESEARCH',title:'Cross-sectional signals',description:'Standardized factor scores, rank correlations, forward-return diagnostics and empirical inference.',glyph:'∑'},
  {id:'02',group:'PORTFOLIO THEORY',title:'Constrained optimization',description:'Mean–variance utility, efficient frontiers, risk parity, CVaR and Black–Litterman.',glyph:'Σ'},
  {id:'03',group:'STOCHASTIC PROCESSES',title:'Volatility & dynamics',description:'GBM, OU, EWMA, GARCH, Heston and compensated jump-diffusion models.',glyph:'σ'},
  {id:'04',group:'OPTION MATHEMATICS',title:'Pricing & sensitivities',description:'Black–Scholes, Greeks, implied volatility, lattice methods and Monte Carlo convergence.',glyph:'Δ'},
  {id:'05',group:'EMPIRICAL VALIDATION',title:'No look-ahead allowed',description:'Dated fundamentals, corporate-action evidence, rolling holdout and numerical acceptance.',glyph:'✓'},
  {id:'06',group:'REPRODUCIBILITY',title:'Every assumption visible',description:'Local Python tests, provenance manifests, explicit research restrictions and research-paper drafts.',glyph:'↗'},
]
function App(){
  const [menu,setMenu]=useState(false)
  const [animated,setAnimated]=useState(true)
  const [scrolled,setScrolled]=useState(false)
  UseReveal()
  useEffect(()=>{
    const listener=()=>setScrolled(window.scrollY>35)
    window.addEventListener('scroll',listener,{passive:true})
    return()=>window.removeEventListener('scroll',listener)
  },[])
  useEffect(()=>{document.documentElement.dataset.motion=animated?'on':'off'},[animated])
  return <div className="site">
    <header className={'topbar '+(scrolled?'scrolled':'')}>
      <a href="#" className="brand" aria-label="Home"><span className="brand-symbol">∑</span><span>QUANT<span className="brand-muted"> / RESEARCH</span></span></a>
      <nav className={'nav-links '+(menu?'open':'')} aria-label="Main navigation">
        <a href="#story" onClick={()=>setMenu(false)}>Visual story</a>
        <a href="#models" onClick={()=>setMenu(false)}>Models</a>
        <a href="#evidence" onClick={()=>setMenu(false)}>Evidence</a>
        <a href="#workflow" onClick={()=>setMenu(false)}>Reproduce</a>
      </nav>
      <div className="top-actions"><button type="button" className="motion-toggle" title="Toggle animation" aria-label="Toggle animations" aria-pressed={animated} onClick={()=>setAnimated(!animated)}>{animated?<Volume2 size={17}/>:<VolumeX size={17}/>}<span>{animated?'Motion on':'Motion off'}</span></button>
        <a className="github-button" href={GITHUB} target="_blank" rel="noreferrer"><Github size={16}/> Source <ExternalLink size={13}/></a>
        <button type="button" className="mobile-menu" aria-label="Toggle menu" aria-expanded={menu} onClick={()=>setMenu(!menu)}><Layers3/></button></div>
    </header>
    <main>
      <section className="hero">
        <div className="hero-atmosphere" aria-hidden="true"><div className="halo"/><div className="orbit orbit-one"/><div className="orbit orbit-two"/><div className="hero-glow"/></div>
        <div className="hero-content">
          <div className="hero-eyebrow"><span className="signal-dot"/> INDEPENDENT QUANTITATIVE RESEARCH <span className="tiny-sep">/</span> EDUCATIONAL LABORATORY</div>
          <h1>Markets are noisy.<br/><span>Mathematics</span> helps<br/>us ask better questions.</h1>
          <P>Explore the logic behind factor investing, portfolio construction and empirical validation—with interactive visuals and reproducible Python research.</P>
          <div className="hero-cta"><a href="#story" className="primary-button"><CirclePlay size={19}/> Explore the visual story <ArrowRight size={17}/></a><a href="#models" className="secondary-button">View mathematical models <ArrowDown size={16}/></a></div>
          <div className="hero-foot"><span><CheckCircle2 size={15}/> Open methodology</span><span><ShieldCheck size={15}/> No fabricated performance</span><span><TrendingUp size={15}/> 2D + 3D explorations</span></div>
        </div>
        <div className="hero-chart" aria-hidden="true">
          <svg viewBox="0 0 700 600" preserveAspectRatio="xMidYMid meet">
            <defs><linearGradient id="heroLine" x1="0" y1="0" x2="1" y2="0"><stop stopColor="#367e89"/><stop offset=".53" stopColor="#52c6bd"/><stop offset="1" stopColor="#c1ffe1"/></linearGradient><linearGradient id="heroFill" x1="0" y1="0" x2="0" y2="1"><stop stopColor="#5dd9c1" stopOpacity=".23"/><stop offset="1" stopColor="#5dd9c1" stopOpacity="0"/></linearGradient></defs>
            {Array.from({length:8},(_,i)=><line key={i} x1="0" x2="700" y1={100+i*60} y2={100+i*60} stroke="#234559" strokeOpacity=".4" strokeDasharray="2 10"/>)}
            <path d="M0 470 C70 460 92 414 135 440 S200 358 255 379 S302 257 350 308 S415 230 463 259 S516 184 562 207 S636 130 700 112 L700 600 L0 600 Z" fill="url(#heroFill)"/>
            <path d="M0 470 C70 460 92 414 135 440 S200 358 255 379 S302 257 350 308 S415 230 463 259 S516 184 562 207 S636 130 700 112" stroke="url(#heroLine)" strokeWidth="4" fill="none" className="draw-chart"/>
            <circle cx="562" cy="207" r="6" fill="#d6ffe8"/><circle cx="562" cy="207" r="18" fill="#a2fce0" fillOpacity=".15"/>
          </svg>
          <div className="floating-note note-one"><span className="mono">RESEARCH</span><strong>Signal ≠ evidence</strong></div>
          <div className="floating-note note-two"><span className="mono">THE QUESTION</span><strong>What survives validation?</strong></div>
        </div>
        <div className="scroll-prompt"><span className="mono">SCROLL TO EXPLORE</span><ArrowDown size={16}/></div>
      </section>
      <section className="principles reveal" aria-label="Research principles"><div><span className="principle-icon"><Sparkles size={19}/></span><div><strong>Explain every assumption</strong><p>Start with explicit definitions and data provenance.</p></div></div><div><span className="principle-icon"><Layers3 size={19}/></span><div><strong>Build from first principles</strong><p>Factor scores, constraints, risk and attribution.</p></div></div><div><span className="principle-icon"><ShieldCheck size={19}/></span><div><strong>Earn empirical claims</strong><p>Only audited sources and genuine holdout evidence.</p></div></div></section>
      <MotionStory/>
      <section className="models-section" id="models"><div className="section-heading reveal"><Chip>RESEARCH ENGINE</Chip><h2>Under the surface: <em>the models.</em></h2><p>The public narrative is lightweight. The source of truth remains a modular Python research system.</p></div>
        <div className="model-grid">{modelTiles.map(item=><article className="model-card reveal" key={item.id}><div className="model-top"><span className="mono">{item.group}</span><span className="model-symbol">{item.glyph}</span></div><h3>{item.title}</h3><p>{item.description}</p><div className="model-bottom"><span className="mono">{item.id} / 06</span><BookOpen size={18}/></div></article>)}</div></section>
      <section className="evidence-section" id="evidence"><div className="section-heading reveal"><Chip>RESEARCH INTEGRITY</Chip><h2>Beautiful charts.<br/><em>Uncompromising evidence.</em></h2><p>Hypothetical animations are labeled as such. Empirical return charts appear only after an explicit public export.</p></div><div className="evidence-layout reveal"><PublishedCard/><div className="evidence-side"><span className="eyebrow">PUBLICATION CHECKLIST</span><h3>Before a return becomes a headline.</h3><div className="checklist">{['Historical constituent membership','Publication-dated fundamentals','Corporate-action adjusted wealth','Compatible total-return benchmark','Frozen holdout and local tests'].map((item,i)=><div key={i}><span className="check-number">{String(i+1).padStart(2,'0')}</span><span>{item}</span></div>)}</div><p>Until these inputs are independently verified, the site publishes no claimed real-market performance.</p></div></div></section>
      <section className="workflow-section" id="workflow"><div className="workflow-card reveal"><div><span className="eyebrow">OPEN, LOCAL-FIRST, REPRODUCIBLE</span><h2>See the story.<br/><em>Audit the mathematics.</em></h2><P>Python runs the calculations locally. A curated static export powers the web presentation. Research inputs and broker credentials are never sent to the public site.</P><div className="workflow-actions"><a href={GITHUB} target="_blank" rel="noreferrer" className="primary-button"><Github size={18}/> Open the source <ArrowRight size={15}/></a><a className="secondary-button" target="_blank" rel="noreferrer" href={GITHUB+'/blob/research/multi-factor-equity-index/docs/MATHEMATICAL_ACCEPTANCE.md'}>Mathematical validation <ExternalLink size={15}/></a></div></div><div className="workflow-steps"><div><span>01</span><strong>Python</strong><small>Research + tests</small></div><ArrowDown/><div><span>02</span><strong>Approved JSON</strong><small>Aggregate data only</small></div><ArrowDown/><div><span>03</span><strong>React / Vercel</strong><small>Interactive publication</small></div></div></div></section>
    </main>
    <footer><div className="footer-top"><span className="brand"><span className="brand-symbol">∑</span> QUANT <span className="brand-muted">/ RESEARCH</span></span><span>Independent mathematical research project · Not affiliated with MSCI, NSE or Dhan.</span></div><div className="footer-bottom"><span>Educational mathematics, not investment advice. No live trading or broker access.</span><a href={GITHUB} target="_blank" rel="noreferrer">View GitHub <ExternalLink size={12}/></a></div></footer>
  </div>
}
export default App

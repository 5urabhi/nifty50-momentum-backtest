import {useEffect,useState} from 'react'
import {BookOpen,CheckCircle2,Download,FileText,FlaskConical,
  RefreshCw,ShieldAlert,SlidersHorizontal} from 'lucide-react'
import './research-scholar.css'

type Dataset={id:string;label:string;ready:boolean;has_prices:boolean}
type Run={id:string;kind:'model_run'|'research_run';label:string}
type Props={datasets:Dataset[];selectedDataset:string;onSelectDataset:(v:string)=>void;
  runs:Run[];onStartJob:(job:{job_id:string;status:string},title:string)=>void}
type Json=Record<string,unknown>
type Preflight={status:string;blockers:string[];warnings:string[];
  available_monthly_observations:number;preferred_monthly_observations:number;
  factor_weights:Record<string,number>;historical_investability_certified:boolean}
type Passport={dataset:string;kind:string;research_classification:string;
  available_files:{name:string;sha256:string;size_bytes:number}[];
  blockers:{category:string;requirement:string;next_action:string}[];
  observed_prices_available:boolean;investability_certified:boolean;study_status:string}
type SourceCoverage={
  securities_in_observed_panel:number;price_observations:number;
  missing_eligible_prices:number|null;missing_eligible_forward_returns:number|null;
  benchmark_alignment:string;PIT_status:string;
  observed_prevalidation_months:number|null;observed_final_test_months:number|null;
  preferred_prevalidation_months_with_20_percent_buffer:number;
  historical_investability_certified:boolean;warnings:string[];
  missing_security_observations_total:number;
  missing_observation_list_truncated:boolean;
  first_missing_security_observations:{date:string;ticker:string;problem:string}[]
}
type Decision={decision_date:string;dataset_kind:string;rows:{
  ticker:string;member_at_decision:boolean;rank:number|null;score:number|null;
  target_weight:number;weighted_factor_contributions:Record<string,number|null>;
  explanation:string}[];disclosure:string}
type ActiveRisk={annualized_active_tracking_error_estimate:number;
  systematic_fraction:number|null;fitted_observations:number;warning:string;
  factor_contributions:{factor:string;active_exposure:number;
    fraction_total_variance:number|null}[]}
type Hypothesis={id:string;question:string;dataset_id:string;primary_metric:string;
  registered_utc:string;registration_sha256:string;content_unchanged:boolean}
type Paper={markdown:string;source_status:string;source_unchanged:boolean;
  mismatched_input_files:string[];external_research_certified:boolean}
type Explain={model:string;level:string;explanation:string;formula:string;
  metrics?:{name:string;value:number|null;unit:string}[];
  metrics_by_split?:Json;parameters?:Json;limitations?:string[];
  evidence_class:string;warning:string}
const FACTORS=['momentum','low_volatility','value','quality','size','yield']
const nf=(n:number|null|undefined,percent=false)=>
  n===null||n===undefined?'Unavailable':(percent?n*100:n).toLocaleString('en-US',{maximumFractionDigits:4})+(percent?'%':'')
const short=(s:string,n=19)=>s.length>n?s.slice(0,n)+'…':s
async function ask<T>(path:string,body?:Json):Promise<T>{
  const response=await fetch('/api/workspace/'+path,body?{
    method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:undefined)
  if(!response.ok){
    let detail:string='HTTP '+response.status
    try{const payload=await response.json() as {detail?:string}
      detail=payload.detail||detail}catch{}
    throw new Error(detail)
  }
  return response.json() as Promise<T>
}
function Pane({title,children}:{title:string;children:React.ReactNode}){
  return <section className="rw-box"><header className="rw-box-head">
    <h3>{title}</h3></header>{children}</section>
}
function Combo({label,value,onChange,items}:{label:string;value:string;
  onChange:(v:string)=>void;items:{id:string;label:string}[]}){
  return <label className="rw-field"><span>{label}</span><select value={value}
    onChange={e=>onChange(e.target.value)}><option value="">Select…</option>
    {items.map(x=><option key={x.id} value={x.id}>{x.label}</option>)}</select></label>
}
function NumberField({label,value,onChange,min,max,step=1}:{label:string;value:number;
  onChange:(v:number)=>void;min:number;max:number;step?:number}){
  return <label className="rw-field"><span>{label}</span><input type="number"
    value={value} min={min} max={max} step={step} onChange={e=>onChange(Number(e.target.value))}/></label>
}
export default function ResearchScholar({datasets,selectedDataset,onSelectDataset,
  runs,onStartJob}:Props){
  const [tab,setTab]=useState<'index'|'explain'|'passport'|'risk'|'publication'>('index')
  const [name,setName]=useState('NIFTY multi-factor methodology research')
  const [factors,setFactors]=useState<Record<string,number>>({momentum:.5,low_volatility:.5,value:0,quality:0,size:0,yield:0})
  const [topN,setTopN]=useState(10)
  const [maxWeight,setMaxWeight]=useState(.2)
  const [weighting,setWeighting]=useState('equal')
  const [rebalance,setRebalance]=useState(3)
  const [cost,setCost]=useState(10)
  const [lag,setLag]=useState(1)
  const [sectorCap,setSectorCap]=useState<number|null>(null)
  const [riskAversion,setRiskAversion]=useState(3)
  const [turnoverPenalty,setTurnoverPenalty]=useState(.02)
  const [teLimit,setTeLimit]=useState<number|null>(null)
  const [maxTrade,setMaxTrade]=useState<number|null>(null)
  const [liquidityOn,setLiquidityOn]=useState(false)
  const [liquidityAum,setLiquidityAum]=useState(1000000)
  const [liquidityParticipation,setLiquidityParticipation]=useState(.05)
  const [liquidityDays,setLiquidityDays]=useState(3)
  const [liquidityImpact,setLiquidityImpact]=useState(50)
  const [formation,setFormation]=useState(12)
  const [validationStart,setValidationStart]=useState('')
  const [finalTestStart,setFinalTestStart]=useState('')
  const [plan,setPlan]=useState<Preflight|null>(null)
  const [passport,setPassport]=useState<Passport|null>(null)
  const [sourceCoverage,setSourceCoverage]=useState<SourceCoverage|null>(null)
  const [chosenRun,setChosenRun]=useState('')
  const [level,setLevel]=useState('researcher')
  const [explanation,setExplanation]=useState<Explain|null>(null)
  const [decision,setDecision]=useState<Decision|null>(null)
  const [ticker,setTicker]=useState('')
  const [decisionDate,setDecisionDate]=useState('')
  const [risk,setRisk]=useState<ActiveRisk|null>(null)
  const [paper,setPaper]=useState<Paper|null>(null)
  const [hypotheses,setHypotheses]=useState<Hypothesis[]>([])
  const [question,setQuestion]=useState('')
  const [rationale,setRationale]=useState('')
  const [metric,setMetric]=useState('Out-of-sample information ratio')
  const [criterion,setCriterion]=useState('Positive later holdout information ratio after costs')
  const [protocol,setProtocol]=useState('')
  const [error,setError]=useState('')
  const [message,setMessage]=useState('')
  const [busy,setBusy]=useState(false)
  const experiments=runs.filter(x=>x.kind==='research_run')
  const config=()=>({dataset_id:selectedDataset,name,factor_weights:factors,
    top_n:topN,weighting,max_weight:maxWeight,rebalance_every:rebalance,
    cost_bps:cost,execution_lag:lag,momentum_formation:formation,
    momentum_skip:1,volatility_lookback:12,sector_cap:sectorCap,
    optimizer_risk_aversion:riskAversion,
    optimizer_turnover_penalty:turnoverPenalty,
    optimizer_tracking_error_limit:teLimit,
    optimizer_max_trade_weight:maxTrade,
    liquidity_aum:liquidityOn?liquidityAum:null,
    liquidity_max_participation:liquidityParticipation,
    liquidity_execution_days:liquidityDays,
    liquidity_impact_coefficient_bps:liquidityImpact,
    validation_start:validationStart||null,final_test_start:finalTestStart||null})
  const doWork=async<T,>(fn:()=>Promise<T>,done:(x:T)=>void)=>{
    setBusy(true);setError('');setMessage('')
    try{const result=await fn();done(result)}
    catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setBusy(false)}
  }
  const updateSource=(value:string)=>{
    onSelectDataset(value);setPlan(null);setPassport(null);setSourceCoverage(null);setDecision(null);setRisk(null)
  }
  useEffect(()=>{
    let alive=true
    if(selectedDataset){
      void ask<Passport>('passports/'+encodeURIComponent(selectedDataset))
        .then(r=>{if(alive)setPassport(r)})
        .catch(()=>{if(alive)setPassport(null)})
    }
    return()=>{alive=false}
  },[selectedDataset])
  useEffect(()=>{
    let alive=true
    void ask<{hypotheses:Hypothesis[]}>('hypotheses')
      .then(r=>{if(alive)setHypotheses(r.hypotheses)}).catch(()=>{})
    return()=>{alive=false}
  },[])
  const checkSourceCoverage=()=>{
    if(!selectedDataset)return
    const query=new URLSearchParams()
    if(validationStart)query.set('validation_start',validationStart)
    if(finalTestStart)query.set('final_test_start',finalTestStart)
    void doWork(()=>ask<SourceCoverage>(
      'source-coverage/'+encodeURIComponent(selectedDataset)+
      (query.size?'?'+query.toString():'')
    ),setSourceCoverage)
  }
  const preflight=()=>doWork(()=>ask<Preflight>('index-studio/preflight',config()),
    r=>{setPlan(r);setMessage(r.blockers.length?'Repair the listed blockers before executing.':
      'Methodology is software-ready; historical data remain unverified.')})
  const execute=()=>{
    if(!plan||plan.blockers.length||!selectedDataset)return
    if(!window.confirm('Run this index methodology using the SELECTED dataset? '+
      'Historical performance remains unverified until independent data review.'))return
    void doWork(()=>ask<{job_id:string;status:string}>('index-studio/run',
      {experiment:config(),confirm:true}),r=>onStartJob(r,'Multi-Factor Index Studio'))
  }
  const explain=()=>{if(!chosenRun)return
    const selected=runs.find(x=>x.id===chosenRun)
    if(!selected)return
    void doWork(()=>ask<Explain>('explain/'+selected.kind+'/'+encodeURIComponent(chosenRun)+
      '?level='+level),setExplanation)
  }
  const why=()=>{if(!chosenRun)return
    void doWork(()=>ask<Decision>('index-studio/decisions/'+encodeURIComponent(chosenRun)+
       '?'+new URLSearchParams({...(ticker?{ticker}:{}),
           ...(decisionDate?{decision_date:decisionDate}:{})})),setDecision)
  }
  const calculateRisk=()=>{if(!chosenRun)return
    void doWork(()=>ask<ActiveRisk>('active-risk/'+encodeURIComponent(chosenRun)),setRisk)
  }
  const getPaper=()=>{if(!chosenRun)return
    void doWork(()=>ask<Paper>('methodology/'+encodeURIComponent(chosenRun)),setPaper)
  }
  const register=()=>{
    if(!selectedDataset)return
    void doWork(()=>ask<Hypothesis>('hypotheses',{
      question,rationale,planned_dataset_id:selectedDataset,
      primary_metric:metric,success_criterion:criterion,design:protocol
    }),r=>{setHypotheses(items=>[r,...items]);setMessage('Hypothesis recorded with an append-only checksum.')})
  }
  return <div className="rw-stack">
    <div className="rw-segments">
      {([['index','Index Studio'],['explain','Why This Result?'],
         ['passport','Data Passports'],['risk','Active Risk'],
         ['publication','Publication & Protocol']] as const).map(([id,label])=>
        <button key={id} className={tab===id?'active':''} onClick={()=>setTab(id)}>
          {label}</button>)}
    </div>
    <Pane title="Research source — one canonical dataset">
      <p className="rw-help">Index Studio reuses the existing prices, membership, fundamentals and benchmark.
        It never duplicates NIFTY or BANK NIFTY candles or upgrades an unverified dataset.</p>
      <Combo label="Observed / demonstration dataset" value={selectedDataset}
        onChange={updateSource}
        items={datasets.map(x=>({id:x.id,label:x.label+(!x.ready?' · missing required files':'')}))}/>
      {error&&<p className="rw-error" role="alert">{error}</p>}
      {message&&<p className="rw-note" role="status">{message}</p>}
    </Pane>
    {tab==='index'&&<div className="rw-two">
      <Pane title="1 · Define the index methodology">
        <div className="rw-form-grid">
          <label className="rw-field"><span>Study name</span><input value={name}
            onChange={e=>{setName(e.target.value);setPlan(null)}}/></label>
          <Combo label="Portfolio weighting" value={weighting}
            onChange={v=>{setWeighting(v);setPlan(null)}}
            items={['equal','score','inverse_volatility','minimum_variance','risk_parity','benchmark_relative']
              .map(x=>({id:x,label:x.replaceAll('_',' ')}))}/>
          <NumberField label="Selected constituents" value={topN} onChange={v=>{setTopN(v);setPlan(null)}}
            min={2} max={300}/>
          <NumberField label="Maximum security weight" value={maxWeight}
            onChange={v=>{setMaxWeight(v);setPlan(null)}} min={.01} max={1} step={.01}/>
          <NumberField label="Reconstitution frequency (months)" value={rebalance}
            onChange={v=>{setRebalance(v);setPlan(null)}} min={1} max={12}/>
          <NumberField label="Cost per absolute turnover (bps)" value={cost}
            onChange={v=>{setCost(v);setPlan(null)}} min={0} max={500}/>
          <Combo label="Execution assumption" value={String(lag)}
            onChange={v=>{setLag(Number(v));setPlan(null)}}
            items={[{id:'1',label:'One month lag (more conservative)'},
                    {id:'0',label:'Idealized same-close (not executable evidence)'}]}/>
          <NumberField label="Momentum formation months" value={formation}
            onChange={v=>{setFormation(v);setPlan(null)}} min={2} max={60}/>
          <label className="rw-field"><span>Validation start (optional)</span>
            <input type="date" value={validationStart} onChange={e=>{setValidationStart(e.target.value);setPlan(null)}}/></label>
          <label className="rw-field"><span>Frozen test start (optional)</span>
            <input type="date" value={finalTestStart} onChange={e=>{setFinalTestStart(e.target.value);setPlan(null)}}/></label>
        </div>
        {weighting==='benchmark_relative'&&<div className="rw-stack">
          <p className="rw-caution">Benchmark-relative optimization requires actual dated
            benchmark_weights.csv for every modeled security, including explicit zero weights.
            Factor scores are not calibrated alpha forecasts. Risk covariance uses strictly prior returns.</p>
          <div className="rw-form-grid">
            <NumberField label="Risk aversion (annual active variance penalty)" value={riskAversion}
              min={0} max={100} step={.1} onChange={v=>{setRiskAversion(v);setPlan(null)}}/>
            <NumberField label="Target turnover penalty" value={turnoverPenalty}
              min={0} max={100} step={.01} onChange={v=>{setTurnoverPenalty(v);setPlan(null)}}/>
            <label className="rs-check"><input type="checkbox" checked={teLimit!==null}
              onChange={e=>{setTeLimit(e.target.checked ? .15 : null);setPlan(null)}}/>
              Limit annualized predicted tracking error</label>
            {teLimit!==null&&<NumberField label="Tracking error limit (decimal)" value={teLimit}
              min={.005} max={5} step={.01} onChange={v=>{setTeLimit(v);setPlan(null)}}/>}
            <label className="rs-check"><input type="checkbox" checked={maxTrade!==null}
              onChange={e=>{setMaxTrade(e.target.checked ? .2 : null);setPlan(null)}}/>
              Limit each rebalance's single-security trade</label>
            {maxTrade!==null&&<NumberField label="Max trade fraction" value={maxTrade}
              min={.01} max={1} step={.01} onChange={v=>{setMaxTrade(v);setPlan(null)}}/>}
          </div>
        </div>}
        <div className="rs-factor-grid">
          {FACTORS.map(key=><NumberField key={key} label={key.replaceAll('_',' ')+' factor weight'}
            value={factors[key]||0} min={0} max={1} step={.1}
            onChange={v=>{setFactors(old=>({...old,[key]:v}));setPlan(null)}}/>)}
        </div>
        <label className="rs-check"><input type="checkbox" checked={sectorCap!==null}
          onChange={e=>{setSectorCap(e.target.checked?0.4:null);setPlan(null)}}/>
          Constrain sector exposure using effective-dated classifications</label>
        {sectorCap!==null&&<NumberField label="Sector cap" value={sectorCap} min={.1} max={1}
          step={.05} onChange={v=>{setSectorCap(v);setPlan(null)}}/>}
        <div className="rw-stack">
          <label className="rs-check"><input type="checkbox" checked={liquidityOn}
            onChange={e=>{setLiquidityOn(e.target.checked);setPlan(null)}}/>
            Model liquidity, participation limits and square-root market impact</label>
          {liquidityOn&&<><p className="rw-caution">Requires sourced liquidity.csv with
            dated ADV in the same currency as capital and half-spreads in basis points.
            Estimates are not real broker fills. Fixed-bps costs must exclude spreads
            to prevent double counting.</p><div className="rw-form-grid">
            <NumberField label="Research capital (ADV currency)" value={liquidityAum}
              min={1} max={1e15} step={10000} onChange={v=>{setLiquidityAum(v);setPlan(null)}}/>
            <NumberField label="Maximum ADV participation" value={liquidityParticipation}
              min={.001} max={1} step={.01} onChange={v=>{setLiquidityParticipation(v);setPlan(null)}}/>
            <NumberField label="Execution days per rebalance" value={liquidityDays}
              min={1} max={30} onChange={v=>{setLiquidityDays(v);setPlan(null)}}/>
            <NumberField label="Impact coefficient (bps × √participation)" value={liquidityImpact}
              min={0} max={10000} step={5} onChange={v=>{setLiquidityImpact(v);setPlan(null)}}/>
          </div></>}
        </div>
        <div className="rw-button-group"><button disabled={busy||!selectedDataset}
          onClick={()=>void preflight()}><ShieldAlert size={15}/> Check assumptions & data</button>
          <button className="rw-primary" disabled={busy||!plan||!!plan.blockers.length}
            onClick={execute}><FlaskConical size={15}/> Confirm & run methodology</button>
        </div>
      </Pane>
      <Pane title="2 · Validate readiness before calculating">
        {!plan?<p className="rw-help">Run preflight to see the exact source files, factor requirements,
          feasibility constraints and any blockers. Missing source data are never synthesized.</p>:
          <><p className={plan.blockers.length?'rw-caution':'rw-note'}>
            {plan.blockers.length?'Blocked — resolve inputs':'Ready for unverified research computation'}</p>
          <div className="rw-stats"><div><small>Monthly price observations</small>
            <strong>{plan.available_monthly_observations||0}</strong></div>
            <div><small>Suggested research window</small>
              <strong>{plan.preferred_monthly_observations} months</strong></div></div>
          {plan.blockers.map((s,i)=><p className="rw-caution" key={i}>✕ {s}</p>)}
          {plan.warnings.map((s,i)=><p className="rw-help" key={i}>• {s}</p>)}
          </>}
        <hr/><p className="rw-help">Reconstitution dates, factor z-scores, source hashes and
          transaction-cost assumptions are stored in the archived run.
          After completing a run, use Why This Result? to reconstruct each stock's selection.</p>
      </Pane>
    </div>}
    {tab==='passport'&&<Pane title="Research Data Passport — evidence and blocker register">
      {passport?<><div className="rw-stats"><div><small>Source classification</small>
        <strong>{passport.research_classification}</strong></div>
        <div><small>Observed prices</small><strong>{passport.observed_prices_available?'Available':'Missing'}</strong></div>
        <div><small>Investability certified</small><strong>NO</strong></div></div>
        <div className="rw-scroll"><table><thead><tr><th>Input</th><th>Size</th><th>SHA-256</th></tr></thead>
        <tbody>{passport.available_files.map(f=><tr key={f.name}><td>{f.name}</td>
          <td>{f.size_bytes.toLocaleString()}</td><td><code title={f.sha256}>{short(f.sha256,24)}</code></td>
        </tr>)}</tbody></table></div>
        <h4>What is still required for research credibility?</h4>
        {passport.blockers.map((v,i)=><p key={i} className="rw-caution">
          <strong>{v.category}</strong>: {v.requirement}. {v.next_action}</p>)}
        <div className="rw-button-group"><button disabled={busy||!selectedDataset}
          onClick={checkSourceCoverage}>
          <ShieldAlert size={15}/> Inspect actual missing observations</button></div>
        {sourceCoverage&&<section className="rw-stack" aria-label="Observed coverage audit">
          <h4>Observed coverage audit — source data, never invented</h4>
          <div className="rw-stats">
            <div><small>Observed source months</small>
              <strong>{sourceCoverage.price_observations}</strong></div>
            <div><small>Stock universe</small>
              <strong>{sourceCoverage.securities_in_observed_panel}</strong></div>
            <div><small>Missing eligible prices</small>
              <strong>{nf(sourceCoverage.missing_eligible_prices)}</strong></div>
            <div><small>Missing forward returns</small>
              <strong>{nf(sourceCoverage.missing_eligible_forward_returns)}</strong></div>
          </div>
          <p className="rw-help">Benchmark calendar: {sourceCoverage.benchmark_alignment}.
            PIT evidence: {sourceCoverage.PIT_status}. Independently certified: NO.</p>
          <p className="rw-help">Prevalidation sample: {nf(sourceCoverage.observed_prevalidation_months)}
            {' '}months. Preferred sample including a 20% estimation buffer:
            {' '}{sourceCoverage.preferred_prevalidation_months_with_20_percent_buffer} months.
            Frozen final-test months: {nf(sourceCoverage.observed_final_test_months)}.</p>
          {sourceCoverage.warnings.slice(0,14).map((v,i)=>
            <p key={i} className="rw-caution">• {v}</p>)}
          {!!sourceCoverage.first_missing_security_observations.length&&
            <div className="rw-scroll"><table><thead><tr>
              <th>Observed date</th><th>Historical ticker</th><th>Missing evidence</th>
            </tr></thead><tbody>
              {sourceCoverage.first_missing_security_observations.slice(0,60).map((row,i)=>
                <tr key={i}><td>{row.date}</td><td>{row.ticker}</td>
                  <td>{row.problem.replaceAll('_',' ')}</td></tr>)}
            </tbody></table></div>}
          <p className="rw-help">Shown: up to 60 missing rows out of
            {' '}{sourceCoverage.missing_security_observations_total}.
            For the full immutable list, use the coverage-audit research-data preparation command.
            Historical company renames/delistings, dividends, index TRI and filing vintages
            must be sourced; QuantLab never fills these as zeros.</p>
          <a href="https://www.niftyindices.com/reports/historical-data"
            target="_blank" rel="noopener noreferrer">
            Original NSE Indices TRI and monthly reports ↗</a>
          <a href="https://www.nseindia.com/companies-listing/corporate-filings-actions"
            target="_blank" rel="noopener noreferrer">
            Original NSE corporate actions ↗</a>
        </section>}
        </>:<p className="rw-help">Choose a dataset to see its files, immutable checksums, and
          independent verification requirements.</p>}
    </Pane>}
    {tab==='explain'&&<div className="rw-stack">
      <Pane title="Model explainer — tied to the actual saved run">
        <div className="rw-form-grid">
          <Combo label="Saved calculation" value={chosenRun} onChange={v=>{
              setChosenRun(v);setExplanation(null);setDecision(null);setRisk(null);setPaper(null)}}
            items={runs.map(x=>({id:x.id,label:x.label}))}/>
          <Combo label="Explanation depth" value={level} onChange={setLevel}
            items={['beginner','researcher','mathematical'].map(v=>({id:v,label:v}))}/>
        </div><button disabled={!chosenRun||busy} onClick={explain}>
          <BookOpen size={14}/> Understand this calculated result</button>
        {explanation&&<div className="rs-explanation">
          <h4>{explanation.model}</h4><p>{explanation.explanation}</p>
          <h5>Mathematical relation</h5><code>{explanation.formula}</code>
          <h5>Evidence class: {explanation.evidence_class}</h5>
          {explanation.metrics&&<div className="rw-stats">{explanation.metrics.slice(0,12).map((m,i)=>
            <div key={i}><small>{m.name}</small><strong>{String(m.value??'N/A')} {m.unit}</strong></div>)}</div>}
          {explanation.metrics_by_split&&<pre>{JSON.stringify(explanation.metrics_by_split,null,2)}</pre>}
          <p className="rw-caution">{explanation.warning}</p>
        </div>}
      </Pane>
      {runs.find(x=>x.id===chosenRun)?.kind==='research_run'&&<Pane
        title="Why was this security included, excluded or reweighted?">
        <p className="rw-help">Recomputes the archived factor z-scores and constrained weights
          using only the original matching input files; no AI-invented causal story.</p>
        <div className="rw-form-grid"><label className="rw-field"><span>Ticker (optional)</span>
          <input value={ticker} onChange={e=>setTicker(e.target.value)}
            placeholder="All positive-weight constituents"/></label>
        <label className="rw-field"><span>Formation date (optional; exact rebalance)</span>
          <input type="date" value={decisionDate} onChange={e=>setDecisionDate(e.target.value)}/></label></div>
        <button disabled={!chosenRun||busy} onClick={why}><SlidersHorizontal size={15}/> Explain index decisions</button>
        {decision&&<><p className="rw-note">Rebalance {decision.decision_date} · {decision.dataset_kind}</p>
          <div className="rw-scroll"><table><thead><tr>
            <th>Ticker</th><th>Rank</th><th>Score</th><th>Target weight</th><th>Explanation</th>
          </tr></thead><tbody>{decision.rows.map(row=><tr key={row.ticker}>
            <td>{row.ticker}</td><td>{row.rank??'–'}</td><td>{nf(row.score)}</td>
            <td>{nf(row.target_weight,true)}</td><td>{row.explanation}</td>
          </tr>)}</tbody></table></div><p className="rw-caution">{decision.disclosure}</p>
        </>}
      </Pane>}
    </div>}
    {tab==='risk'&&<Pane title="Benchmark-relative active factor risk (B F Bᵀ + D)">
      <p className="rw-help">For a genuine risk decomposition, the selected index dataset must
        contain actual dated benchmark_weights.csv and factor_returns.csv.
        The model estimates regression betas using strictly earlier monthly observations.
        It does not create substitute benchmark weights or proprietary Barra factors.</p>
      <Combo label="Saved index run" value={chosenRun} onChange={v=>{setChosenRun(v);setRisk(null)}}
        items={experiments.map(x=>({id:x.id,label:x.label}))}/>
      <button disabled={!chosenRun||busy} onClick={calculateRisk}>
        <RefreshCw size={15}/> Calculate sourced active-risk attribution</button>
      {risk&&<><div className="rw-stats">
        <div><small>Estimated annualized tracking error</small>
          <strong>{nf(risk.annualized_active_tracking_error_estimate,true)}</strong></div>
        <div><small>Systematic share of active variance</small>
          <strong>{nf(risk.systematic_fraction,true)}</strong></div>
        <div><small>Past monthly observations</small><strong>{risk.fitted_observations}</strong></div>
      </div>
      <div className="rs-factors">{risk.factor_contributions.map(v=>
        <div key={v.factor}><strong>{v.factor}</strong><span>{nf(v.active_exposure)} active exposure</span>
          <div className="rs-factor-bar"><i style={{width:Math.min(100,Math.abs((v.fraction_total_variance||0)*100))+'%'}}/></div>
          <span>{nf(v.fraction_total_variance,true)} of total variance</span>
        </div>)}</div>
        <p className="rw-caution">{risk.warning}</p></>}
    </Pane>}
    {tab==='publication'&&<div className="rw-stack">
      <Pane title="Register a hypothesis before inspecting a final test">
        <p className="rw-help">Timestamped research protocols have append-only identifiers.
          They are local records, not independent notarization or proof that no earlier model search occurred.</p>
        <div className="rw-form-grid">
          <label className="rw-field"><span>Research question</span><input value={question}
            onChange={e=>setQuestion(e.target.value)} placeholder="Can a multi-factor index…?"/></label>
          <label className="rw-field"><span>Primary evaluation metric</span><input value={metric}
            onChange={e=>setMetric(e.target.value)}/></label>
          <label className="rw-field"><span>Preregistered success criterion</span>
            <input value={criterion} onChange={e=>setCriterion(e.target.value)}/></label>
          <label className="rw-field"><span>Rationale</span><textarea value={rationale}
            onChange={e=>setRationale(e.target.value)} rows={3}/></label>
          <label className="rw-field"><span>Frozen data, split, methodology and limitations</span>
            <textarea value={protocol} onChange={e=>setProtocol(e.target.value)} rows={4}/></label>
        </div>
        <button disabled={busy||!selectedDataset||!question||!protocol} onClick={register}>
          <CheckCircle2 size={15}/> Register frozen hypothesis</button>
        {hypotheses.length>0&&<div className="rw-scroll"><table><thead><tr>
          <th>Registered</th><th>Question</th><th>Integrity</th></tr></thead><tbody>
          {hypotheses.slice(0,25).map(h=><tr key={h.id}><td>{h.registered_utc.slice(0,16)}</td>
            <td>{h.question}</td><td>{h.content_unchanged?'Hash intact':'Changed/Unverified'}</td></tr>)}
          </tbody></table></div>}
      </Pane>
      <Pane title="Publish a reproducible methodology and source evidence">
        <Combo label="Archived index experiment" value={chosenRun}
          onChange={v=>{setChosenRun(v);setPaper(null)}}
          items={experiments.map(x=>({id:x.id,label:x.label}))}/>
        <button disabled={busy||!chosenRun} onClick={getPaper}><FileText size={15}/> Generate research manuscript</button>
        {paper&&<><p className="rw-caution">Status: {paper.source_status};
          Independently certified: NO; source unchanged: {String(paper.source_unchanged)}.</p>
          <pre className="rs-paper">{paper.markdown}</pre>
          <a className="rw-download-link" download
            href={'/api/workspace/publications/'+encodeURIComponent(chosenRun)+'.zip'}>
            <Download size={15}/> Export methodology, settings, hashes and results ZIP</a>
          <p className="rw-help">Requires the locally available original market dataset to
            rerun. Numerical reproduction command: python scripts/reproduce_study.py --run-id {chosenRun}</p>
        </>}
      </Pane>
    </div>}
  </div>
}

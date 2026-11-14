import {useEffect,useState} from 'react'
import {BarChart3,Download,FlaskConical,LoaderCircle,ShieldAlert,ShieldCheck} from 'lucide-react'
import ResearchPlot,{type ResearchPlotData} from './ResearchPlots'
import {formatMetric} from './metricDisplay'
import './selection-validation.css'

type Candidate={id:string;title:string;kind:string;mode:string;dataset_id?:string}
type SelectionReport={
  run_ids:string[];dataset_id:string;source_hashes:Record<string,string>;
  evidence_class:string;common_months:number;preferred_common_months:number;
  start:string;end:string;
  pbo:{folds:number;combinations:number;pbo_fraction:number;
    median_oos_rank_percentile:number;
    winner_counts:{run_id:string;selections:number}[];
    blocks:{block:number;first_index:number;last_index:number;observations:number}[];
    rows:Record<string,unknown>[];limitation:string;interpretation:string};
  deflated_sharpe:{
    selected_run_id:string;selected_annualized_zero_rate_sharpe:number;
    threshold_annualized_zero_rate_sharpe:number;deflated_sharpe_probability:number;
    declared_number_of_trials:number;candidate_count:number;assumptions:string;limitation:string};
  regimes:{
    trail_months:number;low_threshold_annual_vol:number;
    high_threshold_annual_vol:number;
    summary:{run_id:string;regime:string;observations:number;
      strategy_mean_monthly_fraction:number|null;active_mean_monthly_fraction:number|null;
      down_month_fraction:number|null}[];
    regime_by_month:Record<string,unknown>[];limitation:string};
  interpretation:string;paired_comparison_warning:string;never_certified:string[]
}
const pct=(n:number)=> (100*n).toFixed(1)+'%'
const saveJSON=(name:string,value:unknown)=>{
  const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}))
  const link=document.createElement('a');link.href=url;link.download=name;link.click()
  window.setTimeout(()=>URL.revokeObjectURL(url),1000)
}
export default function SelectionValidation({runs,currentId,onCompare}:{
  runs:Candidate[];currentId:string;onCompare:()=>void
}){
  const eligible=runs.filter(r=>r.kind==='research_run')
  const [selected,setSelected]=useState<string[]>([])
  const [folds,setFolds]=useState<4|6|8>(4)
  const [declaredTrials,setDeclaredTrials]=useState<number>(2)
  const [trail,setTrail]=useState<3|6|12>(6)
  const [report,setReport]=useState<SelectionReport|null>(null)
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')
  useEffect(()=>{
    setSelected(currentId&&eligible.some(r=>r.id===currentId)?[currentId]:[])
    setReport(null);setError('')
  },[currentId])
  const toggle=(id:string)=>{
    setReport(null);setError('')
    setSelected(old=>old.includes(id)?old.filter(x=>x!==id):
      old.length<8?[...old,id]:old)
  }
  const execute=async()=>{
    if(selected.length<2)return
    setBusy(true);setError('');setReport(null)
    try{
      const r=await fetch('/api/workspace/results/selection-audit',{
        method:'POST',headers:{'Content-Type':'application/json'},
        credentials:'same-origin',
        body:JSON.stringify({run_ids:selected,folds,declared_trials:Math.max(selected.length,declaredTrials),
          benchmark_trail:trail})})
      if(!r.ok){
        let info:unknown=null
        try{info=await r.json()}catch{}
        const message=info&&typeof info==='object'&&'detail' in info?
          String((info as {detail:unknown}).detail):'Research engine returned HTTP '+r.status
        throw new Error(message)
      }
      const result=await r.json() as SelectionReport
      setReport(result)
    }catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setBusy(false)}
  }
  const validSelected=selected.length>=2
  const availableYears=report?(report.common_months/12).toFixed(1):''
  const regimeData=report?.regimes.summary.filter(x=>x.run_id===report.deflated_sharpe.selected_run_id)||[]
  const regimePlot:ResearchPlotData|null=regimeData.length?{
    kind:'bar2d',title:'Selected candidate · monthly active return by market-volatility regime',
    x:regimeData.map(x=>x.regime),x_label:'Retrospective trailing benchmark volatility',
    y_label:'Mean monthly active return (fraction)',
    traces:[{name:'Selected candidate',y:regimeData.map(x=>x.active_mean_monthly_fraction)}]
  }:null
  return <div className="sv-root">
    <section className="rs-panel">
      <div className="rs-panel-heading"><div><span className="rs-kicker">
        MODEL-SELECTION RESEARCH / SOURCE-BOUND</span>
        <h3>Overfitting, multiple testing & market regimes</h3>
        <p className="rs-small">Choose archived index experiments using the same exact input
          hashes and benchmark on at least 48 common monthly dates. No missing observations
          are inferred. These are exploratory diagnostics, not a tradable forecast.</p></div>
        <button onClick={onCompare}><BarChart3 size={14}/> Standard comparisons</button>
      </div>
      <div className="sv-form">
        <fieldset><legend>1 · Select 2–8 saved index runs</legend>
          <div className="sv-choices">{eligible.map(r=><label key={r.id}>
            <input type="checkbox" checked={selected.includes(r.id)}
              onChange={()=>toggle(r.id)} disabled={busy||(!selected.includes(r.id)&&selected.length>=8)}/>
            <span><strong>{r.title}</strong><small>{r.id} · {r.mode}</small></span>
          </label>)}</div>
          {eligible.length<2&&<p className="rs-warning">Save at least two distinct index runs
            on the same actual or synthetic source, then return here. Synthetic inputs
            remain synthetic in every analysis.</p>}
          <p className="rs-small">{selected.length} selected · The engine independently
            verifies original source hashes, matching benchmark returns, and common dates.</p>
        </fieldset>
        <fieldset><legend>2 · Declare your validation design</legend>
          <label>Contiguous CSCV partitions
            <select value={folds} onChange={e=>{setFolds(Number(e.target.value) as 4|6|8);setReport(null)}}>
              <option value={4}>4 blocks · 48 common months required</option>
              <option value={6}>6 blocks · 72 common months required</option>
              <option value={8}>8 blocks · 96 common months required</option>
            </select></label>
          <label>All tried model configurations (including discarded runs)
            <input type="number" min={Math.max(2,selected.length)} max={10000}
              value={declaredTrials} onChange={e=>{setDeclaredTrials(Number(e.target.value));setReport(null)}}/>
          </label>
          <label>Backward-looking benchmark volatility window
            <select value={trail} onChange={e=>{setTrail(Number(e.target.value) as 3|6|12);setReport(null)}}>
              <option value={3}>3 months</option><option value={6}>6 months</option>
              <option value={12}>12 months</option>
            </select></label>
          <p className="rs-small">Disclose the full number of configurations you tested,
            including abandoned attempts. CSCV uses combinations of retrospective
            blocks—not a chronological future-only holdout or label-purged CPCV.</p>
          <button className="rs-primary" type="button" disabled={busy||!validSelected||
            !Number.isInteger(declaredTrials)||declaredTrials<selected.length||declaredTrials>10000}
            onClick={()=>void execute()}>
            {busy?<LoaderCircle size={14}/>:<FlaskConical size={14}/>}
            {busy?'Computing matched saved returns…':'Run full model-selection audit'}
          </button>
        </fieldset>
      </div>
      {error&&<div className="rs-error" role="alert"><ShieldAlert size={14}/>{error}</div>}
    </section>
    {report&&<section className="rs-panel" aria-label="Model-selection research results">
      <div className="rs-panel-heading"><div>
        <span className="rs-kicker">MATHEMATICAL RESEARCH / NOT INDEPENDENTLY CERTIFIED</span>
        <h3>Computed overfitting and regime diagnostics</h3>
        <p className="rs-small">{report.common_months} common months ({availableYears} years) ·
          {' '}{report.start} to {report.end} · {report.evidence_class.replaceAll('_',' ')}</p>
      </div><button type="button" onClick={()=>saveJSON('quantlab_selection_audit.json',report)}>
        <Download size={14}/> Complete audit JSON</button></div>
      <div className="rs-kpi-grid">
        <article><small>Retrospective probability of backtest overfitting</small>
          <strong>{pct(report.pbo.pbo_fraction)}</strong><span>{report.pbo.combinations}
            {' '}symmetric train/test combinations; not a future-loss probability</span></article>
        <article><small>Deflated Sharpe statistic · approximate probability</small>
          <strong>{pct(report.deflated_sharpe.deflated_sharpe_probability)}</strong>
          <span>{report.deflated_sharpe.declared_number_of_trials}
            {' '}declared tried configurations · zero risk-free assumption</span></article>
        <article><small>Selected candidate · annualized Sharpe</small>
          <strong>{formatMetric('Sharpe',report.deflated_sharpe.selected_annualized_zero_rate_sharpe,'ratio').value}</strong>
          <span>Full-sample selected winner · {report.deflated_sharpe.selected_run_id}</span></article>
        <article><small>Search-adjusted Sharpe hurdle</small>
          <strong>{formatMetric('Sharpe',report.deflated_sharpe.threshold_annualized_zero_rate_sharpe,'ratio').value}</strong>
          <span>Approximate expected maximum Sharpe under the declared trials</span></article>
      </div>
      <div className="sv-grids">
        <div><h4>How often each candidate won the in-split selection</h4>
          <div className="sv-table"><table><thead><tr><th>Saved candidate</th><th>Times selected</th></tr></thead>
            <tbody>{report.pbo.winner_counts.map(w=><tr key={w.run_id}>
              <td>{w.run_id}</td><td>{w.selections} of {report.pbo.combinations}</td></tr>)}</tbody>
          </table></div></div>
        <div><h4>Trailing benchmark-volatility regimes</h4>
          <div className="sv-table"><table><thead><tr><th>Candidate</th><th>Regime</th>
            <th>Months</th><th>Monthly active return</th><th>Down months</th></tr></thead>
            <tbody>{report.regimes.summary.map((r,i)=><tr key={r.run_id+'-'+i}>
              <td>{r.run_id}</td><td>{r.regime}</td><td>{r.observations}</td>
              <td>{formatMetric('Active return',r.active_mean_monthly_fraction,'fraction').value}</td>
              <td>{formatMetric('Down month rate',r.down_month_fraction,'decimal fraction').value}</td>
            </tr>)}</tbody></table></div></div>
      </div>
      {regimePlot&&<ResearchPlot plot={regimePlot} provenance={report.evidence_class}/>}
      <h4>Scope and unresolved evidence</h4>
      <div className="sv-warnings">
        {[report.pbo.limitation,report.deflated_sharpe.assumptions,
          report.deflated_sharpe.limitation,report.regimes.limitation,
          ...report.never_certified].map((txt,i)=><p key={i}><ShieldAlert size={13}/>{txt}</p>)}
      </div>
      <div className="rs-check"><ShieldCheck size={14}/>
        File checksums and a reproducible calculation do NOT mean vendor data or historical
        investment performance were independently audited.</div>
    </section>}
  </div>
}

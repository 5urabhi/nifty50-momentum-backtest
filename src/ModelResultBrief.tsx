import {ArrowRight, BarChart3, BookOpen, ShieldCheck} from 'lucide-react'
import './model-result-brief.css'

type Observation={label:string;value:number|string|null;unit:string}
type BriefInput={
  model_id:string;title:string;mode:string;metrics:Observation[];
  plots:{title:string;kind:string}[];
  limitations:string[];notes:string[];
  calibration?:Record<string,unknown>;
  source?:{
    dataset_label?:string;dataset_kind?:string;
    is_synthetic_fixture?:boolean;assets?:string[];
    observations?:number;from_date?:string;to_date?:string;
    source_file?:string;source_evidence?:string
  }|null
}

const finite=(value:unknown):value is number=>typeof value==='number'&&Number.isFinite(value)
const fmt=(value:number)=>value.toLocaleString('en-US',{maximumFractionDigits:4})
const pairMetrics=(metrics:Observation[])=>{
  const pairs=[
    ['Held-out one-step log-return RMSE','Zero-drift baseline held-out RMSE','RMSE'],
    ['Held-out one-step RMSE','Flat-volatility benchmark RMSE','RMSE'],
    ['Held-out variance RMSE','No-change variance RMSE','RMSE'],
    ['Held-out moment-matched log likelihood','Historical Gaussian baseline log likelihood','Log likelihood'],
  ]
  for(const [study,baseline,kind] of pairs){
    const a=metrics.find(m=>m.label===study)?.value
    const b=metrics.find(m=>m.label===baseline)?.value
    if(!finite(a)||!finite(b))continue
    if(kind==='RMSE'){
      if(b===0)return {headline:'Baseline error is zero',detail:
        'The selected model cannot show an RMSE improvement over a zero-error baseline.', tone:'neutral'}
      const delta=(b-a)/Math.abs(b)*100
      return {headline:Math.abs(delta)<.01?'Essentially tied with baseline':
        `${fmt(Math.abs(delta))}% ${delta>0?'lower':'higher'} holdout RMSE`,
        detail:`Model: ${fmt(a)} · baseline: ${fmt(b)}. Smaller RMSE is better. `+
          'This is one retrospective split, not proof of future accuracy.',
        tone:delta>0?'good':delta<0?'caution':'neutral'}
    }
    const delta=a-b
    return {headline:delta>0?'Higher held-out average log likelihood':
      delta<0?'Lower held-out average log likelihood':'Tied held-out average log likelihood',
      detail:`Model: ${fmt(a)} · Gaussian baseline: ${fmt(b)}. `+
        'Larger average log likelihood is better, but the comparison uses a '+
        'moment-matched normal approximation, not an exact jump-mixture fit.',
      tone:delta>0?'good':delta<0?'caution':'neutral'}
  }
  return null
}

export default function ModelResultBrief({
  result,onOpenFigures,onOpenMetrics,onOpenMethod,
}:{
  result:BriefInput;onOpenFigures:()=>void;onOpenMetrics:()=>void;
  onOpenMethod:()=>void;
}){
  const calibration=result.calibration
  const training=calibration?.train_count
  const testing=calibration?.test_count
  const split=Number.isInteger(training)&&Number.isInteger(testing)&&
    Number(training)>0&&Number(testing)>0
  const fixture=!!result.source?.is_synthetic_fixture||
    result.source?.dataset_kind==='synthetic'
  const hasQuotedInput=result.mode==='market'
  const historical=result.mode==='historical'
  const seeded=result.mode==='synthetic'
  const proxy=result.model_id==='heston_proxy'
  const baseline=pairMetrics(result.metrics)
  const provenance=fixture?'SYNTHETIC TEST FIXTURE':
    hasQuotedInput?'ORIGINAL QUOTE INPUT · MODEL VALUATION':
    historical?'HISTORICAL INPUT · MODEL RESULT':
    seeded?'SEEDED SCENARIO · ARTIFICIAL PATHS':'THEORETICAL FORMULA'
  const source=hasQuotedInput?
    'An original provider quote is the model input; the price, Greeks, implied volatility '+
    'or surface are still computed outputs. The same quote is used for volatility calibration.':
    fixture?'The source dataset contains synthetic fixture values. Results are for '+
      'software testing and cannot be cited as observed market evidence.':
    historical?'Original saved historical observations determine the model inputs. '+
      (split?'A final chronological segment is not used for parameter fitting within this run.':
        'This computation does not establish held-out predictive performance.'):
    seeded?'Paths are artificial but reproducible with the same seed.':
      'Parameters are user-chosen assumptions, not measured premiums or returns.'
  const next=proxy?
    'A stock-price variance proxy cannot replace risk-neutral Heston calibration. '+
    'For options-surface analysis, use real quotes across strikes and expiries.':
    historical&&split?
      'Review the observed-vs-model graph and compare the held-out statistic against its '+
      'baseline. Test another frozen historical window before interpreting market performance.':
    hasQuotedInput?
      'Inspect bid/ask spread, quoted timestamp and the assumed rate and dividend yield. '+
      'Compare additional independent contracts before claiming pricing accuracy.':
    seeded?'For observed parameter estimates, switch to this model’s historical-data companion.':
    historical?'Inspect numerical convergence, source coverage and robustness before drawing conclusions.':
      'Switch to the observed-quote companion for actual contract inputs, where available.'
  const caveat=result.limitations.find(note=>/HISTORICAL|NOT |RISK|FITT|OVERLAP|IN-SAMPLE|STALE|CONVENTION|SYNTHETIC/i.test(note))||
    result.limitations[0]||'This result is model-conditional; no trading performance is certified.'
  return <section className="ql-interpretation" aria-label="Research interpretation">
    <div className="ql-interpretation-head">
      <div><span className="ql-kicker">QUANTLAB / RESEARCH INTERPRETATION</span>
        <h3>What does this result establish?</h3>
        <p>Computed facts and limitations—not an AI-generated trading recommendation.</p></div>
      <span className="ql-interpretation-badge">{provenance}</span>
    </div>
    <div className="ql-interpretation-grid">
      <article>
        <div className="ql-interpretation-icon"><ShieldCheck size={17}/></div>
        <h4>Evidence</h4>
        <p>{source}</p>
        {split&&<small>{String(training)} training observations · {String(testing)} held out
          {result.source?.assets?.length?' · '+result.source.assets.join(', '):''}</small>}
      </article>
      <article className={baseline?'ql-interpretation-'+baseline.tone:''}>
        <div className="ql-interpretation-icon"><BarChart3 size={17}/></div>
        <h4>{baseline?'Measured comparison':'Available computation'}</h4>
        <strong>{baseline?.headline||(`${result.metrics.length} measured outputs · ${result.plots.length} figure(s)`)}</strong>
        <p>{baseline?.detail||'No comparable out-of-sample baseline was included. '+
          'Do not interpret a fitted value or a visually plausible chart as predictive accuracy.'}</p>
      </article>
      <article>
        <div className="ql-interpretation-icon"><BookOpen size={17}/></div>
        <h4>Next research action</h4>
        <p>{next}</p>
        <small>Primary limitation: {caveat}</small>
      </article>
    </div>
    <div className="ql-interpretation-actions">
      <button type="button" onClick={onOpenFigures}>Explore figures <ArrowRight size={14}/></button>
      <button type="button" onClick={onOpenMetrics}>Inspect exact metrics <ArrowRight size={14}/></button>
      <button type="button" onClick={onOpenMethod}>Method & limitations <ArrowRight size={14}/></button>
    </div>
  </section>
}

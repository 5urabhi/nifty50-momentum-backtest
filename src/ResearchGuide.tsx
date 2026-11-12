import {useState} from 'react'
import {Activity, ArrowRight, BookOpen, CheckCircle2, CircleAlert,
  Database, FlaskConical, GitBranch, HelpCircle, Layers, Search, ShieldCheck} from 'lucide-react'
import './model-lab.css'
import './guide.css'

type Props={onNavigate:(route:string)=>void}
const STEPS=[
 {n:'01',title:'Download observed data',text:'In Dhan Market Data choose historical NIFTY 50 or BANK NIFTY constituents, select dates and candle resolution. The app reconstructs dated index membership and downloads separate stock and index spot candles.',route:'dhan',cta:'Market data'},
 {n:'02',title:'Prepare a dataset',text:'Open a completed download and use Prepare research dataset. Existing minute candles become daily/monthly prices and dated membership; then prepare a clearly labeled price-index benchmark from saved spot candles.',route:'data',cta:'Data manager'},
 {n:'03',title:'Run an index strategy',text:'In Index Research choose the prepared dataset, select factor weights, portfolio weighting, rebalance schedule and execution lag. Short date histories may leave too few valid months; keep the sample-length warnings visible.',route:'research',cta:'Index research'},
 {n:'04',title:'Explore a mathematical model',text:'In Advanced Mathematics or Quantitative Models select a family, model and valid inputs. Synthetic demonstrations do not need a market dataset; empirical fits need adequate observed returns.',route:'mathematics',cta:'Model laboratory'},
 {n:'05',title:'Inspect, compare, export',text:'Use 2D/3D Graphs for computed plots, Results & Diagnostics for exact values and lineage, Saved Runs for factor experiments, and Research Reports for available reproducible artifacts.',route:'history',cta:'Saved runs'},
]
const TOPICS=[
 {title:'What is the difference between an index run and a model run?',text:'Index Research simulates a rules-based factor portfolio with point-in-time eligibility, costs and execution lag. Model Laboratory performs mathematical/theoretical experiments, in-sample statistical fits or seeded simulations. A model-lab output is not automatically an investable backtest.'},
 {title:'What does FILES COMPLETE actually mean?',text:'It means required CSV inputs exist and passed structural preparation. It is NOT a certificate of corporate-action correctness, adjusted total returns, exchange-grade tick reconstruction or audited out-of-sample performance.'},
 {title:'Is the downloaded NIFTY index benchmark TRI?',text:'No. Dhan IDX_I spot is a price index and omits reinvested dividends. QuantLab labels it PRICE INDEX (not TRI). For a total-return comparison acquire independent NIFTY TRI data and adjusted constituent returns, then conduct an audit.'},
 {title:'Why does GARCH or EVT refuse my dataset?',text:'GARCH requires at least 60 common observed returns; peaks-over-threshold EVT is even more data-intensive. The laboratory uses daily_prices.csv when present, otherwise monthly prices.csv. It will reject insufficient overlap rather than fabricate observations or fill missing prices.'},
 {title:'How do I change models and compare results?',text:'Choose Advanced Mathematics or Quantitative Models, select a family tab (Stochastic, Econometrics, Derivatives, Optimization, Tail Risk, 3D), click an algorithm, set validated parameters and Run. Results include model type, provenance, sample count and downloadable JSON/CSV. To compare, use consistent input windows and keep the exported settings.'},
 {title:'Which graphs are real and which are simulations?',text:'All graphs are generated from Python outputs. Observed mode uses stored prices; synthetic mode uses seeded model paths; theoretical mode uses assumed inputs. The 3D option surface is analytical BSM mathematics, while the 3D correlation stress surface uses observed marginal volatilities with an explicitly hypothetical correlation axis.'},
 {title:'Can I use the factor Value / Quality / Size sliders?',text:'Only when publication-dated fundamentals.csv exists. The backend rejects these factors otherwise. Momentum and low-volatility signals can be built from observed prices; never infer company fundamentals from future financial statements.'},
 {title:'What about Random Forest, XGBoost, LSTM, PPO or SAC?',text:'Those are not claimed to be trained or benchmarked in this version. The mathematical model catalog contains 26 connected traditional, stochastic, optimization and risk algorithms. Supervised ML and reinforcement-learning agents require a separate, leak-free train/test framework, realistic costs and market-specific execution data.'},
 {title:'Why are some CAGR and drawdown fields blank?',text:'The effective period after a 12-month factor formation window, skip month and execution lag can leave zero or very few observations on a one-year dataset. A dash means the metric is unavailable—not zero and not an implemented forecasting success. Download a longer historical window for meaningful validation.'},
 {title:'How do I protect my Dhan token?',text:'Store DHAN_ACCESS_TOKEN in a project-root .env file, never in a screenshot, Git commit, log or browser localStorage. Use Verify Dhan API access for a read-only profile check. The Python workstation is localhost-only and never places broker orders.'},
]
const GLOSSARY=[
 ['PIT','Point-in-time: index eligibility, records and published financial data use their historical effective/availability dates.'],
 ['TRI','Total Return Index, including reinvested distributions; distinct from NIFTY spot price index.'],
 ['OHLCV','Open, High, Low, Close and Volume observed market data for a time interval.'],
 ['GARCH','Conditional variance autoregression fitted on observed historical returns.'],
 ['VaR / ES','Value at Risk and Expected Shortfall / tail mean; loss measures, not guaranteed loss bounds.'],
 ['EWMA','Exponentially weighted moving average covariance estimator or volatility forecast.'],
 ['PCA','Principal component decomposition of standardized return histories.'],
 ['Out-of-sample','Dates not used in model fitting or tuning; necessary for credible predictive claims.'],
 ['CVaR','Conditional Value at Risk optimization based on supplied scenario losses.'],
]
export default function ResearchGuide({onNavigate}:Props){
  const [query,setQuery]=useState('')
  const filtered=TOPICS.filter(item=>(item.title+' '+item.text).toLowerCase().includes(query.toLowerCase()))
  return <div className="qg-guide">
    <section className="qg-hero"><div><div className="ql-kicker">USER MANUAL / VERSIONED RESEARCH WORKFLOWS</div>
      <h2>From market data to reproducible evidence.</h2>
      <p>QuantLab is a private, local-first quantitative research workbench. This guide explains what to click, what each screen means, and how to avoid overstating backtests or simulations.</p>
      <div className="qg-doc-buttons">
        <a href="/api/guide/user-guide" target="_blank" rel="noreferrer"><BookOpen size={15}/> Full user guide <ArrowRight size={13}/></a>
        <a href="/api/guide/model-catalog" target="_blank" rel="noreferrer"><Layers size={15}/> Model mathematics catalog <ArrowRight size={13}/></a>
        <a href="/api/guide/reproducibility" target="_blank" rel="noreferrer"><GitBranch size={15}/> Research & reproducibility <ArrowRight size={13}/></a>
        <a href="/api/docs" target="_blank" rel="noreferrer"><Database size={15}/> Interactive API docs <ArrowRight size={13}/></a>
      </div></div><div className="qg-hero-icon"><FlaskConical size={42}/></div></section>
    <section className="qg-panel">
      <div className="qg-head"><CheckCircle2 size={18}/><h3>Quick start · five steps</h3></div>
      <div className="qg-steps">{STEPS.map(step=><article key={step.n}>
        <div className="qg-number">{step.n}</div><div><h4>{step.title}</h4><p>{step.text}</p>
          <button type="button" onClick={()=>onNavigate(step.route)}>{step.cta}<ArrowRight size={13}/></button>
        </div></article>)}</div>
    </section>
    <div className="qg-two">
      <section className="qg-panel">
        <div className="qg-head"><HelpCircle size={18}/><h3>Help by topic</h3></div>
        <label className="qg-search"><Search size={17}/>
          <input type="search" value={query} onChange={e=>setQuery(e.target.value)}
            placeholder="Search models, data, graphs, errors…" aria-label="Search user documentation"/></label>
        <div className="qg-accordions">
          {filtered.map(item=><details key={item.title}><summary>{item.title}</summary><p>{item.text}</p></details>)}
          {filtered.length===0&&<p className="ql-muted">No matching help topics. Try “model”, “benchmark”, “GARCH” or “data”.</p>}
        </div>
      </section>
      <div className="qg-stack">
        <section className="qg-panel"><div className="qg-head"><BookOpen size={18}/><h3>Research glossary</h3></div>
          <dl className="qg-glossary">{GLOSSARY.map(([term,desc])=><div key={term}><dt>{term}</dt><dd>{desc}</dd></div>)}</dl>
        </section>
        <section className="qg-panel qg-integrity">
          <div className="qg-head"><ShieldCheck size={18}/><h3>Interpretation policy</h3></div>
          <p><strong>Computed does not mean verified.</strong> Workstation models use strict source labels: theoretical, seeded synthetic or observed data.</p>
          <p>A result must demonstrate adequate sample size, time-vintage-safe input handling, costs and holdout validation before being described as investment performance.</p>
          <button type="button" onClick={()=>onNavigate('mathematics')}><Activity size={15}/> Open Model Laboratory <ArrowRight size={14}/></button>
          <div className="qg-note"><CircleAlert size={16}/><span>No broker order endpoints are used by the research engine.</span></div>
        </section>
      </div>
    </div>
  </div>
}

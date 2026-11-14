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
 {n:'05',title:'Save, compare and publish',text:'Open Research Workspace to save reusable configurations, compare saved model results, create notebooks, inspect dataset quality and build downloadable reports.',route:'workspace',cta:'Research Workspace'},
]
const TOPICS=[
 {title:'What is the difference between an index run and a model run?',text:'Index Research simulates a rules-based factor portfolio with point-in-time eligibility, costs and execution lag. Model Laboratory performs mathematical/theoretical experiments, in-sample statistical fits or seeded simulations. A model-lab output is not automatically an investable backtest.'},
 {title:'What does FILES COMPLETE actually mean?',text:'It means required CSV inputs exist and passed structural preparation. It is NOT a certificate of corporate-action correctness, adjusted total returns, exchange-grade tick reconstruction or audited out-of-sample performance.'},
 {title:'Is the downloaded NIFTY index benchmark TRI?',text:'No. Dhan IDX_I spot is a price index and omits reinvested dividends. QuantLab labels it PRICE INDEX (not TRI). For a total-return comparison acquire independent NIFTY TRI data and adjusted constituent returns, then conduct an audit.'},
 {title:'Why does GARCH or EVT refuse my dataset?',text:'GARCH requires at least 60 common observed returns; peaks-over-threshold EVT is even more data-intensive. The laboratory uses daily_prices.csv when present, otherwise monthly prices.csv. It will reject insufficient overlap rather than fabricate observations or fill missing prices.'},
 {title:'How do I ask QuantLab to explain my saved results?',text:'Open Results Studio, select a saved experiment, and choose Ask QuantLab. Ask about Sharpe, CAGR, sources, missing evidence, model mathematics, and the next defensible test. The assistant reads actual archived metrics and evidence. It is offline and deterministic, not an LLM or a trading recommender. Click each citation to inspect the exact saved audit. Missing measurements are not invented.'},
 {title:'How do I change models and compare results?',text:'In Advanced Mathematics or Quantitative Models choose a family and algorithm, then save the model preset. Open Research Workspace → Compare & Graph to load 2–8 saved runs, select figures, enforce compatible axes for overlays, or view independent 2D/3D surfaces side by side. Save/export the graph and attach findings to a notebook.'},
 {title:'Which graphs are real and which are simulations?',text:'All graphs are generated from Python outputs. Observed mode uses stored prices; synthetic mode uses seeded model paths; theoretical mode uses assumed inputs. The 3D option surface is analytical BSM mathematics, while the 3D correlation stress surface uses observed marginal volatilities with an explicitly hypothetical correlation axis.'},
 {title:'Can I use the factor Value / Quality / Size sliders?',text:'Only when publication-dated fundamentals.csv exists. The backend rejects these factors otherwise. Momentum and low-volatility signals can be built from observed prices; never infer company fundamentals from future financial statements.'},
 {title:'What about Random Forest, XGBoost, LSTM, PPO or SAC?',text:'Those are not claimed to be trained or benchmarked in this version. The mathematical model catalog contains 26 connected traditional, stochastic, optimization and risk algorithms. Supervised ML and reinforcement-learning agents require a separate, leak-free train/test framework, realistic costs and market-specific execution data.'},
 {title:'Why are some CAGR and drawdown fields blank?',text:'The effective period after a 12-month factor formation window, skip month and execution lag can leave zero or very few observations on a one-year dataset. A dash means the metric is unavailable—not zero and not an implemented forecasting success. Download a longer historical window for meaningful validation.'},
 {title:'How do I protect my Dhan token?',text:'Store DHAN_ACCESS_TOKEN in a project-root .env file, never in a screenshot, Git commit, log or browser localStorage. Use Verify Dhan API access for a read-only profile check. The Python workstation is localhost-only and never places broker orders.'},
]
TOPICS.push(
 {title:'Can I archive or delete a dataset?',text:'Open Research Workspace → Library. Archiving hides a dataset. Only user-imported or derived Dhan views can go to recoverable Trash; raw shared history is protected. Results and notebooks referencing the dataset prevent unsafe deletion.'},
 {title:'Where are my presets, charts, reports and notes stored?',text:'Research Workspace stores versioned metadata in the local SQLite research library and immutable model outputs under results/. Export notebooks to JSON and reports to HTML, Markdown or PDF. Never put API secrets in notes.'},
 {title:'How does walk-forward testing avoid lookahead?',text:'Training returns end before each subsequent holdout fold. Portfolio weights are frozen across each testing step. The confidence interval is exploratory and cannot fix missing dividends, constituent-vintage errors or repeated model selection.'}
)
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
const METRICS:{name:string;formula:string;meaning:string;caveat:string}[]=[
 {name:'Expected Shortfall (ES / CVaR)',formula:'ES(alpha) = E[loss | loss >= VaR(alpha)]',
  meaning:'Average tail loss beyond a specified quantile of observed losses.',
  caveat:'Highly sensitive to sample length, tail count, changing regimes and unadjusted prices.'},
 {name:'Value at Risk (VaR)',formula:'VaR(alpha) = quantile_alpha(-return)',
  meaning:'Loss threshold exceeded in approximately 1-alpha of observations.',
  caveat:'A 95% VaR does not bound the worst 5% of losses.'},
 {name:'Maximum drawdown',formula:'min_t(wealth_t / max_{s<=t}(wealth_s) - 1)',
  meaning:'Largest observed peak-to-trough portfolio decline.',
  caveat:'Path-based statistic; does not predict future or intraday drawdown.'},
 {name:'Annualized volatility',formula:'sqrt(K) x sample_std(return)',
  meaning:'Sample return dispersion scaled by the assumed number of periods per year.',
  caveat:'Square-root-of-time scaling may fail with volatility clustering.'},
 {name:'Sharpe ratio',formula:'sqrt(K) x mean(excess_return) / std(excess_return)',
  meaning:'Historical return per unit of total return variability.',
  caveat:'Use aligned risk-free rates and periods. A high in-sample Sharpe is not proof of alpha.'},
 {name:'Sortino ratio',formula:'sqrt(K) x mean(return - target) / downside_deviation',
  meaning:'Downside volatility-adjusted average return relative to a target.',
  caveat:'Depends strongly on target and the number of below-target observations.'},
 {name:'Tracking error',formula:'sqrt(K) x std(strategy_return - benchmark_return)',
  meaning:'Active return dispersion relative to the reference index.',
  caveat:'Requires a compatible benchmark; price-index and TRI returns are not interchangeable.'},
 {name:'Information ratio',formula:'sqrt(K) x mean(active_return) / std(active_return)',
  meaning:'Historical active return per unit of tracking error.',
  caveat:'Backtested selection and costs must be audited; requires valid holdout evidence.'},
 {name:'Risk parity contribution',formula:'RC_i = weight_i x (covariance_matrix x weights)_i',
  meaning:'Each holding’s contribution to portfolio variance.',
  caveat:'Dependent on fitted covariance, not a causal measure.'},
 {name:'Herfindahl concentration',formula:'HHI = sum_i(weight_i ^ 2); effective N = 1 / HHI',
  meaning:'Simple allocation concentration measure.',
  caveat:'Does not detect hidden correlation or leverage without exposure normalization.'},
 {name:'Newey–West HAC',formula:'Var(mean) = (gamma_0 + 2 sum_k kernel(k) gamma_k) / n',
  meaning:'Serial-dependence and heteroskedasticity-aware asymptotic mean uncertainty.',
  caveat:'Lag choice and pretesting affect inference; cannot correct test selection.'},
 {name:'Holm-adjusted significance',formula:'p_adj(sorted k) = max_prior((m-k+1) x p_sorted_k)',
  meaning:'Familywise multiplicity adjustment across observed tests.',
  caveat:'Only valid if individual p-values and selection protocol are defensible.'},
 {name:'Block-bootstrap confidence interval',formula:'CI = percentile_2.5,97.5 of block-resampled mean',
  meaning:'Exploratory uncertainty interval retaining some short-range dependence.',
  caveat:'Choice of block length and stationarity assumptions remain important.'},
 {name:'Out-of-sample R²',formula:'R²_OOS = 1 - MSE(model, later data) / MSE(train-mean baseline)',
  meaning:'Predictive error improvement relative to a benchmark fitted only on training data.',
  caveat:'Negative values indicate worse performance than the benchmark.'},
 {name:'Factor-proxy beta',formula:'OLS target_return = alpha + sum(beta_i x proxy_return_i) + error',
  meaning:'Statistical loading on observed return-series proxies.',
  caveat:'Not formal index/style attribution without well-defined published factor vintages.'},
]
export default function ResearchGuide({onNavigate}:Props){
  const [query,setQuery]=useState('')
  const [selectedMetric,setSelectedMetric]=useState(METRICS[0].name)
  const filtered=TOPICS.filter(item=>(item.title+' '+item.text).toLowerCase().includes(query.toLowerCase()))
  return <div className="qg-guide">
    <section className="qg-hero"><div><div className="ql-kicker">USER MANUAL / VERSIONED RESEARCH WORKFLOWS</div>
      <h2>From market data to reproducible evidence.</h2>
      <p>QuantLab is a private, local-first quantitative research workbench. This guide explains what to click, what each screen means, and how to avoid overstating backtests or simulations.</p>
      <div className="qg-doc-buttons">
        <a href="/api/guide/user-guide" target="_blank" rel="noreferrer"><BookOpen size={15}/> Full user guide <ArrowRight size={13}/></a>
        <a href="/api/guide/model-catalog" target="_blank" rel="noreferrer"><Layers size={15}/> Model mathematics catalog <ArrowRight size={13}/></a>
        <a href="/api/guide/workspace" target="_blank" rel="noreferrer"><BookOpen size={15}/> Research Workspace manual <ArrowRight size={13}/></a>
        <a href="/api/guide/metrics" target="_blank" rel="noreferrer">
          <BookOpen size={15}/> Complete metric formula reference <ArrowRight size={13}/></a>
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
    <section className="qg-panel qg-metric-guide">
      <div className="qg-head"><BookOpen size={18}/><h3>Metric Guide · Click a formula to understand it</h3></div>
      <p>Select any quantitative metric for its definition, formula, interpretation and limitations. The complete formula guide is downloadable above.</p>
      <div className="qg-metric-layout">
        <div className="qg-metric-list">{METRICS.map(item=><button type="button"
          key={item.name} className={selectedMetric===item.name?'active':''}
          onClick={()=>setSelectedMetric(item.name)}>{item.name}</button>)}</div>
        <article className="qg-metric-detail">{METRICS.filter(x=>x.name===selectedMetric).map(metric=>
          <div key={metric.name}><h4>{metric.name}</h4>
            <h5>Definition and formula</h5><code>{metric.formula}</code>
            <h5>Interpretation</h5><p>{metric.meaning}</p>
            <h5>Assumptions and failure modes</h5><p>{metric.caveat}</p>
            <button type="button" onClick={()=>onNavigate('mathematics')}>
              Open the related model catalog <ArrowRight size={14}/></button>
          </div>)}</article>
      </div>
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

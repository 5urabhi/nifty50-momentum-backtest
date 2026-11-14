import {useEffect,useRef,useState} from 'react'
import {ArrowRight,BookOpen,CheckCircle2,Database,FlaskConical,
  LoaderCircle,MessageCircle,Search,ShieldAlert,ShieldCheck} from 'lucide-react'
import {formatMetric} from './metricDisplay'
import './research-assistant.css'

type Kind='model_run'|'research_run'
type Target='brief'|'diagnostics'|'validation'|'evidence'|'compare'
type Fact={name:string;value:unknown;unit:string;detail:string;source:string}
type Ref={title:string;tab:Target;locator:string}
type Reply={
  kind:Kind;run_id:string;question:string;intent:string;title:string;
  answer:string;evidence_class:string;evidence_label:string;facts:Fact[];
  references:Ref[];next_actions:string[];limitations:string[];
  engine:string;warning:string
}
type Turn={id:number;question:string;reply:Reply}
type Props={run:{kind:Kind;id:string;title:string};onTab:(tab:Target)=>void;
  onData:()=>void;onModels:()=>void;onExperiments:()=>void}
const QUESTIONS=[
  'What does this result establish?',
  'Can I trust this result?',
  'What is the Sharpe ratio?',
  'What data is missing?',
  'Why did this strategy perform this way?',
  'What should I test next?',
  'How can I compare this with another run?',
  'Explain the model assumptions'
]
function detailFromError(value:unknown,status:number){
  if(value&&typeof value==='object'&&'detail' in value){
    const detail=(value as {detail:unknown}).detail
    if(typeof detail==='string')return detail
  }
  return 'Local research engine responded with HTTP '+status
}
export default function ResearchAssistant({run,onTab,onData,onModels,onExperiments}:Props){
  const [draft,setDraft]=useState('')
  const [level,setLevel]=useState<'beginner'|'researcher'|'mathematical'>('beginner')
  const [turns,setTurns]=useState<Turn[]>([])
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')
  const controller=useRef<AbortController|null>(null)
  const nextTurn=useRef(0)
  useEffect(()=>()=>{controller.current?.abort()},[])
  const ask=async(text:string)=>{
    const question=text.trim()
    if(question.length<2||question.length>400){
      setError('Ask a question between 2 and 400 characters.')
      return
    }
    controller.current?.abort()
    const request=new AbortController()
    controller.current=request
    setBusy(true);setError('')
    try{
      const response=await fetch('/api/workspace/results/'+run.kind+'/'+
        encodeURIComponent(run.id)+'/ask',{
        method:'POST',credentials:'same-origin',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({question,level}),signal:request.signal,
      })
      const data=await response.json() as Reply|{detail?:unknown}
      if(!response.ok)throw new Error(detailFromError(data,response.status))
      if(request.signal.aborted)return
      const reply=data as Reply
      if(reply.run_id!==run.id||reply.kind!==run.kind)throw new Error('Research context changed. Reopen this run.')
      nextTurn.current+=1
      setTurns(previous=>[...previous,{id:nextTurn.current,question,reply}].slice(-8))
      setDraft('')
    }catch(e){
      if(!request.signal.aborted)setError(e instanceof Error?e.message:String(e))
    }finally{
      if(controller.current===request){controller.current=null;setBusy(false)}
    }
  }
  return <section className="rqa-root rs-panel" aria-label="Research assistant">
    <div className="rqa-intro">
      <span className="rs-kicker"><MessageCircle size={14}/> RESEARCH ASSISTANT / ARCHIVED EVIDENCE</span>
      <h3>Ask what this research result actually means.</h3>
      <p>This assistant reads the selected run's saved Python calculations and evidence audit.
        It does not ask an external AI model, fetch broker data, alter datasets, or place orders.
        Answers are bounded by what the archive actually contains.</p>
      <div className="rqa-context"><ShieldCheck size={15}/>
        <span><strong>Current run:</strong> {run.title} <small>({run.kind} · {run.id})</small></span>
      </div>
    </div>
    <div className="rqa-prompts" aria-label="Suggested research questions">
      {QUESTIONS.map(q=><button type="button" key={q} onClick={()=>void ask(q)}
        disabled={busy}>{q}<ArrowRight size={12}/></button>)}
    </div>
    <form className="rqa-form" onSubmit={e=>{e.preventDefault();void ask(draft)}}>
      <label htmlFor="rqa-question">Ask about the selected saved run</label>
      <textarea id="rqa-question" value={draft} maxLength={400} rows={2}
        disabled={busy} placeholder="Example: Which evidence checks are blocking this result?"
        onChange={e=>setDraft(e.target.value)}/>
      <div className="rqa-form-bottom">
        <label>Explanation depth
          <select value={level} onChange={e=>setLevel(e.target.value as typeof level)}
            disabled={busy} aria-label="Assistant explanation depth">
            <option value="beginner">Beginner</option>
            <option value="researcher">Researcher</option>
            <option value="mathematical">Mathematical</option>
          </select>
        </label>
        <button className="rs-primary" type="submit" disabled={busy||draft.trim().length<2}>
          {busy?<LoaderCircle size={15} className="rqa-spin"/>:<Search size={15}/>}
          {busy?'Reading saved evidence…':'Ask QuantLab'}
        </button>
      </div>
    </form>
    {error&&<p className="rqa-error" role="alert"><ShieldAlert size={15}/>{error}</p>}
    {busy&&<p className="rqa-status" role="status"><LoaderCircle className="rqa-spin" size={15}/>
      Checking actual saved outputs and evidence gates…</p>}
    <div className="rqa-history" aria-live="polite" aria-relevant="additions">
      {turns.length===0&&<div className="rqa-empty">
        <BookOpen size={24}/><p>Choose a question or type your own.
          If a number is not archived, QuantLab will say so.</p></div>}
      {turns.map(turn=><article className="rqa-turn" key={turn.id}>
        <div className="rqa-question"><MessageCircle size={14}/>{turn.question}</div>
        <div className="rqa-answer">
          <div className="rqa-answer-header"><h4>{turn.reply.title}</h4>
            <span className={turn.reply.evidence_class==='synthetic_demo'?'rqa-class-demo':'rqa-class'}>
              {turn.reply.evidence_label}</span></div>
          <p>{turn.reply.answer}</p>
          {turn.reply.facts.length>0&&<div className="rqa-facts" aria-label="Exactly saved numerical facts">
            {turn.reply.facts.map((fact,i)=>{
              const formatted=formatMetric(fact.name,fact.value,fact.unit)
              return <div className="rqa-fact" key={fact.name+'-'+i}>
                <small>{fact.name}</small><strong>{formatted.value}</strong>
                <span>{formatted.unit}</span>
                {fact.detail&&<p>{fact.detail}</p>}
              </div>
            })}</div>}
          {turn.reply.next_actions.length>0&&<section className="rqa-next">
            <h5>Actionable next steps</h5>
            {turn.reply.next_actions.map((action,i)=><p key={i}>
              <CheckCircle2 size={13}/>{action}</p>)}
          </section>}
          {turn.reply.limitations.length>0&&<section className="rqa-limits">
            <h5>Interpretation limits</h5>
            {turn.reply.limitations.map((item,i)=><p key={i}><ShieldAlert size={13}/>{item}</p>)}
          </section>}
          <section className="rqa-references"><h5>Inspect the actual evidence</h5>
            <div>{turn.reply.references.map((ref,i)=><button type="button"
              key={ref.locator+'-'+i} title={ref.locator}
              onClick={()=>onTab(ref.tab)}>
              <BookOpen size={13}/>{ref.title}<ArrowRight size={12}/>
            </button>)}</div>
            <small>Source: {run.kind}/{run.id}. These citations are links to saved results,
              not external verification.</small>
          </section>
        </div>
      </article>)}
    </div>
    <div className="rqa-footer">
      <button type="button" onClick={onModels}><FlaskConical size={13}/> Model Laboratory</button>
      <button type="button" onClick={onExperiments}><FlaskConical size={13}/> New experiment</button>
      <button type="button" onClick={onData}><Database size={13}/> Resolve source inputs</button>
      <small>Research-only, local, deterministic. No generative market claims.</small>
    </div>
  </section>
}

/** Consistent, evidence-safe units across QuantLab result surfaces.
 * Only convert explicitly declared fractional return metrics; never infer a
 * monetary currency or change a model's physical parameters by guessing.
 */
export type MetricDisplay={value:string;unit:string}
const number=(v:number,digits=4)=>v.toLocaleString('en-US',{maximumFractionDigits:digits})
const FRACTIONAL_PERFORMANCE=/(?:^|\b)(return|cagr|drawdown|volatility|tracking error|turnover|hit rate|beat rate|exposure|portfolio weight|active weight|allocation|annualized alpha)(?:\b|$)/i
const FRACTIONAL_RISK=/(?:\bvar\b|value at risk|expected shortfall|tail loss|factor weight|down.month.rate|down.month.fraction|probability|selection frequency)/i
const CURRENCY:Record<string,{symbol:string;label:string}>={
  inr:{symbol:'₹',label:'INR'},usd:{symbol:'$',label:'USD'},eur:{symbol:'€',label:'EUR'},
  gbp:{symbol:'£',label:'GBP'}
}
export function formatMetric(name:string,value:unknown,declaredUnit?:string|null):MetricDisplay{
  const rawUnit=(declaredUnit||'').trim()
  if(value===null||value===undefined||value===''||
     typeof value==='number'&&!Number.isFinite(value))
    return {value:'Unavailable',unit:rawUnit||'Not reported'}
  const val=typeof value==='number'?value:typeof value==='string'&&value.trim()!==''&&Number.isFinite(Number(value))?Number(value):null
  if(val===null)return {value:String(value),unit:rawUnit||'As reported'}
  const unit=rawUnit.toLowerCase().replaceAll(' ','')
  // Currency cannot be deduced from an exchange listing or an asset symbol.
  const currency=CURRENCY[unit]||CURRENCY[unit.replace(/^(currency:|currency)/,'')]
  if(currency)return {value:currency.symbol+number(val,2),unit:currency.label}
  if(unit==='bps'||unit==='bp'||unit==='basispoints')
    return {value:number(val,2),unit:'bps'}
  if(['decimalfraction','fractionperyear','fraction','decimalloss'].includes(unit)&&
      (FRACTIONAL_PERFORMANCE.test(name)||FRACTIONAL_RISK.test(name))){
    const horizon=unit==='fractionperyear'?'Percent per year · from saved fraction':
      unit==='decimalloss'?'Percent loss · saved horizon':'Percent · from saved fraction'
    return {value:number(val*100,2)+'%',unit:horizon}
  }
  if(unit==='decimalfraction'||unit==='fraction'||unit==='fractionperyear')
    return {value:number(val,6),unit:rawUnit||'Decimal fraction'}
  if(unit==='%'||unit==='percent'||unit==='percentage')
    return {value:number(val,2)+'%',unit:'Percent · as reported'}
  if(unit==='ratio'||/sharpe|sortino|information ratio|calmar/i.test(name))
    return {value:number(val,3),unit:rawUnit||'Ratio (unitless)'}
  if(unit==='count'||unit==='observations'||unit==='samples')
    return {value:number(val,0),unit:rawUnit||'Count'}
  return {value:number(val),unit:rawUnit||'Reported value · units unspecified'}
}

#!/usr/bin/env node
/**
 * Local-only 3-minute QuantLab demo video from a synthetic, source-labeled UI.
 * Requires a running localhost Vite + FastAPI pair and Playwright Chromium.
 * Saves WEBM with no narration. The recording is NOT a real NIFTY backtest.
 */
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import path from 'node:path'
import {chromium} from 'playwright'

const args=process.argv.slice(2)
const setting=(key, defaultValue)=>{
  const offset=args.indexOf(key)
  return offset===-1?defaultValue:args[offset+1]
}
const base=setting('--url','http://127.0.0.1:5173')
const out=path.resolve(setting('--output','artifacts/research-demo'))
const duration=Number(setting('--seconds','180'))
assert.ok(/^http:\/\/(127\.0\.0\.1|localhost):\d+$/.test(base),
  'Demo recorder is restricted to a local Vite server on loopback')
assert.ok(Number.isFinite(duration)&&duration>=100&&duration<=240,
  'Choose a demo length from 100 to 240 seconds')
await fs.mkdir(out,{recursive:true})
const basename='quantlab-synthetic-research-tour'
const target=path.join(out,basename+'.webm')
try { await fs.access(target); throw new Error('Demo already exists; choose a new output folder') }
catch (e) { if(e?.code!=='ENOENT') throw e }
const shots= [
  {section:'Home',seconds:19,caption:'Research workstation · synthetic demonstration'},
  {section:'Data Library',seconds:18,caption:'Data provenance and saved research sources'},
  {section:'Model Laboratory',seconds:22,caption:'Financial mathematics and model configuration'},
  {section:'Experiment Studio',seconds:22,caption:'Chronological experiments and validation assumptions'},
  {section:'Compare & Visualize',seconds:25,caption:'Interactive 2D / 3D visual research'},
  {section:'Compare & Visualize',tab:'Index Research Studio',seconds:29,
   caption:'Index methodology, benchmark-relative risk and source requirements'},
  {section:'Research Projects',seconds:20,caption:'Reproducible notebooks, reporting and experiments'},
  {section:'Compare & Visualize',tab:'Index Research Studio',subtab:'Data Passports',
   seconds:25,caption:'No independent certification without original source review'}
]
const total=shots.reduce((sum,x)=>sum+x.seconds,0)
let browser
let context
let video
const started=new Date().toISOString()
try {
  browser=await chromium.launch({headless:true,args:['--no-sandbox','--disable-dev-shm-usage']})
  context=await browser.newContext({
    viewport:{width:1440,height:900},deviceScaleFactor:1,
    recordVideo:{dir:out,size:{width:1440,height:900}},
    colorScheme:'dark'
  })
  const page=await context.newPage()
  video=page.video()
  page.setDefaultTimeout(20000)
  const response=await page.request.get(base.replace(':5173',':8765')+'/api/health')
  assert.equal(response.status(),200,'Local FastAPI must be online')
  const health=await response.json()
  assert.equal(health.broker_orders_enabled,false,'Trading order execution must be disabled')
  // Create only the deterministic local fixture; do not call Dhan or use a
  // user's real datasets, accounts, credentials, or market-data API.
  const synthetic=await page.request.post(
    base.replace(':5173',':8765')+'/api/datasets/synthetic')
  assert.equal(synthetic.status(),200,'Synthetic fixture must be available')
  await page.goto(base,{waitUntil:'domcontentloaded'})
  await page.getByText('ENGINE ONLINE',{exact:true}).waitFor({timeout:30000})
  await page.evaluate(()=>{
    const div=document.createElement('div')
    div.id='quantlab-demo-evidence-notice'
    div.textContent='SYNTHETIC SOFTWARE DEMO · NOT INDEPENDENTLY AUDITED'
    Object.assign(div.style,{
      position:'fixed',bottom:'16px',right:'16px',padding:'10px 16px',
      background:'#612e28',color:'#ffffff',borderRadius:'12px',
      fontFamily:'system-ui',fontWeight:'700',letterSpacing:'.035em',
      zIndex:'2147483647',pointerEvents:'none',
      boxShadow:'0 4px 18px rgba(0,0,0,.45)'
    })
    document.body.appendChild(div)
  })
  for (const scene of shots) {
    const nav=page.locator('.ws-sidebar nav').getByRole('button',{
      name:scene.section,exact:true
    })
    await nav.click()
    if (scene.tab) {
      await page.locator('.rw-navigation').getByRole('tab',{
        name:new RegExp('^'+scene.tab)
      }).click()
    }
    if (scene.subtab) {
      await page.getByRole('button',{name:scene.subtab,exact:true}).click()
    }
    // Force the only demonstrated research dataset to be synthetic.
    const picker=page.getByLabel('Observed / demonstration dataset')
    if (await picker.count()) await picker.selectOption('synthetic')
    await page.evaluate((caption)=>{
      let note=document.getElementById('quantlab-demo-scene')
      if(!note){
        note=document.createElement('div')
        note.id='quantlab-demo-scene'
        Object.assign(note.style,{
          position:'fixed',top:'22px',right:'20px',padding:'12px 18px',
          background:'#12263e',border:'1px solid #4d8e94',
          color:'#d8f7f2',borderRadius:'10px',font:'600 16px system-ui',
          maxWidth:'450px',zIndex:'2147483645',pointerEvents:'none'
        })
        document.body.appendChild(note)
      }
      note.textContent=caption
    },scene.caption)
    // Bounded tour: no implicit model/trading jobs or publication approval.
    await new Promise(resolve=>setTimeout(resolve,scene.seconds/total*duration*1000))
  }
  await context.close()
  await fs.rename(await video.path(),target)
  const manifest={
    kind:'synthetic_bounded_local_demo',recorded_at_utc:started,
    duration_requested_seconds:duration,
    source:'deterministic synthetic fixture, not NSE/Dhan licensed history',
    independently_audited:false,broker_orders:false,
    file:path.basename(target),audio:false,
    scenes:shots.map(x=>({section:x.section,tab:x.tab||null,caption:x.caption}))
  }
  await fs.writeFile(path.join(out,basename+'.json'),JSON.stringify(manifest,null,2)+'\n')
  console.log('Saved synthetic evidence-labeled demo:',target)
} finally {
  if(context){try{await context.close()}catch{}}
  if(browser){try{await browser.close()}catch{}}
}

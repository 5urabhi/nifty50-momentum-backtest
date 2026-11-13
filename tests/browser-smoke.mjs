/**
 * Ubuntu Chromium acceptance: real browser -> Vite proxy -> FastAPI -> local
 * deterministic CI fixture -> rendered numerical response.
 *
 * This is not a Dhan live-credential test or investment-data certification.
 * Run via .github/workflows/workstation-browser-smoke.yml.
 */
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import path from 'node:path'
import { chromium } from 'playwright'

const artifactDir = path.resolve(process.env.QUANTLAB_SMOKE_ARTIFACT_DIR || 'artifacts/browser-smoke')
await fs.mkdir(artifactDir, { recursive: true })
const base = process.env.QUANTLAB_SMOKE_URL || 'http://127.0.0.1:5173'
const steps = []
const errors = []
const api500 = []
let browser
let page

function record(name, status, detail = '') {
  steps.push({ name, status, detail, at: new Date().toISOString() })
  console.log('[browser-smoke] ' + status + ': ' + name + (detail ? ' (' + detail + ')' : ''))
}
async function step(name, fn) {
  const started = Date.now()
  try {
    await fn()
    record(name, 'PASS', Date.now() - started + ' ms')
  } catch (e) {
    record(name, 'FAIL', String(e))
    if (page) {
      try {
        await page.screenshot({path: path.join(artifactDir, 'failed-' +
            name.toLowerCase().replace(/[^a-z0-9]+/g, '-').slice(0,55)+'.png'),fullPage:true})
      } catch {}
    }
    throw e
  }
}
function nav(name) {
  return page.locator('.ws-sidebar nav').getByRole('button', {name, exact:true})
}
function researchTab(name) {
  return page.locator('.rw-navigation').getByRole('tab', {name: new RegExp('^'+name)})
}
async function apiJson(endpoint) {
  const response = await page.request.get(base + endpoint)
  assert.equal(response.status(), 200, endpoint + ': ' + (await response.text()).slice(0,400))
  return response.json()
}
async function waitJobComplete(jobId) {
  for (let attempt=0; attempt<75; attempt++) {
    const data = await apiJson('/api/workspace/jobs')
    const job = data.jobs.find(x => x.id === jobId)
    if (job?.status === 'complete') return job
    if (job?.status === 'error' || job?.status === 'cancelled')
      throw new Error('Report job did not succeed: ' + JSON.stringify(job))
    await new Promise(resolve=>setTimeout(resolve,500))
  }
  throw new Error('Timed out waiting for actual report job ' + jobId)
}
async function screenshot(name) {
  await page.screenshot({path:path.join(artifactDir,name+'.png'),fullPage:true})
}
try {
  browser = await chromium.launch({headless:true,args:['--no-sandbox','--disable-dev-shm-usage']})
  const context = await browser.newContext({
    viewport: {width: 1440, height: 900}, deviceScaleFactor: 1,
    acceptDownloads:true, locale:'en-US', colorScheme:'dark'
  })
  page = await context.newPage()
  page.setDefaultTimeout(18000)
  page.on('pageerror', e => errors.push(String(e)))
  page.on('response', r=>{
    try {
      if (new URL(r.url()).pathname.startsWith('/api/') && r.status() >= 500)
        api500.push(r.status()+' '+r.request().method()+' '+new URL(r.url()).pathname)
    } catch {}
  })
  await step('backend and eight-destination shell', async()=>{
    const health=await apiJson('/api/health')
    assert.equal(health.broker_orders_enabled,false,'Broker execution must be off')
    assert.equal(health.dhan_token_configured,false,'CI fixture must have no broker token')
    await page.goto(base,{waitUntil:'domcontentloaded'})
    await page.getByText('ENGINE ONLINE',{exact:true}).waitFor({timeout:25000})
    const buttons = page.locator('aside .ws-nav-item')
    assert.equal(await buttons.count(),8,'Exactly eight main destinations')
    await screenshot('01-home-desktop')
  })
  await step('all research destination views and nested navigation',async()=>{
    for (const section of ['Home','Data Library','Model Laboratory','Experiment Studio',
      'Compare & Visualize','Results Studio','Research Projects','Help & Settings']) {
      await nav(section).click()
      const header=page.locator('.ws-titlebar h1')
      assert.ok((await header.innerText()).length>2,'Destination must have a visible title: '+section)
    }
    await nav('Compare & Visualize').click()
    await page.locator('.rw-top h2').waitFor()
    assert.equal(await researchTab('Plot Builder').count(),1)
  })
  await step('Results Studio source-classified evidence audit and export',async()=>{
    await nav('Results Studio').click()
    await page.locator('.rs-identity h3').waitFor()
    await page.locator('.rs-tabs').getByRole('button',{name:'Evidence audit'}).click()
    await page.getByRole('heading',{name:'Research Evidence Audit'}).waitFor()
    await page.locator('.rs-check-gates .rs-gate').first().waitFor({timeout:20000})
    const saved=await apiJson('/api/lab/runs?limit=30')
    const audit=await apiJson('/api/workspace/results/model_run/'+saved.runs[0].id+'/evidence')
    assert.equal(audit.evidence_class,'synthetic_demo','GBM is synthetic, not historical')
    assert.equal(audit.readiness,'research_diagnostic_only')
    assert.ok(audit.checks.some(check=>check.status==='blocked'))
    assert.ok(await page.getByRole('button',{name:'Evidence JSON'}).isEnabled())
    await screenshot('02-results-evidence-audit')
  })
  await step('Dhan download uses an accessible four-step guided flow',async()=>{
    await nav('Data Library').click()
    await page.locator('.ws-context-tabs').getByRole('button',{
      name:'Download market data'
    }).click()
    await page.getByRole('heading',{name:'Download data for your research'}).waitFor()
    await page.getByRole('heading',{name:'1. What data do you want?'}).waitFor()
    await page.getByRole('heading',{name:'2. Choose dates and data type'}).waitFor()
    await page.getByRole('heading',{name:'3. Download'}).waitFor()
    await page.getByRole('heading',{name:'Download progress & prepare data'}).waitFor()
    const steps=await page.locator('.dh-simple-track span').allTextContents()
    assert.deepEqual(steps,['1 · Choose data','2 · Dates','3 · Download','4 · Prepare'])
    const indexOption=page.getByRole('button',{name:/NIFTY 50 · Historical/})
    assert.equal(await indexOption.getAttribute('aria-pressed'),'true')
    const frequency=page.getByRole('combobox',{name:'Download frequency'})
    assert.equal(await frequency.inputValue(),'daily')
    assert.equal(await page.locator('.dh-membership-details').evaluate(el=>el.open),false)
    assert.equal(await page.locator('.dh-advanced-data').evaluate(el=>el.open),false)
    const download=page.getByRole('button',{name:/Start download/})
    assert.equal(await download.isDisabled(),true,'No Dhan token in isolated CI')
    await page.getByText(/Dhan token not found/).waitFor()
    await page.locator('.dh-advanced-data summary').click()
    await page.getByText(/NOT dividend-reinvested TRI/).waitFor()
    await page.locator('.dh-advanced-data summary').click()
    await page.getByRole('button',{name:/BANK NIFTY · Historical/}).click()
    assert.equal(await page.getByRole('button',{name:/BANK NIFTY · Historical/})
      .getAttribute('aria-pressed'),'true')
    await page.getByRole('button',{name:/NIFTY 50 · Historical/}).click()
    await screenshot('02-dhan-four-step-download')
    await nav('Compare & Visualize').click()
    await page.locator('.rw-top h2').waitFor()
  })
  await step('Data Manager exposes source completion and recoverable dataset management',async()=>{
    await nav('Data Library').click()
    await page.locator('.ws-context-tabs').getByRole('button',{name:'Data manager'}).click()
    await page.getByRole('heading',{name:'Saved datasets · manage & delete'}).waitFor()
    const imported=page.getByRole('button',{name:/Delete dataset/})
    assert.ok(await imported.count()>0,'User-owned datasets need a visible delete action')
    await page.locator('.ws-dataset-trash summary').waitFor()
    await page.locator('.ws-dataset-trash summary').click()
    await page.locator('.ws-dataset-trash').evaluate(el=>el.open===true)
    await nav('Model Laboratory').click()
    await page.locator('.ql-family-tabs').getByRole('button',{name:/Stochastic Processes/}).click()
    await page.getByText('SIMULATED EXAMPLE — NOT LIVE OR HISTORICAL MARKET DATA').waitFor()
    await nav('Compare & Visualize').click()
    await page.locator('.rw-top h2').waitFor()
  })
  await step('Dhan error is visible, safe and the batch arrow opens failed stock details',async()=>{
    // A simulated Dhan refusal only: no token, no real vendor request, no raw
    // response body. The browser must surface the failing symbol/status
    // independently from pagination and make the batch arrow functional.
    const fakeId='batch_baaaaaaaaaaaaaaa'
    const summary={
      id:fakeId,status:'paused',selection:'banknifty_pit',interval:1,
      created_utc:'2026-11-13T00:00:00Z',from_date:'2025-11-13',to_date:'2026-10-12',
      total:14,processed:1,current_symbol:'AUBANK',errors:1,warning:'',
      counts:{pending:13,downloading:0,complete:0,cached:0,no_data:0,failed:1},
      failure_examples:[{
        symbol:'AUBANK',code:'HTTP 401',
        diagnostic:'Dhan HTTP 401 (vendor response body hidden)',
        explanation:'Dhan rejected this historical candle request. Verify your token and Data API subscription; the exact cause is not yet confirmed.',
      }],
    }
    const batchRoutes=/\/api\/dhan\/batches(?:\/[^?]*)?(?:\?.*)?$/
    await page.route(batchRoutes,async route=>{
      const request=route.request()
      if(request.method()!=='GET')return route.continue()
      const url=new URL(request.url())
      if(url.pathname.endsWith('/batches')){
        return route.fulfill({status:200,contentType:'application/json',
          body:JSON.stringify({batches:[summary]})})
      }
      if(url.pathname.endsWith('/'+fakeId)){
        const failed={
          id:'NSE_EQ:999',symbol:'AUBANK',display_name:'AU Small Finance Bank',
          security_id:'999',exchange_segment:'NSE_EQ',instrument:'EQUITY',
          series:'EQ',isin:'',regular_eq:true,status:'failed',rows:0,rows_added:0,
          error:'Dhan HTTP 401 (vendor response body hidden)',
        }
        const filter=url.searchParams.get('status')||'all'
        const items=filter==='all'||filter==='failed'?[failed]:[]
        return route.fulfill({status:200,contentType:'application/json',
          body:JSON.stringify({...summary,items,page:1,per_page:40,filtered_total:items.length})})
      }
      return route.continue()
    })
    await nav('Data Library').click()
    await page.locator('.ws-context-tabs').getByRole('button',{
      name:'Download market data',
    }).click()
    const errorCard=page.getByRole('alert',{name:'Download error details'})
    await errorCard.getByText('AUBANK',{exact:true}).waitFor()
    await errorCard.getByText('HTTP 401',{exact:true}).waitFor()
    await errorCard.getByText(/Dhan HTTP 401/).waitFor()
    await errorCard.getByRole('button',{name:'Copy error details'}).waitFor()
    await errorCard.getByRole('button',{name:'Verify token and Data API subscription'}).waitFor()
    assert.ok(!(await errorCard.innerText()).includes('SECRET_API_TOKEN'))
    // Past downloads is intentionally an optional disclosure in the guided
    // UI. Open it before testing the batch-row View errors action.
    const past=page.locator('.dh-previous-downloads')
    if(!(await past.evaluate(el=>el.open)))await past.locator('summary').click()
    const row=page.getByRole('button',{
      name:'View BANK NIFTY · Historical members download details and errors',
    })
    await row.click()
    await page.waitForFunction(()=>document.querySelector('#dh-batch-diagnostics')?.open===true)
    const selected=page.getByRole('combobox',{name:'Filter download result status'})
    assert.equal(await selected.inputValue(),'failed')
    await page.getByRole('cell',{name:'AUBANK'}).waitFor()
    await screenshot('02b-dhan-visible-error-and-batch-arrow')
    await page.unroute(batchRoutes)
    await nav('Compare & Visualize').click()
    await page.locator('.rw-top h2').waitFor()
  })
  await step('observed-column plot builder: browser to API to mathematical chart',async()=>{
    await researchTab('Plot Builder').click()
    await page.getByLabel('Observed market dataset').selectOption('upload_ci_browser_smoke')
    await page.getByLabel('Graph type').selectOption('scatter')
    await page.getByRole('button',{name:'Plot selected observations'}).click()
    await page.locator('.ra-result svg').first().waitFor()
    assert.match(await page.locator('.ra-result').innerText(),/SHA-256/i)
    const graph=page.locator('.ra-result .ql-svg-chart').first()
    await graph.hover({position:{x:320,y:140}})
    await page.locator('.ra-result .ql-active-observation').first().waitFor()
    assert.ok((await page.locator('.ra-result .ql-active-observation').textContent()).length>3,
      'Hover must expose actual data values, not a non-interactive line')
    await screenshot('02-plot-scatter')
    const figure=await apiJson('/api/workspace/plot-builder/columns/upload_ci_browser_smoke')
    assert.equal(figure.total_columns,4)
    assert.ok(figure.total_dates>400,'Fixture must expose real aligned rows to the API')
  })
  await step('chart save, report attachment and standalone HTML export',async()=>{
    await page.getByRole('button',{name:'Save chart',exact:true}).click()
    await page.getByLabel('Add saved chart to report notebook').selectOption({label:'CI smoke notebook'})
    await page.getByRole('button',{name:'Add to report',exact:true}).click()
    await page.getByText('Saved graph added directly to your report notebook.').waitFor()
    const downloadPromise=page.waitForEvent('download')
    await page.getByRole('button',{name:/Interactive HTML/}).click()
    const download=await downloadPromise
    const filename=path.join(artifactDir,'03-exported-plot.html')
    await download.saveAs(filename)
    const html=await fs.readFile(filename,'utf8')
    assert.ok(html.includes('<svg')&&html.includes('pointerdown'),
      '2D exported HTML must contain graph and interactive pan handler')
    await page.getByLabel('Graph type').selectOption('correlation')
    await page.getByRole('button',{name:'Plot selected observations'}).click()
    await page.locator('.ra-result svg').first().waitFor()
    assert.match(await page.locator('.ra-result').innerText(),/source/i)
    await screenshot('04-heatmap')
  })
  await step('statistical tests on backend numeric return observations',async()=>{
    await page.getByRole('button',{name:/Statistics & Diagnostics/}).click()
    await page.getByRole('button',{name:'Calculate actual statistical evidence'}).click()
    await page.getByRole('heading',{name:/Observed diagnostics/}).waitFor()
    assert.ok((await page.locator('.rw-stats').first().innerText()).includes('jarque'))
    await screenshot('05-statistical-diagnostics')
  })
  await step('evidence gate remains unverified and trained ML completes its real holdout',async()=>{
    await researchTab('Evidence & ML').click()
    await page.getByRole('heading',{name:'Research-data evidence register'}).waitFor()
    await page.getByText('Historical investability certified',{exact:true}).waitFor()
    const evidence=await apiJson('/api/workspace/integrity/upload_ci_browser_smoke')
    assert.equal(evidence.historical_investability_certified,false)
    assert.equal(evidence.prospective_trading_certified,false)
    await page.getByRole('button',{name:'Live Dhan Check'}).click()
    await page.getByText(/Choose a prepared DAILY Dhan dataset/).waitFor()
    // No real credential, no vendor API calls, and no data mutation.
    await page.getByRole('button',{name:'ML / RL Holdout'}).click()
    await page.getByText('Preferred (+20%)').waitFor()
    await page.getByText('Minimum training+holdout requirement satisfied').waitFor()
    page.once('dialog',dialog=>dialog.accept())
    const pendingResponse=page.waitForResponse(r=>
      new URL(r.url()).pathname==='/api/workspace/learning/run'&&
      r.request().method()==='POST')
    await page.getByRole('button',{name:/Confirm & run chronological research/}).click()
    const started=await pendingResponse
    assert.equal(started.status(),200,await started.text())
    const submitted=await started.json()
    assert.ok(submitted.job_id)
    const finished=await waitJobComplete(submitted.job_id)
    assert.equal(finished.result.method,'ridge')
    assert.ok(finished.result.last_training_label_date <
      finished.result.first_test_decision_date,'No test future labels in training')
    const csv=await page.request.get(base+'/api/workspace/studies/'+finished.result.study_id+
      '/returns.csv')
    assert.equal(csv.status(),200,'Full chronological holdout CSV downloaded')
    assert.ok((await csv.text()).split('\n').length>40)
    await screenshot('06-learning-evidence')
  })
  await step('researcher index studio passports, data-safe preflight and model explanations',async()=>{
    await researchTab('Index Research Studio').click()
    await page.getByRole('heading',{name:'Research source — one canonical dataset'}).waitFor()
    await page.getByRole('button',{name:'Data Passports'}).click()
    await page.getByRole('heading',{name:/Research Data Passport/}).waitFor()
    const passport=await apiJson('/api/workspace/passports/upload_ci_browser_smoke')
    assert.equal(passport.investability_certified,false)
    assert.ok(passport.available_files.some(x=>x.name==='prices.csv'))
    await screenshot('11-source-data-passport')
    await page.getByRole('button',{name:'Inspect actual missing observations'}).click()
    await page.getByRole('heading',{name:/Observed coverage audit/}).waitFor()
    const sourceGaps=await apiJson('/api/workspace/source-coverage/upload_ci_browser_smoke')
    assert.equal(sourceGaps.historical_investability_certified,false)
    assert.ok(sourceGaps.price_observations>=2)
    assert.ok(Array.isArray(sourceGaps.warnings))
    await screenshot('11b-historical-coverage-gaps')
    await page.getByRole('button',{name:'Index Studio',exact:true}).click()
    await page.getByRole('button',{name:'Check assumptions & data'}).click()
    await page.getByText(/Infeasible observed universe/).waitFor()
    assert.equal(await page.getByRole('button',{name:'Confirm & run methodology'}).isDisabled(),true)
    await page.getByRole('button',{name:'Why This Result?'}).click()
    const saved=await apiJson('/api/lab/runs?limit=30')
    assert.ok(saved.runs.length>=2)
    await page.getByLabel('Saved calculation').selectOption(saved.runs[0].id)
    await page.getByRole('button',{name:'Understand this calculated result'}).click()
    await page.locator('.rs-explanation').waitFor()
    assert.match(await page.locator('.rs-explanation').innerText(),/Mathematical relation/)
    await screenshot('12-archived-research-explainer')
  })
  await step('research hypothesis registration is pinned and inspectable',async()=>{
    await page.getByRole('button',{name:'Publication & Protocol'}).click()
    await page.getByLabel('Research question').fill(
      'Can this preregistered multi-factor experiment beat its earlier-defined benchmark?')
    await page.getByLabel('Rationale').fill(
      'A factor combination may be more diversified than either univariate score.')
    await page.getByLabel('Frozen data, split, methodology and limitations').fill(
      'Use 70/15/15 chronological splits, fixed objective parameters and a wholly untouched final test.')
    await page.getByRole('button',{name:'Register frozen hypothesis'}).click()
    await page.getByText(/Hypothesis recorded with an append-only checksum/).waitFor()
    const h=await apiJson('/api/workspace/hypotheses')
    assert.equal(h.hypotheses[0].content_unchanged,true)
    assert.equal(h.hypotheses[0].dataset_id,'upload_ci_browser_smoke')
    await screenshot('13-registered-research-protocol')
  })
  await step('guided research and two-parameter grid preflight',async()=>{
    await researchTab('Guided & Grids').click()
    await page.getByRole('heading',{name:/Guided Research/}).waitFor()
    await page.getByRole('button',{name:/Multi-parameter grids/}).click()
    await page.getByRole('button',{name:/Validate complete experiment grid/}).click()
    await page.getByText(/3 model executions/).waitFor()
    await screenshot('06-parameter-grid')
  })
  await step('research notebook generates actual PDF HTML and Markdown files',async()=>{
    await researchTab('Projects & Notes').click()
    await page.getByRole('button',{name:/CI smoke notebook/}).first().click()
    const generate=page.getByRole('button',{name:/Generate PDF, HTML & Markdown report/})
    await generate.waitFor()
    assert.equal(await generate.isDisabled(),false,'Clean seeded notebook should allow report')
    const responsePromise=page.waitForResponse(r=>r.url().includes('/api/workspace/reports')&&r.request().method()==='POST')
    await generate.click()
    const response=await responsePromise
    assert.equal(response.status(),200,'Actual report generation must queue successfully')
    const queued=await response.json()
    assert.ok(queued.job_id,'Report must be associated with a real job ID')
    await waitJobComplete(queued.job_id)
    const records=await apiJson('/api/workspace/records?kind=report')
    assert.ok(records.records.length>0,'Report metadata must persist')
    const report=records.records[0]
    for(const [kind,expected] of [['html','<html'],['markdown','#'],['pdf','%PDF']]) {
      const file=await page.request.get(base+'/api/workspace/reports/'+report.id+'/'+kind)
      assert.equal(file.status(),200,'Report export '+kind)
      const raw=await file.body()
      assert.ok(raw.length>100,'Report '+kind+' must contain actual output')
      assert.ok(raw.toString('utf8',0,Math.min(raw.length,1000)).toLowerCase()
        .includes(expected.toLowerCase()),'Invalid '+kind+' report content')
    }
    await screenshot('07-notebook-report')
  })
  await step('model comparison and library resource listings render',async()=>{
    await researchTab('Compare & Graph').click()
    assert.ok(await page.locator('.rw-run-list label').count() >= 2,
      'Two seeded model runs must be visible')
    const toggles=page.locator('.rw-run-list input[type=checkbox]')
    await toggles.nth(0).check()
    await toggles.nth(1).check()
    await screenshot('08-saved-model-comparison')
    await researchTab('Library').click()
    await page.getByText('Datasets & results').first().waitFor()
  })
  await step('global command palette and formula reference',async()=>{
    await page.keyboard.press('Control+k')
    const dialog=page.getByRole('dialog',{name:'Search QuantLab research library'})
    await dialog.waitFor()
    await dialog.getByPlaceholder(/Find datasets/).fill('Heston')
    await dialog.getByText('Heston').first().waitFor()
    await page.keyboard.press('Escape')
    await nav('Help & Settings').click()
    await page.getByRole('button',{name:'Expected Shortfall (ES / CVaR)'}).waitFor()
    await page.getByRole('button',{name:'Value at Risk (VaR)'}).click()
    assert.match(await page.locator('.qg-metric-detail').innerText(),/quantile_alpha/)
    await screenshot('09-metric-reference')
  })
  await step('mobile viewport and navigation remain usable',async()=>{
    await page.setViewportSize({width:390,height:844})
    await page.getByRole('button',{name:'Open navigation'}).click()
    await nav('Compare & Visualize').click()
    await page.locator('.rw-top h2').waitFor()
    await screenshot('10-mobile-workspace')
  })
  await step('no unhandled browser exceptions or HTTP 5xx',async()=>{
    assert.deepEqual(errors,[],'Browser page errors')
    assert.deepEqual(api500,[],'Backend 5xx responses')
  })
} catch(e) {
  console.error('[browser-smoke] FAIL:',e)
  process.exitCode=1
} finally {
  await fs.writeFile(path.join(artifactDir,'summary.json'),JSON.stringify({
    success:process.exitCode!==1,
    steps,jsErrors:errors,api5xx:api500,scope:'isolated synthetic CI fixture; no broker credentials/orders',
  },null,2)+'\n')
  if(browser)await browser.close()
}

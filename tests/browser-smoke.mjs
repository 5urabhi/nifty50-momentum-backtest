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
      'Compare & Visualize','Results Library','Research Projects','Help & Settings']) {
      await nav(section).click()
      const header=page.locator('.ws-titlebar h1')
      assert.ok((await header.innerText()).length>2,'Destination must have a visible title: '+section)
    }
    await nav('Compare & Visualize').click()
    await page.locator('.rw-top h2').waitFor()
    assert.equal(await researchTab('Plot Builder').count(),1)
  })
  await step('observed-column plot builder: browser to API to mathematical chart',async()=>{
    await researchTab('Plot Builder').click()
    await page.getByLabel('Observed market dataset').selectOption('upload_ci_browser_smoke')
    await page.getByLabel('Graph type').selectOption('scatter')
    await page.getByRole('button',{name:'Plot selected observations'}).click()
    await page.locator('.ra-result svg').first().waitFor()
    assert.match(await page.locator('.ra-result').innerText(),/SHA-256/i)
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

import { chromium } from 'playwright'
import { randomBytes } from 'node:crypto'
import fs from 'node:fs'
import { fileURLToPath } from 'node:url'
process.chdir(fileURLToPath(new URL('../../', import.meta.url)))
fs.mkdirSync('output/ui-review', { recursive: true })
const browser = await chromium.launch({ headless: true, channel: process.env.PLAYWRIGHT_CHANNEL || 'msedge' })
try {
const page = await browser.newPage({ viewport: {width:1440,height:1000} })
const errors=[]
page.on('pageerror',e=>errors.push(e.message))
const email=`qa-${Date.now()}@example.com`, password=randomBytes(24).toString('hex')
await page.goto('http://127.0.0.1:5173/register', {waitUntil:'domcontentloaded'})
await page.getByLabel('Full name').fill('QA Workspace Reviewer')
await page.getByLabel('Workspace name').fill('QA verification workspace')
await page.getByLabel('Email address').fill(email)
await page.getByLabel('Password',{exact:true}).fill(password)
await page.getByRole('button',{name:'Create account',exact:true}).click()
await page.waitForURL('**/app')
await page.getByRole('heading',{name:'Your client workspace'}).waitFor()
await page.getByRole('link',{name:'New analysis',exact:true}).first().click()
await page.getByLabel('Choose financial workbook').setInputFiles('client_data.xlsx')
await page.getByRole('button',{name:'Preview workbook'}).click()
await page.getByRole('checkbox').check()
await page.getByRole('button',{name:'Confirm and start analysis'}).click()
await page.waitForURL('**/app/processing/*')
const aid=page.url().split('/').at(-1)
await page.reload({waitUntil:'domcontentloaded'})
await page.waitForURL('**/app/audit-report/*',{timeout:120000})
await page.getByRole('heading',{name:'Audit Report',exact:true}).waitFor()
const mlResponse = await page.request.get(`http://127.0.0.1:5173/api/analysis/${aid}/ml`)
const ml = await mlResponse.json()
const savedRules = await (await page.request.get(`http://127.0.0.1:5173/api/analysis/${aid}/rules`)).json()
if (!ml.rows.some(row => row.SHAP?.status === 'available')) throw new Error('No SHAP explanations in the saved analysis')
for (const width of [1440, 390]) {
 await page.setViewportSize({width, height:1000})
 for (const view of ['ml', 'xai']) {
  await page.goto(`http://127.0.0.1:5173/app/${view}/${aid}`, {waitUntil:'domcontentloaded'})
  if (view === 'xai') {
   await page.getByRole('heading', {name:`${savedRules.summary.failed} failed checks need explanation and review`}).waitFor()
   if (await page.locator('.xai-rule-card').count() !== savedRules.summary.failed) throw new Error('XAI omitted failed rules')
   if (await page.locator('.shap-explanation').count()) throw new Error('XAI duplicated the full ML page')
   await page.getByLabel('Reporting year').selectOption(String(ml.rows.at(-1).Year))
   const expected = savedRules.violations.filter(r=>r.Year===ml.rows.at(-1).Year).length
   if (await page.locator('.xai-rule-card').count() !== expected) throw new Error('XAI year filter omitted evidence')
   await page.getByRole('heading', {name:'Why this rule failed'}).first().waitFor()
   await page.getByLabel('Search failed rules').fill('no-match-fixture')
   await page.getByRole('heading', {name:'No failures match these filters'}).waitFor()
   await page.getByRole('button', {name:'Clear filters'}).click()
   if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))errors.push(`XAI overflow at ${width}`)
   await page.evaluate(()=>window.scrollTo(0,0))
   await page.screenshot({path:`output/ui-review/rule-xai-${width}.png`,fullPage:true})
   continue
  }
  await page.getByRole('heading', {name:'How the score adds up'}).waitFor()
  if (await page.locator('.shap-feature').count() !== 6) throw new Error('Expected six ranked SHAP contributions')
  await page.getByRole('button', {name:/Show all .* contributions/}).click()
  if (await page.locator('.shap-feature').count() <= 6) throw new Error('Contribution expansion failed')
  await page.getByRole('button', {name:'Show top 6'}).click()
  await page.getByLabel('Reporting year').selectOption(String(ml.rows.at(-1).Year))
  if (ml.rows.at(-1).Prediction === 'Normal') {
   await page.getByRole('heading', {name:`Why ${ml.rows.at(-1).Year} was not flagged`}).waitFor()
   await page.getByRole('heading', {name:'Factors moving away from anomaly'}).waitFor()
  }
  if (view === 'xai') {
   await page.getByRole('region', {name:'Overall assessment'}).waitFor()
   if (ml.rows.every(row => row.Prediction === 'Normal')) await page.getByRole('heading', {name:'No ML anomalies detected in the assessed years'}).waitFor()
  }
  await page.getByText('How SHAP was calculated', {exact:true}).click()
  if (await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)) errors.push(`SHAP overflow at ${width} ${view}`)
  await page.evaluate(()=>window.scrollTo(0,0))
  await page.screenshot({path:`output/ui-review/shap-${view}-${width}.png`, fullPage:true})
 }
}
await page.setViewportSize({width:1440,height:1000})
// Saved pre-SHAP results must remain readable and must not imply attribution exists.
await page.route(`**/api/analysis/${aid}/ml`, async route => {
 const legacy = structuredClone(ml)
 for (const row of legacy.rows) delete row.SHAP
 await route.fulfill({json:legacy})
})
await page.goto(`http://127.0.0.1:5173/app/ml/${aid}`)
await page.getByRole('heading', {name:'SHAP explanation unavailable'}).waitFor()
await page.getByText('This saved analysis predates SHAP.', {exact:false}).waitFor()
if (ml.rows.every(row => row.Prediction === 'Normal')) await page.getByRole('heading', {name:/Why .* was not flagged/}).waitFor()
await page.unroute(`**/api/analysis/${aid}/ml`)
await page.goto(`http://127.0.0.1:5173/app/reviews/${aid}?finding=${encodeURIComponent('ml:' + ml.rows.at(-1).Year)}`)
await page.getByRole('heading', {name:'How the score adds up'}).waitFor()
await page.goto(`http://127.0.0.1:5173/app/audit-report/${aid}`)
await page.getByRole('link',{name:'Finding review',exact:true}).click()
await page.locator('.finding-select').first().click()
await page.getByRole('heading',{name:'Review decision'}).waitFor()
await page.getByLabel('Review note').fill('Browser verification: checked source values and supporting evidence.')
await page.getByLabel('Status',{exact:true}).selectOption('investigating')
await Promise.all([page.waitForResponse(r=>r.url().includes('/finding')&&r.request().method()==='PUT'),page.getByRole('button',{name:'Save review',exact:true}).click()])
await page.locator('.review-history').getByText('Browser verification: checked source values and supporting evidence.',{exact:true}).waitFor()
await page.locator('.finding-select').first().filter({hasText:'investigating'}).waitFor()
await page.evaluate(()=>window.scrollTo(0,0))
await page.screenshot({path:'output/ui-review/workspace-review-desktop.png',fullPage:true})
await page.getByText('Source workbook cells for',{exact:false}).click()
if(await page.locator('.source-details tbody tr').count()===0)errors.push('No workbook provenance rows')
for(const width of [1440,390]){
 await page.setViewportSize({width,height:1000})
 for(const path of ['/app',`/app/reviews/${aid}`,'/app/team','/app/new']){
  await page.goto('http://127.0.0.1:5173'+path,{waitUntil:'domcontentloaded'})
  await page.waitForTimeout(450)
  if(path.includes('/reviews/')){await page.locator('.finding-select').first().click();await page.getByRole('heading',{name:'Review decision'}).waitFor()}
  if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))errors.push(`Overflow at ${width} ${path}`)
  await page.screenshot({path:`output/ui-review/workspace-${width}-${path.split('/').at(-1)}.png`,fullPage:true})
 }
}
await page.goto('http://127.0.0.1:5173/app',{waitUntil:'domcontentloaded'})
await page.getByRole('button',{name:'Sign out',exact:true}).click()
await page.waitForURL('**/login')
await page.getByLabel('Email address').fill(email)
await page.getByLabel('Password',{exact:true}).fill(password)
await page.getByRole('button',{name:'Sign in',exact:true}).click()
await page.waitForURL('**/app')
console.log(JSON.stringify({result:'complete',analysisId:aid,errors},null,2))
if(errors.length)throw new Error(errors.join('; '))
} finally { await browser.close() }


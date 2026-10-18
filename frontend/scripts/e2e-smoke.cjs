const fs = require('fs')
const path = require('path')
const { chromium } = require('playwright')

const root = path.resolve(__dirname, '..', '..')
const appUrl = 'http://localhost:5174/'
const apiUrl = process.env.VITE_API_URL || 'http://127.0.0.1:8000/api'
const clientFile = path.join(root, 'client_data.xlsx')
const downloadDir = path.join(root, 'runtime', 'test-downloads')

function assert(condition, message) {
  if (!condition) throw new Error(message)
}

async function expectText(page, text) {
  try {
    await page.waitForFunction(
      (value) => document.body.innerText.toLowerCase().includes(value.toLowerCase()),
      text,
      { timeout: 20000 }
    )
  } catch (error) {
    console.error('Expected text not found:', text)
    console.error('Current URL:', page.url())
    console.error((await page.locator('body').innerText().catch(() => '')).slice(0, 2500))
    throw error
  }
}

(async () => {
  fs.mkdirSync(downloadDir, { recursive: true })
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ acceptDownloads: true })
  const page = await context.newPage()
  const consoleErrors = []
  const requestFailures = []

  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text())
  })
  page.on('requestfailed', (request) => {
    const line = `${request.method()} ${request.url()} ${request.failure()?.errorText || ''}`
    if (line.includes('/audit-report.pdf') && line.includes('ERR_ABORTED')) return
    requestFailures.push(line)
  })

  await page.goto(appUrl, { waitUntil: 'networkidle' })
  await expectText(page, 'Precision Intelligence')
  await page.getByRole('button', { name: /Get Started/i }).first().click()
  await page.waitForURL('**/app')
  await page.setInputFiles('input[type="file"]', clientFile)
  await expectText(page, 'client_data.xlsx')
  await page.getByRole('button', { name: /Process Client/i }).click()
  await page.waitForURL('**/app/audit-report/**', { timeout: 60000 })

  const analysisId = await page.evaluate(() => localStorage.getItem('finsight:analysisId'))
  assert(analysisId && /^\d+$/.test(analysisId), 'analysisId was not stored after processing')
  await expectText(page, 'AARTI DRUGS LTD')
  await expectText(page, 'Rule Failures')
  await expectText(page, 'Download Detailed PDF')

  const pages = [
    ['Analysis', 'analysis', 'Client Analysis', 'Profit_Margin'],
    ['Rule Engine', 'rules', 'Rule Engine', 'BS-001'],
    ['ML Anomaly Detection', 'ml', 'ML Anomaly Detection', 'Decision score'],
    ['XAI', 'xai', 'Explainable AI', 'Recommendations'],
    ['Audit Trail', 'trail', 'Audit Trail', 'Generated detailed audit report PDF'],
    ['Audit Report', 'audit-report', 'Audit Report', 'Download Detailed PDF'],
  ]

  for (const [link, slug, heading, content] of pages) {
    await page.locator(`a[href="/app/${slug}/${analysisId}"]`).first().click()
    await page.waitForURL(`**/app/${slug}/${analysisId}`, { timeout: 20000 })
    await expectText(page, heading)
    await expectText(page, 'AARTI DRUGS LTD')
    await expectText(page, content)
  }

  const trailBefore = await page.request.get(`${apiUrl}/analysis/${analysisId}/trail`).then((r) => r.json())
  await page.getByRole('link', { name: 'Analysis' }).click()
  await page.getByRole('link', { name: 'Audit Trail' }).click()
  const trailAfter = await page.request.get(`${apiUrl}/analysis/${analysisId}/trail`).then((r) => r.json())
  assert(trailBefore.events.length === trailAfter.events.length, 'navigation changed audit trail event count, suggesting a rerun')

  await page.getByRole('link', { name: /PDF/i }).first().click()
  const download = await page.waitForEvent('download', { timeout: 20000 }).catch(() => null)
  if (!download) {
    const [nextDownload] = await Promise.all([
      page.waitForEvent('download', { timeout: 20000 }),
      page.getByRole('link', { name: /Download Detailed PDF/i }).click(),
    ])
    await nextDownload.saveAs(path.join(downloadDir, nextDownload.suggestedFilename()))
  } else {
    await download.saveAs(path.join(downloadDir, download.suggestedFilename()))
  }

  assert(consoleErrors.length === 0, `console errors: ${consoleErrors.join(' | ')}`)
  assert(requestFailures.length === 0, `request failures: ${requestFailures.join(' | ')}`)

  console.log(JSON.stringify({ ok: true, analysisId, downloadedTo: downloadDir, pages: pages.map((p) => p[0]) }, null, 2))
  await browser.close()
})().catch(async (error) => {
  console.error(error)
  process.exit(1)
})

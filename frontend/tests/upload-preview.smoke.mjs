import { chromium } from 'playwright'
import assert from 'node:assert/strict'
import fs from 'node:fs'

const browser = await chromium.launch({headless: true, channel: 'msedge'})
try {
  const page = await browser.newPage()
  const errors = []
  page.on('pageerror', e => errors.push(e.message))
  await page.route('**/api/auth/me', r => r.fulfill({json: {user: {name: 'Preview tester', role: 'admin'}, organization: {name: 'Test workspace'}, csrf_token: 'test'}}))
  const preview = {valid: true, file_hash: 'abc', company: 'Sample company', years: [2024, 2025], financial_units: {status: 'unknown', label: 'Source units unspecified'}, errors: [], warnings: ['Some key metrics are unavailable.'], invalid_cells: [], missing_metrics: [{year: 2025, metrics: ['Borrowings']}], columns: ['Sales', 'Net profit'], rows: [{Year: 2024, Sales: 100, 'Net profit': 10}, {Year: 2025, Sales: 120, 'Net profit': null}]}
  await page.route('**/api/analysis/preview', r => r.fulfill({json: preview}))
  await page.goto('http://127.0.0.1:5173/app/new')
  await page.getByRole('heading', {name: '1. Prepare your workbook'}).waitFor()
  const guideImage = page.getByRole('img', {name: /Blank Data Sheet/})
  assert(await guideImage.evaluate(image => image.complete && image.naturalWidth > 0), 'Workbook picture must load')
  assert.equal(await page.locator('.upload-sheet-marker').count(), 12, 'Workbook picture must mark the key cells and sections')
  await page.getByRole('heading', {name: 'One column = one financial year'}).waitFor()
  await page.getByText('B16 · 31 Mar 2025').waitFor()
  await page.getByText('B56 · 31 Mar 2025').waitFor()
  await page.getByText('B81 · 31 Mar 2025').waitFor()
  await page.getByRole('link', {name: 'Open the sheet full size'}).waitFor()
  const [templateDownload] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('link', {name: 'Download blank template'}).click(),
  ])
  assert.equal(templateDownload.suggestedFilename(), 'FinSight_Template.xlsx')
  await page.getByLabel('Choose financial workbook').setInputFiles('../client_data.xlsx')
  await page.getByRole('button', {name: 'Preview workbook'}).click()
  const start = page.getByRole('button', {name: 'Confirm and start analysis'})
  await start.waitFor()
  assert(await start.isDisabled())
  await page.getByRole('checkbox').check()
  assert(await start.isEnabled())
  fs.mkdirSync('../output/ui-review', {recursive: true})
  for (const width of [1440, 390]) {
    await page.setViewportSize({width, height: 1000})
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, `Overflow at ${width}`)
    await page.screenshot({path: `../output/ui-review/upload-preview-${width}.png`, fullPage: true})
  }
  await page.getByLabel('Choose financial workbook').setInputFiles('../client_data.xlsx')
  assert.equal(await start.count(), 0, 'Changing file must discard old confirmation')
  preview.valid = false; preview.errors = ['Fix the value at Data Sheet!B10.']
  await page.getByRole('button', {name: 'Preview workbook'}).click()
  await page.getByText('Fix the value at Data Sheet!B10.').waitFor()
  assert.equal(await start.count(), 0, 'Invalid data must not offer submission')
  assert.deepEqual(errors, [])
  console.log('Upload preview UI passed: confirmation, replacement, invalid input, desktop and mobile.')
} finally { await browser.close() }

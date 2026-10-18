import { chromium } from 'playwright'
import assert from 'node:assert/strict'
const browser = await chromium.launch({headless:true,channel:'msedge'})
try {
 const page = await browser.newPage()
 const rows = [2024,2025].map((Year,i)=>({Company:'Unit test',Year,Sales:250+i*50,'Net profit':25+i*5,Interest:10,Debt_to_Equity:1.5,Profit_Margin:0.1}))
 await page.route('**/api/auth/me',r=>r.fulfill({json:{user:{name:'Tester',role:'admin'},organization:{name:'QA'},csrf_token:'test'}}))
 await page.route('**/api/analysis/999',r=>r.fulfill({json:{company:'Unit test',job:{state:'completed'}}}))
 await page.route('**/api/analysis/999/analysis',r=>r.fulfill({json:{company:'Unit test',rows,columns:Object.keys(rows[0]),financial_units:{status:'unknown'}}}))
 await page.goto('http://127.0.0.1:5173/app/analysis/999')
 await page.getByText('Monetary values: ₹ crore.',{exact:true}).waitFor()
 assert.equal(await page.locator('.kpi-card').first().locator('strong').innerText(),'300')
 await page.locator('.chart-point').first().focus()
 await page.getByText('250 ₹ crore',{exact:true}).waitFor()
 await page.locator('.metric-explorer select').selectOption('Debt_to_Equity')
 assert.equal(await page.locator('.explorer-summary strong').first().innerText(),'1.5x')
 await page.locator('.metric-explorer select').selectOption('Interest')
 assert.equal(await page.locator('.explorer-summary strong').first().innerText(),'10 ₹ crore')
 console.log('Analytics UI units passed: source values unchanged, crore tooltips, ratio and interest formatting.')
} finally {await browser.close()}

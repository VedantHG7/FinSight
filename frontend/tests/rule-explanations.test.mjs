import test from 'node:test'
import assert from 'node:assert/strict'
import { failedRules, explainRule } from '../src/ruleExplanations.js'

test('all failures remain available, including more than eight per year', () => {
 const rows = Array.from({length:12}, (_,i)=>({Year:2025,Status:'fail','Rule ID':`R${i}`,Severity:'High'}))
 rows.push({Year:2025,Status:'pass'})
 assert.equal(failedRules(rows).length,12)
 assert.equal(failedRules(rows,'2024').length,0)
 assert.equal(failedRules(rows,'2025','High','R11').length,1)
})
test('reconciliation explanations describe proxies without inventing missing evidence', () => {
 const result = explainRule({Formula:'cash_delta_tieout',Observed:{'Cash & Bank':5}})
 assert.match(result.condition,/previous period/)
 assert.match(result.action,/opening cash/)
 assert.match(result.limitation,/Legitimate movements/)
 assert.deepEqual(result.values,[['Cash & Bank',5]])
})
test('unknown rule uses saved evidence rather than guessing a cause', () => {
 assert.equal(explainRule({Message:'Saved failure',Formula:'unknown'}).condition,'Saved failure')
})

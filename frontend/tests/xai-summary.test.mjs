import test from 'node:test'
import assert from 'node:assert/strict'
import { summarizeAssessment } from '../src/xaiSummary.js'

test('all normal years still yield a conclusion and preserve failed rules', () => {
 const value = summarizeAssessment([{Year:2024,'ML Prediction':'Normal','ML Coverage Percent':100,'Violation Count':2},{Year:2025,'ML Prediction':'Normal','ML Coverage Percent':75,'Violation Count':0}])
 assert.match(value.title, /No ML anomalies/)
 assert.equal(value.normal, 2)
 assert.equal(value.failures, 2)
 assert.equal(value.coverageGaps, 1)
})
test('unavailable years are never counted as normal', () => {
 const value = summarizeAssessment([{'ML Prediction':'Normal'},{'ML Prediction':'Unavailable'}])
 assert.equal(value.normal, 1)
 assert.equal(value.unavailable, 1)
 assert.match(value.title, /some years could not be assessed/)
 assert.match(summarizeAssessment([{'ML Prediction':'Unavailable'}]).title, /Insufficient data/)
})
test('empty results and flagged results are distinct', () => {
 assert.match(summarizeAssessment([]).title, /No assessment/)
 const value = summarizeAssessment([{Prediction:'Anomaly'},{Prediction:'Normal'}])
 assert.equal(value.flagged, 1)
 assert.match(value.title, /needs anomaly review/)
})

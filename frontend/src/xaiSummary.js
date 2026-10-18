export function summarizeAssessment(rows = []) {
  const prediction = r => r.Prediction || r['ML Prediction']
  const flagged = rows.filter(r => prediction(r) === 'Anomaly').length
  const normal = rows.filter(r => prediction(r) === 'Normal').length
  const unavailable = rows.length - flagged - normal
  const failures = rows.reduce((total, r) => total + (Number(r['Violation Count']) || 0), 0)
  const coverageGaps = rows.filter(r => {
    const coverage = r['Coverage Percent'] ?? r['ML Coverage Percent']
    return coverage == null || coverage < 100
  }).length
  const title = !rows.length ? 'No assessment is available yet' : flagged ? `${flagged} reporting ${flagged === 1 ? 'year needs' : 'years need'} anomaly review` : !normal ? 'Insufficient data for an ML conclusion' : unavailable ? 'No anomalies in the scored years; some years could not be assessed' : 'No ML anomalies detected in the assessed years'
  return { flagged, normal, unavailable, failures, coverageGaps, title }
}

import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { AccountBar, useAuth } from './Accounts'
import { api } from './api'

export default function UploadPreview() {
  const { account } = useAuth(), navigate = useNavigate()
  const [file, setFile] = useState(null), [preview, setPreview] = useState(null)
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [confirmed, setConfirmed] = useState(false)
  if (account.user.role === 'reviewer') return <Navigate to="/app" replace />
  const select = value => { setFile(value); setPreview(null); setConfirmed(false); setError('') }
  const submit = async (start = false) => {
    if (!file) return setError('Select an Excel workbook first.')
    if (!/\.(xlsx|xls)$/i.test(file.name)) return setError('Choose an Excel workbook (.xlsx or .xls).')
    if (file.size > 10 * 1024 * 1024) return setError('Workbook exceeds the 10 MB upload limit.')
    if (start && (!preview?.valid || !confirmed)) return
    setBusy(true); setError('')
    const form = new FormData(); form.append('file', file)
    if (start) form.append('preview_hash', preview.file_hash)
    try {
      const data = await api(start ? '/analysis/upload' : '/analysis/preview', { method: 'POST', body: form })
      if (start) { localStorage.setItem('finsight:analysisId', String(data.analysis_id)); navigate('/app/processing/' + data.analysis_id) }
      else { setPreview(data); setConfirmed(false) }
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  return <div className="workspace"><AccountBar /><main className="workspace-main upload-preview">
    <div className="page-title"><p className="eyebrow">New analysis · Review your inputs</p><h1>Check your workbook before analysis.</h1><p>Preview the company, years and source values. Analysis starts only after you review and confirm.</p></div>
    <section className="finding-card"><h2>1. Choose a workbook</h2><p>One company · Up to 10 MB · .xlsx or .xls · Financial data on Data Sheet</p>
      <label className="drop-zone" onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); if (!busy) select(e.dataTransfer.files?.[0] || null) }}>
        <strong>{file?.name || 'Choose or drop a workbook'}</strong><input aria-label="Choose financial workbook" type="file" accept=".xlsx,.xls" disabled={busy} onChange={e => { select(e.target.files?.[0] || null); e.target.value = '' }} />
      </label><button className="primary-button slim" disabled={busy || !file} onClick={() => submit()}>{busy ? 'Working…' : 'Preview workbook'}</button>
    </section>
    {error && <p role="alert" className="error-text">{error}</p>}
    {preview && <section className="finding-card" aria-label="Workbook preview">
      <h2>2. Review detected data</h2><p><strong>{preview.company || 'Company not detected'}</strong></p><p>Reporting years: {preview.years.join(', ') || 'Not detected'}</p><p>Monetary units: <strong>{preview.financial_units.label}</strong></p><p className="upload-help">Source values are shown as supplied. No currency conversion or scaling is applied. Ratios and share counts retain their own units.</p>
      {preview.errors.length > 0 && <div role="alert"><h3>Fix before continuing</h3><ul>{preview.errors.map(t => <li key={t}>{t}</li>)}</ul></div>}
      {preview.invalid_cells.length > 0 && <ul>{preview.invalid_cells.map((c, i) => <li key={i}>Data Sheet!{c.cell} · {c.year} · {c.source_label}: “{String(c.value)}”</li>)}</ul>}
      {preview.warnings.length > 0 && <div><h3>Review these warnings</h3><ul>{preview.warnings.map(t => <li key={t}>{t}</li>)}</ul></div>}
      {preview.missing_metrics.length > 0 && <details><summary>Missing metrics by year</summary>{preview.missing_metrics.map(r => <p key={r.year}><strong>{r.year}:</strong> {r.metrics.join(', ')}</p>)}</details>}
      {preview.rows.length > 0 && <div className="preview-table" tabIndex="0" role="region" aria-label="Source values by reporting year"><table><caption>Source financial values · blank values are unavailable</caption><thead><tr><th scope="col">Metric</th>{preview.years.map(y => <th scope="col" key={y}>{y}</th>)}</tr></thead><tbody>{preview.columns.map(c => <tr key={c}><th scope="row">{c}</th>{preview.rows.map(r => <td key={r.Year}>{r[c] == null ? '—' : String(r[c])}</td>)}</tr>)}</tbody></table></div>}
      {preview.valid && <><label className="preview-confirm"><input type="checkbox" checked={confirmed} disabled={busy} onChange={e => setConfirmed(e.target.checked)} /><span>I have checked the company, reporting years, currency and units{preview.financial_units.status !== 'detected' ? ' (continuing with units unspecified)' : ''}, and reviewed any missing-data warnings.</span></label><button className="primary-button slim" disabled={busy || !confirmed} onClick={() => submit(true)}>{busy ? 'Starting…' : 'Confirm and start analysis'}</button></>}
      <p className="upload-help">To correct the data, edit your workbook, choose the updated file and preview it again.</p>
    </section>}
  </main></div>
}


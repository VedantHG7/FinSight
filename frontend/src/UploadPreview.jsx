import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { AccountBar, useAuth } from './Accounts'
import { api } from './api'

const sheetMarkers = [
  { number: 1, left: '24%', top: '1.5%' },
  { number: 2, left: '12%', top: '5.4%' },
  { number: 3, left: '12%', top: '16.2%' },
  { number: 3, left: '12%', top: '42.8%' },
  { number: 3, left: '12%', top: '58.1%' },
  { number: 3, left: '12%', top: '84.7%' },
  { number: 4, left: '22%', top: '17.4%' },
  { number: 4, left: '22%', top: '59.1%' },
  { number: 4, left: '22%', top: '85.7%' },
  { number: 5, left: '12%', top: '18.5%' },
  { number: 6, left: '27%', top: '18.5%' },
  { number: 7, left: '12%', top: '96.1%' },
]

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
    <div className="page-title"><p className="eyebrow">New analysis · Review your inputs</p><h1>Upload a financial workbook.</h1><p>Check the format, preview the detected data, then confirm when it looks right. Analysis starts only after your confirmation.</p></div>
    <section className="finding-card upload-format-guide" aria-labelledby="workbook-format-title">
      <div className="upload-format-heading"><div><h2 id="workbook-format-title">1. Prepare your workbook</h2><p>This is the blank version of the example workbook. It has the same sheets, row names, and columns. Fill in one company’s data, then upload the Excel file (up to 10 MB).</p></div><a className="secondary-button" href="/data/FinSight_Template.xlsx" download="FinSight_Template.xlsx">Download blank template</a></div>
      <div className="upload-sheet-guide">
        <figure className="upload-sheet-figure">
          <div className="upload-sheet-frame" tabIndex="0" role="region" aria-label="Scrollable, numbered picture of the blank Data Sheet template"><div className="upload-sheet-artwork"><img src="/data/FinSight_Template_Preview.png" alt="Blank Data Sheet. Numbered markers point to the company name, section titles, reporting date rows, metric labels, and empty amount cells." />{sheetMarkers.map((marker, index) => <span className="upload-sheet-marker" style={{ left: marker.left, top: marker.top }} aria-hidden="true" key={index}>{marker.number}</span>)}</div></div>
          <figcaption>Numbered dots point to cells in the actual template. Scroll the picture to see Balance Sheet and Cash Flow. <a href="/data/FinSight_Template_Preview.png" target="_blank" rel="noreferrer">Open the sheet full size</a></figcaption>
        </figure>
        <div className="upload-sheet-key" aria-label="What the numbered parts mean">
          <div><span className="upload-sheet-key-number">1</span><p><strong>Company name · B1</strong><br />Replace the blank cell with the company you are uploading. Use one company per workbook.</p></div>
          <div><span className="upload-sheet-key-number">2</span><p><strong>META · company details</strong><br />Face Value (B7), Current Price (B8), and Market Capitalization (B9) are optional reference fields. Leave the version values in B2/B3 and the B6 formula unchanged.</p></div>
          <div><span className="upload-sheet-key-number">3</span><p><strong>Statement sections</strong><br />The headings at <strong>A15, A40, A55, and A80</strong> group Profit &amp; Loss, Quarters, Balance Sheet, and Cash Flow. Fill the three annual sections for analysis; Quarters is optional.</p></div>
          <div><span className="upload-sheet-key-number">4</span><p><strong>Blue Report Date rows</strong><br />These tell FinSight which financial year each column belongs to. For FY 2025, enter the full end date <strong>31 Mar 2025</strong> in <strong>B16, B56, and B81</strong>. The Quarters date row is separate.</p></div>
          <div><span className="upload-sheet-key-number">5</span><p><strong>Metric names · column A</strong><br />Sales, Net profit, Borrowings, and the other row names say what each number means. Keep their names and order.</p></div>
          <div><span className="upload-sheet-key-number">6</span><p><strong>Your figures · columns B–K</strong><br />Enter each amount where its metric row meets its year column. For example, <strong>B17</strong> is Sales for the date in <strong>B16</strong>. Leave unavailable values blank.</p></div>
          <div><span className="upload-sheet-key-number">7</span><p><strong>PRICE and DERIVED · bottom rows</strong><br />These are optional reference fields. FinSight does not use them for the annual analysis.</p></div>
        </div>
      </div>
      <div className="upload-year-example"><div><p className="eyebrow">How year-wise data works</p><h3>One column = one financial year</h3><p>For the same year, repeat its date in all three annual Report Date rows. Then put that year’s figures below those dates in the same column.</p></div><div className="upload-year-table" role="region" aria-label="Example of matching annual reporting dates"><table><thead><tr><th scope="col">Data Sheet section</th><th scope="col">Column B · FY 2025</th><th scope="col">Column C · FY 2024</th></tr></thead><tbody><tr><th scope="row">Profit &amp; Loss</th><td>B16 · 31 Mar 2025</td><td>C16 · 31 Mar 2024</td></tr><tr><th scope="row">Balance Sheet</th><td>B56 · 31 Mar 2025</td><td>C56 · 31 Mar 2024</td></tr><tr><th scope="row">Cash Flow</th><td>B81 · 31 Mar 2025</td><td>C81 · 31 Mar 2024</td></tr></tbody></table></div><p className="upload-year-tip">Example: the Sales amount in B17 belongs to FY 2025; the Sales amount in C17 belongs to FY 2024. Type complete Excel dates in the blue rows, not just “2025” or “2024”. If you have only one year of data, fill column B and leave later year columns empty.</p></div>
      <p className="upload-help">FinSight analyses the annual Profit &amp; Loss, Balance Sheet, and Cash Flow figures in the <strong>Data Sheet</strong>. Quarters and the other formula sheets are there for reference. Use one consistent currency and scale for monetary amounts.</p>
    </section>
    <section className="finding-card"><h2>2. Choose a workbook</h2><p>Only the Data Sheet is analysed. Other sheets are ignored.</p>
      <label className="drop-zone" onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); if (!busy) select(e.dataTransfer.files?.[0] || null) }}>
        <strong>{file?.name || 'Choose or drop a workbook'}</strong><input aria-label="Choose financial workbook" type="file" accept=".xlsx,.xls" disabled={busy} onChange={e => { select(e.target.files?.[0] || null); e.target.value = '' }} />
      </label><button className="primary-button slim" disabled={busy || !file} onClick={() => submit()}>{busy ? 'Working…' : 'Preview workbook'}</button>
    </section>
    {error && <p role="alert" className="error-text">{error}</p>}
    {preview && <section className="finding-card" aria-label="Workbook preview">
      <h2>3. Review detected data</h2><p><strong>{preview.company || 'Company not detected'}</strong></p><p>Reporting years: {preview.years.join(', ') || 'Not detected'}</p><p>Monetary units: <strong>{preview.financial_units.label}</strong></p><p className="upload-help">Source values are shown as supplied. No currency conversion or scaling is applied. Ratios and share counts retain their own units.</p>
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


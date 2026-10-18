import { reportingUnit, metricType, metricUnit } from './analyticsUnits'
import Icon from './Icon'
import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { Link, Navigate, Route, Routes, useNavigate, useParams } from 'react-router-dom'
import Onboarding from './pages/Onboarding'
import logo from './assets/finsight-logo.jpg'
import { API, api } from './api'
import { AuthProvider, AuthPage, ForgotPasswordPage, ResetPasswordPage, ChangePasswordPage, RequireAccount, AccountBar, useAuth } from './Accounts'
import { Workspace, JobPage, TeamPage } from './Workspace'
import Reviews from './Reviews'
import { MLInsights } from './MLInsights'
import XAIPage from './XAIPage'
import UploadPreview from './UploadPreview'

const STAGES = ['Upload validation', 'Preprocessing', 'Rule Engine', 'ML Anomaly Detection', 'Explainable AI', 'Audit Report']
const NAV = [
  { to: '/app', label: 'Client history', icon: 'history' },
  { to: '/app/new', label: 'New analysis', icon: 'add_circle' },
  { key: 'analysis', label: 'Financial analytics', icon: 'analytics' },
  { key: 'reviews', label: 'Finding review', icon: 'fact_check' },
  { key: 'rules', label: 'Rule Engine', icon: 'rule' },
  { key: 'ml', label: 'ML Anomaly Detection', icon: 'query_stats' },
  { key: 'xai', label: 'Explainable AI', icon: 'auto_awesome' },
  { key: 'trail', label: 'Audit Trail', icon: 'history' },
  { key: 'audit-report', label: 'Audit Report', icon: 'assessment' },
]

function App() {
 return <AuthProvider><Routes>
  <Route path="/" element={<Onboarding/>}/><Route path="/onboarding" element={<Onboarding/>}/>
  <Route path="/login" element={<AuthPage/>}/><Route path="/register" element={<AuthPage/>}/>
  <Route path="/forgot-password" element={<ForgotPasswordPage/>}/><Route path="/reset-password" element={<ResetPasswordPage/>}/>
  <Route element={<RequireAccount/>}>
   <Route path="/app" element={<Workspace/>}/><Route path="/app/new" element={<UploadPreview/>}/><Route path="/app/team" element={<TeamPage/>}/><Route path="/app/change-password" element={<ChangePasswordPage/>}/>
   <Route path="/app/processing/:analysisId" element={<JobPage/>}/><Route path="/app/processing" element={<Navigate to="/app" replace/>}/>
   <Route path="/app/reviews/:analysisId" element={<ReviewWorkspace/>}/>
   {['analysis','rules','ml','xai','trail','audit-report'].map(page=><Route key={page} path={`/app/${page}/:analysisId`} element={<Dashboard page={page}/>}/>)}
  </Route><Route path="*" element={<Navigate to="/" replace/>}/>
 </Routes></AuthProvider>
}

function Dashboard({page}){
 const {analysisId}=useParams(),navigate=useNavigate()
 const [summary,setSummary]=useState(null),[data,setData]=useState(null),[error,setError]=useState('')
 useEffect(()=>{
  let active=true;setSummary(null);setData(null);setError('');localStorage.setItem('finsight:analysisId',analysisId)
  api('/analysis/'+analysisId).then(async next=>{
   if(!active)return
   if(next.job.state!=='completed'){navigate('/app/processing/'+analysisId,{replace:true});return}
   const result=await api('/analysis/'+analysisId+'/'+pageEndpoint(page))
   if(active){setSummary(next);setData({...result,__page:page,__analysisId:analysisId})}
  }).catch(err=>{if(active)setError(err.message)})
  return()=>{active=false}
 },[analysisId,page,navigate])
 if(error)return <Layout page={page} analysisId={analysisId} summary={summary}><Empty title="Unable to load page" text={error}/></Layout>
 if(!summary||!data||data.__page!==page||data.__analysisId!==analysisId)return <Layout page={page} analysisId={analysisId}><Empty title="Loading client data" text="Reading this analysis."/></Layout>
 const pages={analysis:<AnalysisPage key={analysisId} data={data} analysisId={analysisId}/>,rules:<RulesPage data={data}/>,ml:<MLInsights data={data}/>,xai:<XAIPage data={data}/>,trail:<TrailPage data={data}/>,'audit-report':<ReportPage data={data} analysisId={analysisId}/>}
 return <Layout page={page} analysisId={analysisId} summary={summary}>{pages[page]}</Layout>
}

function ReviewWorkspace(){const {analysisId}=useParams();return <Layout page="reviews" analysisId={analysisId}><Reviews/></Layout>}

function Layout({children,page,analysisId,summary}){
 const [menuOpen,setMenuOpen]=useState(false),{account}=useAuth()
 return <div className="app-shell"><a className="skip-link" href="#workspace-content">Skip to content</a><aside className={`sidebar ${menuOpen?'is-open':''}`}><Link className="brand" to="/app"><img src={logo} alt=""/><span>FinSight</span></Link><div className="profile"><Icon>person</Icon><div><strong>{account.user.name}</strong><small>{account.organization.name}</small></div></div><p className="nav-caption">Audit workspace</p><nav aria-label="Workspace navigation">{NAV.filter(item=>!(account.user.role==='reviewer'&&item.to==='/app/new')).map(item=><Link key={item.label} className={item.key===page?'active':''} aria-current={item.key===page?'page':undefined} onClick={()=>setMenuOpen(false)} to={item.to||`/app/${item.key}/${analysisId}`}><Icon>{item.icon}</Icon>{item.label}</Link>)}</nav><div className="sidebar-footer"><Icon>insights</Icon><strong>Clarity in every finding.</strong><p>Financial intelligence, connected.</p><Link to="/app/team">Team & workspace ↗</Link></div></aside><section className="main-pane"><header className="topbar"><button className="menu-toggle" aria-label={menuOpen?'Close navigation':'Open navigation'} aria-expanded={menuOpen} onClick={()=>setMenuOpen(!menuOpen)}><Icon>{menuOpen?'close':'menu'}</Icon></button><div><p className="eyebrow">{summary?.company?'Current client':account.organization.name}</p><h2>{summary?.company||'Finding review'}</h2></div>{analysisId&&<a className="icon-button" href={`${API}/analysis/${analysisId}/audit-report.pdf`}><Icon>download</Icon>PDF</a>}</header><main id="workspace-content" className="content">{summary?.overview?.analysis_status==='Completed with limitations'&&<section className="finding-card" role="status"><h3>Completed with limitations</h3><p>Some checks could not be evaluated. Rule coverage: {summary.overview.rule_coverage_percent}%. ML: {formatStatus(summary.overview.ml_status)}. See the audit report for details.</p></section>}{children}</main></section></div>
}

const AmountUnitContext = createContext('')

function AnalysisPage({ data, analysisId }) {
  const rows = useMemo(() => [...(data.rows || [])].sort((a, b) => Number(a.Year) - Number(b.Year)), [data.rows])
  const [unitOverride, setUnitOverride] = useState(() => { try { const saved = localStorage.getItem('finsight:units:' + analysisId) || ''; return ['INR rupees', 'INR thousand', 'INR lakh', 'INR crore'].includes(saved) ? saved : '' } catch { return '' } })
  const amountUnit = reportingUnit(data.financial_units, unitOverride)
  const latest = rows.at(-1) || {}
  const previous = rows.at(-2) || {}
  const [growthGroup, setGrowthGroup] = useState('Business growth')
  const [explorerMetric, setExplorerMetric] = useState('Sales')
  const availableMetrics = useMemo(() => (data.columns || []).filter((column) => !['Company', 'Year'].includes(column) && rows.some((row) => isFiniteNumber(row[column]))), [data.columns, rows])
  useEffect(() => { if (!availableMetrics.includes(explorerMetric)) setExplorerMetric(availableMetrics[0] || '') }, [availableMetrics, explorerMetric])
  const period = yearRange(rows)
  const insights = financialInsights(rows)
  const growthGroups = {
    'Business growth': ['Revenue_Growth', 'Profit_Growth'],
    'Balance sheet': ['Asset_Growth', 'Borrowing_Growth', 'Reserve_Growth'],
    'Working capital': ['Receivable_Growth', 'Inventory_Growth'],
    'Cash flow': ['Operating_CF_Growth', 'Cash_Growth'],
  }
  return <AmountUnitContext.Provider value={amountUnit}><div className="analytics-page">
    <div className="analytics-hero">
      <div><p className="eyebrow">Financial Analytics</p><h1>Understand the numbers before reviewing exceptions.</h1><p>Explore financial performance, ratios, growth, cash flow and multi-year trends from the validated dataset.</p></div>
      <div className="analysis-context"><span><small>Company</small>{data.company}</span><span><small>Analysis period</small>{period}</span><Link to={`/app/ml/${analysisId}`}>View anomaly analysis <Icon>arrow_forward</Icon></Link></div>
    </div>

    <ValidationJourney data={data} />

    <AnalyticsSection title="Financial overview" description={`Latest reported values for ${latest.Year || 'the available period'}. Movements are descriptive and are not automatically good or bad.`}>
      <label>Reporting units <select aria-label="Reporting units" value={unitOverride} onChange={event => { const value = event.target.value; setUnitOverride(value); try { localStorage.setItem('finsight:units:' + analysisId, value) } catch {} }}><option value="">Workbook scale / ₹ crore default</option>{['INR rupees', 'INR thousand', 'INR lakh', 'INR crore'].map(unit => <option key={unit} value={unit}>{unit.replace('INR', '₹')}</option>)}</select></label><p className="chart-help">Select the units stated in your workbook. This label is saved for this analysis in this browser and does not rescale values.</p><p className="chart-help"><strong>Monetary values: {amountUnit}.</strong> Monetary totals and differences retain this scale; values are not divided or multiplied again. Ratios are unitless, growth and margins are percentages, and per-share values are in rupees. {amountUnit === '₹ crore' && '1 crore = ₹1,00,00,000; a source value of 250 means ₹250 crore.'} {!unitOverride && data.financial_units?.status !== 'detected' && 'Using your configured ₹ crore convention because the workbook has no unambiguous unit declaration. Choose another scale if needed.'}</p><div className="kpi-grid">{[
        ['Sales', 'Sales / Revenue', 'amount'], ['Net profit', 'Net Profit', 'amount'], ['Total Assets', 'Total Assets', 'amount'],
        ['Borrowings', 'Borrowings', 'amount'], ['Cash from Operating Activity', 'Operating Cash Flow', 'amount'],
      ].map(([metric, label, type]) => <KpiCard key={metric} label={label} metric={metric} current={latest[metric]} previous={previous[metric]} year={latest.Year} type={type} unit={amountUnit} />)}</div>
    </AnalyticsSection>

    <AnalyticsSection title="Revenue and profit trend" description="Are revenue and profit moving together? Separate scales prevent profit from being visually flattened by larger revenue values.">
      <div className="chart-grid two"><ChartCard title="Sales / Revenue" note={amountUnit}><TrendChart rows={rows} series={[series('Sales', 'Sales', '#0f766e', 'amount')]} /></ChartCard><ChartCard title="Net profit" note={amountUnit}><TrendChart rows={rows} series={[series('Net profit', 'Net profit', '#2563eb', 'amount')]} /></ChartCard></div>
    </AnalyticsSection>

    <AnalyticsSection title="Profitability" description="Historical movement in margins and returns. No external benchmark is assumed.">
      <ChartCard title="Profitability ratios" note="Percentage"><TrendChart rows={rows} series={[series('Profit_Margin', 'Profit margin', '#0f766e', 'percent'), series('Operating_Margin', 'Operating margin', '#2563eb', 'percent'), series('ROA', 'ROA', '#d97706', 'percent'), series('ROE', 'ROE', '#7c3aed', 'percent')]} /></ChartCard>
    </AnalyticsSection>

    <AnalyticsSection title="Cash flow quality" description="Compare reported profit with operating cash generation. A mismatch is a relationship to investigate, not proof of manipulation.">
      <div className="chart-grid two"><ChartCard title="Net profit vs operating cash flow" note={amountUnit}><GroupedBarChart rows={rows} series={[series('Net profit', 'Net profit', '#2563eb', 'amount'), series('Cash from Operating Activity', 'Operating cash flow', '#0f766e', 'amount')]} /></ChartCard><ChartCard title="Cash flow ratios" note="Trend / ratio and percentage"><TrendChart rows={rows} series={[series('Operating_CF_Ratio', 'Operating CF ratio', '#0f766e', 'percent'), series('Cash_Margin', 'Cash margin', '#d97706', 'ratio')]} /></ChartCard></div>
    </AnalyticsSection>

    <AnalyticsSection title="Solvency and liquidity" description="How leverage, debt-service capacity and cash support changed over time.">
      <div className="chart-grid two"><ChartCard title="Leverage and coverage" note="Ratio"><TrendChart rows={rows} series={[series('Debt_to_Equity', 'Debt to equity', '#dc2626', 'ratio'), series('Interest_Coverage', 'Interest coverage', '#2563eb', 'ratio'), series('Cash_to_Debt', 'Cash to debt', '#0f766e', 'ratio')]} /></ChartCard><ChartCard title="Liquidity movement" note="Ratio"><TrendChart rows={rows} series={[series('Working_Capital_Ratio', 'Working capital ratio', '#7c3aed', 'ratio'), series('Cash_to_Debt', 'Cash to debt', '#0f766e', 'ratio')]} /></ChartCard></div>
    </AnalyticsSection>

    <AnalyticsSection title="Efficiency and working capital" description="Ratios describe asset use, expenses and working-capital relationships using the standardized processed data.">
      <div className="chart-grid two"><ChartCard title="Efficiency history" note="Selected ratio trends"><TrendChart rows={rows} series={[series('Asset_Utilization', 'Asset utilization', '#2563eb', 'ratio'), series('Receivable_Ratio', 'Receivable ratio', '#0f766e', 'ratio'), series('Expense_Ratio', 'Expense ratio', '#dc2626', 'ratio')]} /></ChartCard><ChartCard title={`Latest ratio profile - ${latest.Year || 'N/A'}`} note="Horizontal comparison"><HorizontalBars row={latest} series={[series('Asset_Utilization', 'Asset utilization', '#2563eb', 'ratio'), series('Receivable_Ratio', 'Receivable ratio', '#0f766e', 'ratio'), series('Inventory_Ratio', 'Inventory ratio', '#d97706', 'ratio'), series('Expense_Ratio', 'Expense ratio', '#dc2626', 'ratio'), series('Depreciation_Ratio', 'Depreciation ratio', '#7c3aed', 'ratio')]} /></ChartCard></div>
    </AnalyticsSection>

    <AnalyticsSection title="Growth analysis" description="Related growth measures are grouped to keep the comparison readable.">
      <div className="segmented" role="group" aria-label="Growth metric group">{Object.keys(growthGroups).map((group) => <button type="button" key={group} className={growthGroup === group ? 'active' : ''} onClick={() => setGrowthGroup(group)}>{group}</button>)}</div>
      <div className="chart-grid two"><ChartCard title={growthGroup} note="Period-over-period trend"><TrendChart rows={rows} series={growthGroups[growthGroup].map((metric, index) => series(metric, readableMetric(metric), CHART_COLORS[index], 'percent'))} /></ChartCard><ChartCard title={`${growthGroup} heatmap`} note="Colour shows direction and strength"><GrowthHeatmap rows={rows} metrics={growthGroups[growthGroup]} /></ChartCard></div>
    </AnalyticsSection>

    <AnalyticsSection title="Long-term growth and stability" description="CAGR smooths multi-period growth, while volatility shows the magnitude of recent fluctuations. Higher volatility is not automatically fraud.">
      <div className="chart-grid two"><ChartCard title="Three-period CAGR" note="Grouped bars / requires sufficient history"><GroupedBarChart rows={rows} series={[series('Revenue_CAGR_3Y', 'Revenue CAGR', '#0f766e', 'percent'), series('Profit_CAGR_3Y', 'Profit CAGR', '#2563eb', 'percent')]} /></ChartCard><ChartCard title={`Latest volatility profile - ${latest.Year || 'N/A'}`} note="Horizontal comparison"><HorizontalBars row={latest} series={[series('Revenue_Volatility', 'Revenue', '#0f766e', 'amount'), series('Profit_Volatility', 'Profit', '#2563eb', 'amount'), series('Operating_CF_Volatility', 'Operating cash flow', '#d97706', 'amount')]} /></ChartCard></div>
    </AnalyticsSection>

    <AnalyticsSection title="Financial trend summary" description="Deterministic observations generated only from available values in the latest periods.">
      <div className="insight-grid">{insights.length ? insights.map((item) => <article className="insight-card" key={item.title}><Icon>{item.icon}</Icon><div><strong>{item.title}</strong><p>{item.text}</p></div></article>) : <EmptyState text="There is not enough comparable history to generate a factual trend summary." />}</div>
    </AnalyticsSection>

    <AnalyticsSection title="Explore metrics" description="Inspect any available processed metric without crowding the main dashboard.">
      <div className="metric-explorer"><label>Metric<select value={explorerMetric} onChange={(event) => setExplorerMetric(event.target.value)}>{availableMetrics.map((metric) => <option value={metric} key={metric}>{readableMetric(metric)}</option>)}</select></label><p className="chart-help">Unit: {metricUnit(explorerMetric, amountUnit)}</p><div className="explorer-summary"><span>Latest value<strong>{formatMetricValue(latest[explorerMetric], inferType(explorerMetric), amountUnit)}</strong></span><span>Latest period<strong>{latest.Year || 'N/A'}</strong></span><span>Change<strong>{formatDelta(latest[explorerMetric], previous[explorerMetric], inferType(explorerMetric))}</strong></span></div><TrendChart rows={rows} series={[series(explorerMetric, readableMetric(explorerMetric), '#0f766e', inferType(explorerMetric))]} /></div>
    </AnalyticsSection>

    <details className="data-detail"><summary>View validated data table</summary><div className="action-bar"><p>Monetary columns are in {amountUnit}. Ratios and percentage metrics retain their raw decimal values in this table and CSV; per-share values remain in rupees.</p><a className="primary-button slim" href={`${API}/analysis/${analysisId}/preprocessed.csv`}><Icon>download</Icon>Download CSV</a></div><DataTable columns={data.columns} rows={rows} /></details>
  </div></AmountUnitContext.Provider>
}

const CHART_COLORS = ['#0f766e', '#2563eb', '#d97706', '#7c3aed', '#dc2626']
const PERCENT_METRICS = new Set(['Profit_Margin', 'Operating_Margin', 'ROE', 'ROA', 'Operating_CF_Ratio', 'Depreciation_Ratio', 'Revenue_Growth', 'Profit_Growth', 'Borrowing_Growth', 'Asset_Growth', 'Reserve_Growth', 'Operating_CF_Growth', 'Receivable_Growth', 'Inventory_Growth', 'Cash_Growth', 'Revenue_CAGR_3Y', 'Profit_CAGR_3Y'])
function series(metric, label, color, type = 'ratio') { return { metric, label, color, type } }
function isFiniteNumber(value) { return value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value)) }
function readableMetric(metric = '') { return metric.replaceAll('_', ' ').replace(/\bCF\b/g, 'cash flow').replace(/\bROA\b/g, 'ROA').replace(/\bROE\b/g, 'ROE').replace(/\bCAGR\b/g, 'CAGR').replace(/\b\w/g, (letter) => letter.toUpperCase()) }
function inferType(metric) { return metricType(metric) }
function formatMetricValue(value, type = 'ratio', unit = '') { if (!isFiniteNumber(value)) return 'N/A'; const number = Number(value); if (type === 'percent') return `${(number * 100).toLocaleString('en-IN', { maximumFractionDigits: 1 })}%`; if (type === 'amount') return `${new Intl.NumberFormat('en-IN', { notation: 'standard', maximumFractionDigits: 2 }).format(number)}${unit ? ' ' + unit : ''}`; if (type === 'perShare') return `₹${number.toLocaleString('en-IN')} / share`; if (type === 'days') return `${number.toLocaleString('en-IN')} days`; if (type === 'number') return number.toLocaleString('en-IN', { maximumFractionDigits: 2 }); return `${number.toLocaleString('en-IN', { maximumFractionDigits: 2 })}x` }
function formatDelta(current, previous, type = 'amount') { if (!isFiniteNumber(current) || !isFiniteNumber(previous)) return 'N/A'; const delta = Number(current) - Number(previous); if (type === 'percent') return `${delta >= 0 ? '+' : ''}${(delta * 100).toFixed(1)} pp`; if (Number(previous) === 0) return `${delta >= 0 ? '+' : ''}${formatMetricValue(delta, type)}`; const rate = delta / Math.abs(Number(previous)); return `${rate >= 0 ? '+' : ''}${(rate * 100).toFixed(1)}%` }

function AnalyticsSection({ title, description, children }) { return <section className="analytics-section"><div className="section-heading"><div><h2>{title}</h2><p>{description}</p></div></div>{children}</section> }
function ChartCard({ title, note, children }) { return <article className="chart-card"><div className="chart-title"><h3>{title}</h3><span>{note}</span></div>{children}</article> }
function EmptyState({ text = 'Data unavailable for this metric.' }) { return <div className="chart-empty"><Icon>data_info_alert</Icon><p>{text}</p></div> }
function KpiCard({ label, metric, current, previous, year, type, unit }) {
  const comparable = isFiniteNumber(current) && isFiniteNumber(previous)
  const delta = comparable ? Number(current) - Number(previous) : null
  return <article className="kpi-card"><div className="kpi-label"><span>{label}</span><Icon>{metric === 'Sales' ? 'monitoring' : metric === 'Borrowings' ? 'account_balance' : 'payments'}</Icon></div><strong>{formatMetricValue(current, type)}</strong><small>{unit}</small><div className="kpi-foot"><span className={delta == null ? '' : delta >= 0 ? 'up' : 'down'}>{delta == null ? 'No prior comparison' : <><Icon>{delta >= 0 ? 'north_east' : 'south_east'}</Icon>{formatDelta(current, previous, type)} vs prior period</>}</span><small>{year || 'N/A'}</small></div></article>
}
function ValidationJourney({ data }) {
  const v = data.validation || {}
  return <section className="validation-journey"><div className="journey-head"><div><p className="eyebrow">Data readiness</p><h2>Before and after validation</h2><p>The source values are preserved, standardized, and extended with derived analytics. Missing values remain unavailable rather than becoming zero.</p></div><span className="completeness"><strong>{v.processed_completeness_percent ?? 'N/A'}%</strong>processed values available</span></div><div className="journey-flow"><div><span className="step-no">1</span><small>Uploaded data</small><strong>{v.source_records ?? data.raw_rows?.length ?? 0} periods</strong><p>{v.source_metrics ?? Math.max((data.raw_columns?.length || 2) - 2, 0)} source metrics</p></div><Icon>arrow_forward</Icon><div><span className="step-no">2</span><small>Validation</small><strong>Names and types checked</strong><p>Company, year and numeric values verified</p></div><Icon>arrow_forward</Icon><div><span className="step-no">3</span><small>Analytics ready</small><strong>{v.processed_records ?? data.rows?.length ?? 0} periods</strong><p>{v.processed_metrics ?? Math.max((data.columns?.length || 2) - 2, 0)} raw and engineered metrics</p></div></div><div className="journey-note"><Icon>info</Icon><p>{v.processed_values_missing ?? 0} processed cells are unavailable and stay excluded from affected visuals. Charts do not use ML-imputed values.</p></div></section>
}
function TrendChart({ rows, series: definitions }) {
  const [hovered, setHovered] = useState(null)
  const active = definitions.filter((definition) => rows.some((row) => isFiniteNumber(row[definition.metric])))
  if (!active.length) return <EmptyState text="Insufficient historical data for this view." />
  const values = active.flatMap((definition) => rows.map((row) => Number(row[definition.metric])).filter(Number.isFinite))
  let min = Math.min(...values), max = Math.max(...values)
  if (min === max) { min -= Math.abs(min || 1) * 0.1; max += Math.abs(max || 1) * 0.1 }
  const range = max - min || 1
  const width = 760, height = 250, left = 54, right = 18, top = 18, bottom = 36
  const x = (index) => left + (rows.length <= 1 ? (width - left - right) / 2 : index * (width - left - right) / (rows.length - 1))
  const y = (value) => top + (max - value) * (height - top - bottom) / range
  const ticks = [0, .25, .5, .75, 1]
  return <div className="trend-chart interactive-chart"><div className="chart-legend">{active.map((definition) => <span key={definition.metric}><i style={{ background: definition.color }} />{definition.label}</span>)}</div><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${active.map((item) => item.label).join(', ')} trend`} preserveAspectRatio="none" onMouseLeave={() => setHovered(null)}>{ticks.map((tick) => { const value = max - tick * range; const yy = top + tick * (height - top - bottom); return <g key={tick}><line x1={left} x2={width - right} y1={yy} y2={yy} className="grid-line" /><text x={left - 8} y={yy + 4} textAnchor="end">{formatAxis(value, active[0].type)}</text></g> })}{rows.map((row, index) => <text key={row.Year} x={x(index)} y={height - 10} textAnchor="middle">{row.Year}</text>)}{active.map((definition) => { const segments = chartSegments(rows, definition.metric, x, y); return <g key={definition.metric}>{segments.map((points, segmentIndex) => <polyline key={segmentIndex} points={points.map((point) => `${point.x},${point.y}`).join(' ')} fill="none" stroke={definition.color} strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" />)}{rows.map((row, index) => isFiniteNumber(row[definition.metric]) ? <circle className="chart-point" tabIndex="0" key={`${row.Year}-${definition.metric}`} cx={x(index)} cy={y(Number(row[definition.metric]))} r="5" fill={definition.color} stroke="#fff" strokeWidth="2" onMouseEnter={() => setHovered({ x: x(index), y: y(Number(row[definition.metric])), year: row.Year, label: definition.label, value: row[definition.metric], type: definition.type, color: definition.color })} onFocus={() => setHovered({ x: x(index), y: y(Number(row[definition.metric])), year: row.Year, label: definition.label, value: row[definition.metric], type: definition.type, color: definition.color })} onBlur={() => setHovered(null)} /> : null)}</g>})}</svg>{hovered && <ChartTooltip point={hovered} width={width} height={height} />}<p className="chart-help">Hover or focus a point to view the exact value. Gaps represent unavailable data.</p></div>
}

function ChartTooltip({ point, width, height }) { const unit = useContext(AmountUnitContext); return <div className="chart-tooltip" style={{ left: `${(point.x / width) * 100}%`, top: `${(point.y / height) * 100}%`, '--tooltip-color': point.color }}><small>{point.year}</small><strong>{point.label}</strong><span>{formatMetricValue(point.value, point.type, unit)}</span></div> }

function GroupedBarChart({ rows, series: definitions }) {
  const [hovered, setHovered] = useState(null)
  const active = definitions.filter((definition) => rows.some((row) => isFiniteNumber(row[definition.metric])))
  if (!active.length) return <EmptyState text="Insufficient historical data for this comparison." />
  const values = active.flatMap((definition) => rows.map((row) => Number(row[definition.metric])).filter(Number.isFinite))
  const min = Math.min(0, ...values), max = Math.max(0, ...values), range = max - min || 1
  const width = 760, height = 250, left = 54, right = 18, top = 18, bottom = 38
  const plotWidth = width - left - right, groupWidth = plotWidth / Math.max(rows.length, 1), barWidth = Math.min(22, groupWidth / Math.max(active.length + 1, 2))
  const y = (value) => top + (max - value) * (height - top - bottom) / range
  const zeroY = y(0)
  return <div className="trend-chart interactive-chart"><div className="chart-legend">{active.map((definition) => <span key={definition.metric}><i style={{ background: definition.color }} />{definition.label}</span>)}</div><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${active.map((item) => item.label).join(' and ')} bar comparison`} preserveAspectRatio="none" onMouseLeave={() => setHovered(null)}><line x1={left} x2={width - right} y1={zeroY} y2={zeroY} className="zero-line" />{rows.map((row, rowIndex) => <g key={row.Year}>{active.map((definition, seriesIndex) => { if (!isFiniteNumber(row[definition.metric])) return null; const value = Number(row[definition.metric]); const center = left + rowIndex * groupWidth + groupWidth / 2; const xx = center + (seriesIndex - (active.length - 1) / 2) * (barWidth + 3) - barWidth / 2; const yy = value >= 0 ? y(value) : zeroY; const barHeight = Math.max(1, Math.abs(y(value) - zeroY)); const point = { x: xx + barWidth / 2, y: yy, year: row.Year, label: definition.label, value, type: definition.type, color: definition.color }; return <rect className="chart-bar" tabIndex="0" key={definition.metric} x={xx} y={yy} width={barWidth} height={barHeight} rx="2" fill={definition.color} onMouseEnter={() => setHovered(point)} onFocus={() => setHovered(point)} onBlur={() => setHovered(null)} /> })}<text x={left + rowIndex * groupWidth + groupWidth / 2} y={height - 10} textAnchor="middle">{row.Year}</text></g>)}</svg>{hovered && <ChartTooltip point={hovered} width={width} height={height} />}<p className="chart-help">Hover or focus a bar to view the exact value.</p></div>
}

function HorizontalBars({ row, series: definitions }) {
  const unit = useContext(AmountUnitContext)
  const [hovered, setHovered] = useState(null)
  const active = definitions.filter((definition) => isFiniteNumber(row?.[definition.metric]))
  if (!active.length) return <EmptyState />
  const max = Math.max(...active.map((definition) => Math.abs(Number(row[definition.metric]))), 1)
  return <div className="horizontal-bars" onMouseLeave={() => setHovered(null)}>{active.map((definition) => { const value = Number(row[definition.metric]); return <div className="horizontal-bar-row" key={definition.metric}><div className="bar-label"><span>{definition.label}</span><strong>{formatMetricValue(value, definition.type, unit)}</strong></div><div className="bar-track"><button type="button" aria-label={`${definition.label}: ${formatMetricValue(value, definition.type, unit)}`} style={{ width: `${Math.max(2, Math.abs(value) / max * 100)}%`, background: definition.color }} onMouseEnter={() => setHovered(definition.metric)} onFocus={() => setHovered(definition.metric)} onBlur={() => setHovered(null)} />{hovered === definition.metric && <div className="bar-value-tooltip">Exact value: {formatMetricValue(value, definition.type, unit)}</div>}</div></div>})}<p className="chart-help">Bar lengths compare absolute magnitudes within this panel.</p></div>
}

function GrowthHeatmap({ rows, metrics }) {
  const available = metrics.filter((metric) => rows.some((row) => isFiniteNumber(row[metric])))
  if (!available.length) return <EmptyState text="No growth values are available for this group." />
  const maxAbs = Math.max(...available.flatMap((metric) => rows.map((row) => Math.abs(Number(row[metric]))).filter(Number.isFinite)), .01)
  const columns = { gridTemplateColumns: `minmax(116px, 1.5fr) repeat(${rows.length}, minmax(38px, 1fr))` }
  return <div className="growth-heatmap"><div className="heatmap-row heatmap-head" style={columns}><span>Metric</span>{rows.map((row) => <small key={row.Year}>{row.Year}</small>)}</div>{available.map((metric) => <div className="heatmap-row" style={columns} key={metric}><strong>{readableMetric(metric)}</strong>{rows.map((row) => { const value = row[metric]; if (!isFiniteNumber(value)) return <span className="heat-cell empty-cell" key={row.Year} title={`${row.Year}: Data unavailable`}>-</span>; const numeric = Number(value); const intensity = .15 + Math.min(Math.abs(numeric) / maxAbs, 1) * .75; const color = numeric >= 0 ? `rgba(15, 118, 110, ${intensity})` : `rgba(190, 45, 45, ${intensity})`; return <span className="heat-cell" key={row.Year} style={{ background: color }} tabIndex="0" data-tooltip={`${row.Year} - ${readableMetric(metric)}: ${formatMetricValue(numeric, 'percent')}`}>{numeric >= 0 ? '+' : ''}{(numeric * 100).toFixed(0)}%</span> })}</div>)}<div className="heatmap-scale"><span>Decline</span><i className="negative" /><i className="neutral" /><i className="positive" /><span>Growth</span></div><p className="chart-help">Hover or focus a cell to view the exact percentage.</p></div>
}
function chartSegments(rows, metric, x, y) { const segments = []; let current = []; rows.forEach((row, index) => { if (isFiniteNumber(row[metric])) current.push({ x: x(index), y: y(Number(row[metric])) }); else if (current.length) { segments.push(current); current = [] } }); if (current.length) segments.push(current); return segments }
function formatAxis(value, type) { if (type === 'percent') return `${(value * 100).toFixed(0)}%`; return Number(value).toLocaleString('en-IN', { maximumFractionDigits: 1 }) }
function financialInsights(rows) {
  if (rows.length < 2) return []
  const current = rows.at(-1), previous = rows.at(-2), results = []
  const change = (metric) => isFiniteNumber(current[metric]) && isFiniteNumber(previous[metric]) ? Number(current[metric]) - Number(previous[metric]) : null
  const revenue = change('Sales'), profit = change('Net profit'), ocf = change('Cash from Operating Activity')
  if (revenue !== null && profit !== null && Math.sign(revenue) !== Math.sign(profit)) results.push({ icon: 'compare_arrows', title: 'Revenue and profit diverged', text: `From ${previous.Year} to ${current.Year}, revenue ${revenue >= 0 ? 'increased' : 'declined'} while net profit ${profit >= 0 ? 'increased' : 'declined'}.` })
  else if (revenue !== null && profit !== null) results.push({ icon: 'monitoring', title: 'Revenue and profit moved together', text: `Both revenue and net profit ${revenue >= 0 ? 'increased' : 'declined'} in the latest period.` })
  if (isFiniteNumber(current.Borrowing_Growth) && isFiniteNumber(current.Asset_Growth) && Number(current.Borrowing_Growth) > Number(current.Asset_Growth)) results.push({ icon: 'account_balance', title: 'Borrowings grew faster than assets', text: `Latest borrowing growth was ${formatMetricValue(current.Borrowing_Growth, 'percent')} versus asset growth of ${formatMetricValue(current.Asset_Growth, 'percent')}.` })
  if (revenue !== null && revenue > 0 && ocf !== null && ocf < 0) results.push({ icon: 'waterfall_chart', title: 'Cash generation moved against revenue', text: 'Revenue increased while operating cash flow declined in the latest period.' })
  if (isFiniteNumber(current.Receivable_Growth) && isFiniteNumber(current.Revenue_Growth) && Number(current.Receivable_Growth) > Number(current.Revenue_Growth)) results.push({ icon: 'receipt_long', title: 'Receivables outpaced revenue', text: `Receivable growth was ${formatMetricValue(current.Receivable_Growth, 'percent')} compared with revenue growth of ${formatMetricValue(current.Revenue_Growth, 'percent')}.` })
  if (change('Profit_Margin') !== null) results.push({ icon: 'percent', title: `Profit margin ${change('Profit_Margin') >= 0 ? 'improved' : 'declined'}`, text: `Latest profit margin was ${formatMetricValue(current.Profit_Margin, 'percent')}, a ${formatDelta(current.Profit_Margin, previous.Profit_Margin, 'percent')} movement.` })
  return results.slice(0, 4)
}

function RulesPage({ data }) {
  const [query, setQuery] = useState('')
  const rows = filterRows(data.rows || [], query)
  return <><PageTitle title="Rule Engine" subtitle="Authoritative rule execution with understandable failure evidence." /><StatGrid stats={[['Checks attempted', data.summary.total], ['Passed', data.summary.passed], ['Failed', data.summary.failed], ['Cannot evaluate', data.summary.skipped], ['Errors', data.summary.errors]]} /><RiskScores rows={data.risk_scores || []} /><div className="action-bar"><Search value={query} onChange={setQuery} placeholder="Search rules, evidence, severity..." /></div><Findings rows={rows} columns={['Year', 'Rule ID', 'Rule Name', 'Severity', 'Status', 'Message', 'Recommendation']} statusKey="Status" /></>
}



function TrailPage({ data }) {
  return <><PageTitle title="Audit Trail" subtitle="Processing history for this analysis. Opening this page does not rerun the pipeline." /><div className="timeline">{(data.events || []).map((event) => <div className="timeline-row" key={event.id}><Icon>task_alt</Icon><div><strong>{event.stage}</strong><p>{event.message}</p><small>{formatDate(event.created_at)}</small></div></div>)}</div></>
}

function ReportPage({ data, analysisId }) {
  const o = data.overview || {}
  return <><PageTitle title="Audit Report" subtitle="Detailed report generated from actual client data, rules, ML, XAI, risk score, and recommendations." /><StatGrid stats={[['Client', o.company], ['Years', o.years?.join(', ')], ['Rule Failures', o.rule_failures], ['ML Anomalies', o.ml_anomalies], ['Avg Risk', o.average_risk_score == null ? 'Unavailable' : `${o.average_risk_score}%`], ['Rule Coverage', `${o.rule_coverage_percent ?? 'N/A'}%`], ['ML Status', formatStatus(o.ml_status)]]} /><section className="finding-card"><h3>Analysis coverage and limitations</h3><p>Risk scores reflect evaluated checks only. A risk classification requires at least 50% rule coverage; this is an operational guard, not a confidence estimate. ML coverage is the percentage of features observed before imputation.</p>{(data.limitations || []).map((item) => <p key={item}>{item}</p>)}</section><a className="primary-button report-download" href={`${API}/analysis/${analysisId}/audit-report.pdf`}><Icon>picture_as_pdf</Icon>Download Detailed PDF</a><RiskScores rows={data.risk_scores || []} /><Findings rows={data.rule_findings || []} columns={['Year', 'Rule ID', 'Rule Name', 'Severity', 'Message']} /></>
}

function PageTitle({ title, subtitle }) { return <div className="page-title"><p className="eyebrow">Financial intelligence / {title}</p><h1>{title}</h1><p>{subtitle}</p></div> }
function Empty({ title, text }) { return <div className="empty"><Icon>hourglass_top</Icon><h1>{title}</h1><p>{text}</p></div> }
function Search({ value, onChange, placeholder = 'Search current client data...' }) { return <div className="search"><Icon>search</Icon><input aria-label={placeholder} value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} /></div> }
function StatGrid({ stats }) { return <section className="stat-grid">{stats.map(([label, value]) => <div className="stat" key={label}><span>{label}</span><strong>{value ?? 'N/A'}</strong></div>)}</section> }
function Badge({ value }) { return <span className={`badge ${String(value || '').toLowerCase()}`}>{value === 'skipped' ? 'Cannot evaluate' : value || 'N/A'}</span> }
function DataTable({ columns, rows }) { return <div className="table-wrap"><table><thead><tr>{columns.map((c) => <th key={c}>{c}</th>)}</tr></thead><tbody>{rows.length === 0 && <tr><td colSpan={columns.length} className="table-empty">No matching records to display.</td></tr>}{rows.map((row, i) => <tr key={i}>{columns.map((c) => <td key={c}>{formatValue(row[c])}</td>)}</tr>)}</tbody></table></div> }
function Findings({ rows, columns, statusKey }) {
  const { analysisId } = useParams()
  return <div className="table-wrap"><table><thead><tr>{columns.map(c => <th key={c}>{c}</th>)}<th>Review</th></tr></thead><tbody>
    {rows.length === 0 && <tr><td colSpan={columns.length + 1} className="table-empty">No matching records to display.</td></tr>}
    {rows.map((row,i) => <tr key={i}>{columns.map(c => <td key={c}>{c === statusKey || c === 'Severity' ? <Badge value={row[c]}/> : formatValue(row[c])}</td>)}<td><Link className="text-button" to={'/app/reviews/' + analysisId + '?finding=' + encodeURIComponent('rule:' + row.Year + ':' + row['Rule ID'])}>View evidence →</Link></td></tr>)}
  </tbody></table></div>
}

function RiskScores({ rows }) { if (!rows?.length) return null; return <section className="risk-row">{rows.map((row) => <div className="risk-card" key={row.Year}><span>{row.Year}</span><strong>{row['Risk Score'] == null ? 'Unavailable' : `${row['Risk Score']}%`}</strong><Badge value={row['Risk Level']} /><small>{row['Failed Rules']} failed rules</small><small>{row['Coverage Percent'] ?? 'N/A'}% coverage | {row['Skipped Rules']} skipped</small></div>)}</section> }

async function fetchJson(url) { return api(url) }

function pageEndpoint(page) { return page === 'audit-report' ? 'report' : page === 'rules' ? 'rules' : page }
function filterRows(rows, query) { if (!query) return rows; const q = query.toLowerCase(); return rows.filter((row) => Object.values(row).some((v) => String(v ?? '').toLowerCase().includes(q))) }
function yearRange(rows) { const years = rows.map((r) => Number(r.Year)).filter(Boolean); return years.length ? `${Math.min(...years)} - ${Math.max(...years)}` : 'N/A' }
function formatValue(value) { if (value === null || value === undefined || value === '') return 'N/A'; if (typeof value === 'number') return Number.isInteger(value) ? value : value.toLocaleString('en-IN', { maximumFractionDigits: 4 }); if (typeof value === 'object') return Object.entries(value).map(([k, v]) => `${k}: ${formatValue(v)}`).join(', '); return value }
function formatDate(value) { return value ? new Date(value).toLocaleString() : '' }
function formatStatus(value) { return value ? value.replaceAll('_', ' ') : 'N/A' }

export default App





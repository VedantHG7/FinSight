import Icon from '../Icon'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import logo from '../assets/finsight-logo.jpg'

const capabilities = [
  ['analytics', '01', 'See the full financial picture', 'Explore revenue, profitability, cash flow, and multi-year trends in one connected analytics workspace.'],
  ['rule', '02', 'Review the evidence', 'Evaluate financial data against audit rules. See passed, failed, and skipped checks with supporting explanations.'],
  ['query_stats', '03', 'Surface unusual patterns', 'Use machine learning to identify company-year anomalies, with feature coverage and limitations in view.'],
  ['description', '04', 'Move from insight to action', 'Bring rule findings, anomaly evidence, and recommendations together in a downloadable audit report.'],
]
const faqs = [
  ['What can I upload?', 'Upload an Excel workbook (.xlsx or .xls) for one company. The workbook should contain a Data Sheet with reporting years and financial-statement sections.'],
  ['How are findings explained?', 'Each analysis combines available rule evidence, machine-learning signals, and audit recommendations. Coverage and missing data are shown alongside the findings.'],
  ['Can I download a report?', 'Yes. Open the Audit Report in your workspace to download a PDF with findings, risk scores, recommendations, and analysis limitations.'],
  ['Do anomaly signals confirm financial misconduct?', 'No. Anomalies identify patterns for further review. Findings support professional judgment and should be assessed alongside the underlying records.'],
]

export default function Onboarding() {
  const [menuOpen, setMenuOpen] = useState(false)
  return <div className="site">
    <a className="skip-link" href="#site-main">Skip to content</a>
    <header className="site-nav"><div className="site-container nav-inner">
      <Link className="brand" to="/" aria-label="FinSight home"><img src={logo} alt="" /><span>FinSight<span className="brand-dot">.</span></span></Link>
      <nav className={menuOpen ? 'site-links open' : 'site-links'} aria-label="Main navigation">{[['#solutions', 'Capabilities'], ['#how-it-works', 'How it works'], ['#questions', 'Questions']].map(([href, label]) => <a key={href} href={href} onClick={() => setMenuOpen(false)}>{label}</a>)}</nav>
      <Link className="primary-button slim" to="/app">Open workspace <Icon>arrow_forward</Icon></Link>
      <button className="site-menu" onClick={() => setMenuOpen(!menuOpen)} aria-expanded={menuOpen} aria-label="Toggle navigation"><Icon>{menuOpen ? 'close' : 'menu'}</Icon></button>
    </div></header>
    <main id="site-main">
      <section className="site-container landing-hero">
        <div className="hero-copy"><p className="eyebrow"><span className="status-dot" /> Financial clarity. In focus.</p><h1>Every number tells a story.<br /><em>See the whole picture.</em></h1><p className="lede">Connect financial analytics, risk signals, and explainable findings. Give your next audit a clearer starting point.</p><div className="hero-actions"><Link className="primary-button slim" to="/app">Start an analysis <Icon>arrow_forward</Icon></Link><a className="text-button" href="#how-it-works">Explore the workflow <span aria-hidden="true">↗</span></a></div><div className="hero-notes"><span><Icon>table_view</Icon>Excel to insight</span><span><Icon>fact_check</Icon>Evidence in context</span></div></div>
        <div className="product-preview" aria-label="Illustrative financial analytics preview">
          <div className="preview-top"><span><span className="status-dot" /> Financial overview</span><span className="preview-tag">Illustrative data</span></div>
          <div className="preview-heading"><div><p className="eyebrow">Performance at a glance</p><h2>A clearer perspective.</h2></div><Icon>insights</Icon></div>
          <div className="preview-metrics"><div><small>Revenue</small><strong>₹124.8m</strong><span>+12.4% year over year</span></div><div><small>Operating margin</small><strong>24.6%</strong><span>Five-year perspective</span></div></div>
          <div className="preview-chart"><div><strong>Performance trend</strong><span>Revenue · Operating cash flow</span></div><svg viewBox="0 0 480 180" role="img" aria-label="Illustrative revenue and cash flow trends"><defs><linearGradient id="preview-fill" x1="0" y1="0" x2="0" y2="1"><stop stopColor="#0f766e" stopOpacity=".18"/><stop offset="1" stopColor="#0f766e" stopOpacity="0"/></linearGradient></defs>{[35, 80, 125, 170].map(y => <line key={y} x1="0" x2="480" y1={y} y2={y} stroke="#e4ebef"/>)}<path d="M0 145 C60 145 70 105 120 110 S190 120 240 80 S320 100 360 55 S430 60 480 15 L480 180 L0 180Z" fill="url(#preview-fill)"/><path d="M0 145 C60 145 70 105 120 110 S190 120 240 80 S320 100 360 55 S430 60 480 15" fill="none" stroke="#0f766e" strokeWidth="3"/><path d="M0 165 C60 160 75 140 120 145 S200 125 240 130 S320 90 360 95 S425 75 480 70" fill="none" stroke="#6887a6" strokeWidth="2.5" strokeDasharray="6 5"/></svg><div className="preview-years"><span>FY 2021</span><span>FY 2022</span><span>FY 2023</span><span>FY 2024</span><span>FY 2025</span></div></div>
          <div className="preview-note"><Icon>fact_check</Icon><div><strong>Go beyond the headline numbers</strong><p>Trends, evidence, and coverage in one place.</p></div><Icon>arrow_forward</Icon></div>
        </div>
      </section>
      <div className="capability-strip"><div className="site-container"><span>ONE CONNECTED WORKSPACE</span><strong>Financial analytics</strong><i/><strong>Rule validation</strong><i/><strong>Anomaly detection</strong><i/><strong>Audit reporting</strong></div></div>
      <section id="solutions" className="site-container landing-section"><div className="landing-section-heading"><div><p className="eyebrow">Built for the detail</p><h2>From financial complexity<br />to informed decisions.</h2></div><p>Follow the numbers, understand the signals, and keep the supporting evidence close.</p></div><div className="capability-grid">{capabilities.map(([icon, num, title, text]) => <article key={num} className="capability-card"><div className="capability-top"><Icon>{icon}</Icon><small>{num}</small></div><h3>{title}</h3><p>{text}</p></article>)}</div></section>
      <section id="how-it-works" className="workflow-section"><div className="site-container landing-section"><p className="eyebrow">A considered workflow</p><h2>One workbook. A connected analysis.</h2><div className="workflow-grid">{[['01', 'Bring your data', 'Upload an Excel workbook with the company’s financial statements and reporting years.'], ['02', 'Build the picture', 'Explore validated metrics, rule outcomes, and machine-learning signals with clear coverage indicators.'], ['03', 'Review and report', 'Investigate explanations, trace the analysis history, and export your consolidated audit report.']].map(([num,title,text]) => <article key={num}><span>{num}</span><h3>{title}</h3><p>{text}</p></article>)}</div></div></section>
      <section id="questions" className="site-container landing-section faq-section"><div><p className="eyebrow">Before you begin</p><h2>A little more clarity.</h2><p className="lede">Understand your data, your workflow, and what the findings mean.</p></div><div className="faq-list">{faqs.map(([q,a]) => <details key={q}><summary>{q}<span aria-hidden="true">+</span></summary><p>{a}</p></details>)}</div></section>
      <section className="site-container"><div className="landing-cta"><div><p className="eyebrow">Your next step</p><h2>Put your financial data<br />into perspective.</h2><p>Your next analysis starts with a workbook.</p></div><Link className="primary-button slim" to="/app">Open your workspace <Icon>arrow_forward</Icon></Link></div></section>
    </main>
    <footer className="site-container site-footer"><Link className="brand" to="/"><img src={logo} alt=""/>FinSight</Link><p>Financial analytics & audit intelligence</p><a href="#questions">Questions & answers ↗</a></footer>
  </div>
}

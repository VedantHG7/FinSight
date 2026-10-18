// Explain the implemented checks, without inventing a business cause or missing evidence.
const checks = {
 ocf_reconciliation_proxy: ['Operating cash flow differs from net profit plus depreciation and explicitly supplied other operating cash adjustments beyond the tolerance.', 'Verify that Other Operating Cash Adjustments includes every remaining signed adjustment, including working-capital movements, and reconcile the cash-flow statement.'],
 required_columns: ['The source data is missing one or more required financial columns.', 'Supply the missing source columns shown in the evidence. Generated empty columns do not satisfy this check.'],
 accounting_equation: ['Assets and liabilities do not reconcile within the configured tolerance.', 'Compare the balance-sheet totals and confirm whether equity is included in the supplied liabilities total.'],
 negative_equity: ['Equity share capital plus reserves is below zero.', 'Reconcile accumulated losses and the equity schedule.'],
 negative_screen: ['At least one screened value is negative.', 'Check the sign convention and source balance; a negative value can be valid for some accounting items.'],
 negative_value: ['The tested metric is below zero.', 'Check the source value and the reason for the negative balance or cash flow.'],
 config_max: ['The tested ratio is above its configured upper limit.', 'Recalculate the ratio from its numerator and denominator and assess whether this limit is suitable for the company.'],
 config_min: ['The tested ratio is below its configured lower limit.', 'Recalculate the ratio and verify the configured lower limit.'],
 growth_gap: ['The first tested growth measure is positive while the second is negative.', 'Compare the two movements and reconcile timing, working-capital and classification differences.'],
 relationship_adverse: ['The first tested metric is positive while the second is negative.', 'Reconcile the two source measures; their opposite signs trigger the check but do not establish the cause.'],
 cash_delta_tieout: ['The change in cash from the previous period differs from reported net cash flow by more than the tolerance.', 'Reconcile opening cash + net cash flow to closing cash. Check exchange-rate effects, scope changes and the definition of cash equivalents.'],
 reserve_rollforward: ['The change in reserves differs from net profit less dividends by more than the tolerance.', 'Reconcile opening reserves + profit − dividends to closing reserves, including other comprehensive income, transfers and other equity movements.'],
 financing_plausibility: ['Reported financing cash flow differs materially from the change in borrowings less dividends under the implemented proxy.', 'Reconcile financing flows to debt movements and dividends. Include equity transactions, leases and non-cash debt movements omitted by this proxy.'],
 dividend_reserves: ['Dividends exceed reserves, with negative reserves treated as zero for this check.', 'Verify the dividend period, reserves balance and supporting equity movements. This screening check is not a legal distribution test.'],
 ocf_below_profit: ['Operating cash flow is lower than reported net profit.', 'Reconcile profit to cash flow, including receivables, inventory, payables and non-cash adjustments.'],
 cash_ocf_divergence: ['Cash declined despite positive operating cash flow.', 'Inspect investing and financing outflows to explain how total cash declined.'],
 declining_trend: ['The available history is strictly decreasing over the configured consecutive-year window.', 'Inspect each period in the window and confirm whether the trend reflects a business change or a data issue.'],
 increasing_trend: ['The available history is strictly increasing over the configured consecutive-year window.', 'Inspect each period and the underlying drivers; an increase is not automatically an error.'],
 sustained_negative: ['Every tested value in the configured history window is negative.', 'Inspect the source series and determine why the negative condition persisted.'],
 missing_required: ['A required company or reporting-year value is missing.', 'Correct the workbook identification fields.'],
 numeric_fields: ['A field expected to be numeric could not be interpreted as a number.', 'Check source formatting and non-numeric placeholders.'],
 year_date_match: ['The reporting year does not match the supplied report-date text.', 'Verify that the workbook uses consistent reporting periods.'],
}
const statistical = ['feature_zscore','outlier','feature_volatility','common_size_shift','margin_instability','expense_spike','interest_reasonableness','cash_flow_composition']
export function explainRule(rule) {
 const info = checks[rule.Formula] || (statistical.includes(rule.Formula) ? ['The absolute robust deviation score exceeded the configured limit against the available same-year observations.', 'Check the comparison population and underlying metric. A statistical outlier is not proof of an error.'] : null)
 return { condition: info?.[0] || rule.Message || 'The saved rule result is Failed; its detailed evaluation condition was not recorded.',
   action: info?.[1] || rule.Recommendation || 'Inspect the source workbook and supporting schedule.',
   values: Object.entries(rule.Observed || {}),
   limitation: ['cash_delta_tieout','reserve_rollforward','financing_plausibility'].includes(rule.Formula) ? 'This reconciliation is a screening proxy. Legitimate movements outside the supplied inputs can explain a difference.' : 'This is a review signal, not a confirmed misstatement. A business cause must be established from supporting evidence.' }
}

export function failedRules(rows = [], year = '', severity = '', query = '') {
 const rank = {Critical:0,High:1,Medium:2,Low:3}
 return rows.filter(r => r.Status === 'fail' && (!year || String(r.Year) === year) && (!severity || r.Severity === severity) && `${r['Rule ID']} ${r['Rule Name']} ${r.Message}`.toLowerCase().includes(query.toLowerCase()))
 .sort((a,b) => (rank[a.Severity] ?? 4) - (rank[b.Severity] ?? 4) || b.Year - a.Year || String(a['Rule ID']).localeCompare(String(b['Rule ID'])))
}

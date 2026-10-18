// The user's workbook convention is INR crore. Explicit source declarations win.
export function reportingUnit(source, override = '') {
  return (override || (source?.status === 'detected' ? source.label : 'INR crore')).replace('INR', '₹')
}

export function metricType(metric) {
  if (/^(Company|Year|Report Date)$/.test(metric)) return 'number'
  if (/^(EPS|Earnings per share)|Face value|PRICE:/i.test(metric)) return 'perShare'
  if (/shares/i.test(metric)) return 'number'
  if (/^(dio|dso|dpo|ccc)$/i.test(metric) || /days/i.test(metric)) return 'days'
  if (/Growth|Margin|ROA|ROE|CAGR|effective_tax_rate/.test(metric)) return 'percent'
  if (/Ratio|Coverage|to_Equity|to_Debt|Asset_Utilization|turnover/i.test(metric)) return 'ratio'
  if (/Sales|Revenue|profit|Assets|Liabilities|Borrowings|Cash|Expenses|Reserves|Receivables|Inventory|Volatility|Capital|Income|Interest|Depreciation|Cost|Investments|CWIP|Power and Fuel|Selling and admin|Other Mfr/i.test(metric)) return 'amount'
  return 'number'
}

export function metricUnit(metric, amountUnit) {
  return {amount: amountUnit, percent: '%', ratio: '×', perShare: '₹ / share', days: 'days', number: 'source units'}[metricType(metric)]
}

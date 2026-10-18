# Rule reliability changes

New analyses run 40 checks. LED-001 duplicates BS-001 and TR-002 duplicates
IS-010; their modules are retained for historical reference but no longer loaded.
Historical JSON/PDF reports and review decisions are unchanged. Restart the API
and worker and upload a new analysis to apply these changes.

## Evaluation and coverage

The persisted status `skipped` now displays as **Cannot evaluate** in the rule
table. Each new skipped result carries a reason. Missing source metrics, missing
thresholds, insufficient same-year comparisons (fewer than three observations),
or zero median absolute deviation never count as passes. Skipped checks remain
outside the risk denominator. The existing 50% coverage policy is unchanged;
more honest abstention can make a formerly available score unavailable.

RAT-007 and RAT-008 have no approved threshold in the current configuration.
They abstain rather than inventing a threshold or producing an execution error.
Peer checks still require same-year comparison data; a normal single-company
upload does not provide that population. No historical data is relabeled as peers.

Trends require three consecutive years, without missing values, and strictly
increasing/decreasing values. Flat trends pass directional tests. Reconciliations
require the immediately preceding year. Growth does not bridge missing years.

## Completed checks and source evidence

DV-012 checks the actual source columns against REQUIRED_COLUMNS, before empty
columns and derived features are added. DV-007 retains evidence of invalid numeric
source values before coercion. Reporting dates survive preprocessing for DV-018.
Duplicate company-year input records are rejected.

CF-006 reconciles operating cash flow against net profit + depreciation +
`Other Operating Cash Adjustments`. This new source field must explicitly contain
the complete signed sum of all remaining adjustments, including working capital,
other non-cash items, and relevant classification adjustments. Missing adjustments
cause abstention, not an assumption of zero. A difference greater than the existing
0.01 tolerance is flagged. This verifies the supplied bridge, not its completeness.

CF-009 now compares operating cash flow directly with net income, matching its
purpose, instead of testing an unrelated operating-cash-to-sales peer ratio.

## Rule-only feature definitions

Saved ML feature formulas are preserved. Additional rule features use:

- Equity_Ratio: (share capital + reserves) / total assets.
- Interest_Coverage_Ratio: (profit before tax + interest) / interest.
- Asset_Utilization_Ratio: sales / closing total assets.
- effective_tax_rate: (profit before tax - net profit) / profit before tax.
- Gross_Profit_Margin: reported gross profit / sales; otherwise
  (sales - explicitly supplied Cost of Goods Sold) / sales.
- inventory_turnover: Cost of Goods Sold / closing inventory; dio is 365 / turnover.
- receivables_turnover: Credit Sales / closing receivables; dso is 365 / turnover.

Directly supplied rule ratios are preserved. Missing COGS or credit sales is not
replaced with total expenses or total sales. Zero denominators remain unavailable.
Turnover definitions use closing balances, not averages. Financial units, source
definitions, and threshold calibration still require appropriate review.

## Verification

Regression coverage lives in backend/tests/test_rule_reliability.py and the
existing rule explanation tests. It covers true failures, boundaries, unavailable
comparisons, source validation, dates, derived features and missing years.

from audit_engine.models import RuleSpec, Severity
from audit_engine.rules.factory import build_rule

RULE = build_rule(RuleSpec(
    rule_id='CF-006',
    name='Operating cash flow reconciliation',
    group='Handbook Rules',
    category='cross_statement',
    validation_logic='ocf_reconciliation_proxy',
    severity=Severity.HIGH,
    required_metrics=('Net profit', 'Depreciation', 'Cash from Operating Activity', 'Other Operating Cash Adjustments'),
    description='Reconciles operating cash flow using an explicitly supplied signed total of all adjustments other than depreciation, including working capital and other non-cash or classification adjustments.',
    business_purpose='Focuses audit review on a material inconsistency, adverse condition, or statistically unusual relationship.',
    formula='ocf_reconciliation_proxy',
    threshold='Net profit + depreciation + other operating cash adjustments must reconcile to operating cash flow within tolerance',
    recommendation='Investigate the underlying drivers and obtain supporting evidence before relying on the reported balance.',
    risk_impact='Potential financial-statement reliability, liquidity, solvency, or earnings-quality risk.',
))

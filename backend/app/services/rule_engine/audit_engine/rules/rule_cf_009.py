from audit_engine.models import RuleSpec, Severity
from audit_engine.rules.factory import build_rule

RULE = build_rule(RuleSpec(
    rule_id='CF-009',
    name='Operating cash flow below net income',
    group='Handbook Rules',
    category='cross_statement',
    validation_logic='ocf_below_profit',
    severity=Severity.HIGH,
    required_metrics=('Cash from Operating Activity', 'Net profit'),
    description='Tests cash flow versus net income divergence using only supplied financial-statement metrics.',
    business_purpose='Focuses audit review on a material inconsistency, adverse condition, or statistically unusual relationship.',
    formula='ocf_below_profit',
    threshold='Operating cash flow is below net profit; review cash conversion and non-cash adjustments',
    recommendation='Investigate the underlying drivers and obtain supporting evidence before relying on the reported balance.',
    risk_impact='Potential financial-statement reliability, liquidity, solvency, or earnings-quality risk.',
))

from audit_engine.models import RuleSpec, Severity
from audit_engine.rules.factory import build_rule

RULE = build_rule(RuleSpec(
    rule_id='TR-006',
    name='Common-size statement analysis',
    group='Handbook Rules',
    category='trend',
    validation_logic='common_size_shift',
    severity=Severity.MEDIUM,
    required_metrics=('Expense_Ratio',),
    description='Tests common-size statement analysis using only supplied financial-statement metrics.',
    business_purpose='Focuses audit review on a material inconsistency, adverse condition, or statistically unusual relationship.',
    formula='common_size_shift',
    threshold='Robust z-score against same-year peer population (configurable)',
    recommendation='Investigate the underlying drivers and obtain supporting evidence before relying on the reported balance.',
    risk_impact='Potential financial-statement reliability, liquidity, solvency, or earnings-quality risk.',
))

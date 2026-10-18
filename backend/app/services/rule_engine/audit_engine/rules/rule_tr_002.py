from audit_engine.models import RuleSpec, Severity
from audit_engine.rules.factory import build_rule

RULE = build_rule(RuleSpec(
    rule_id='TR-002',
    name='Year-over-year expense variance',
    group='Handbook Rules',
    category='trend',
    validation_logic='expense_spike',
    severity=Severity.MEDIUM,
    required_metrics=('Total Expenses',),
    description='Tests year-over-year expense variance using only supplied financial-statement metrics.',
    business_purpose='Focuses audit review on a material inconsistency, adverse condition, or statistically unusual relationship.',
    formula='expense_spike',
    threshold='Robust z-score against same-year peer population (configurable)',
    recommendation='Investigate the underlying drivers and obtain supporting evidence before relying on the reported balance.',
    risk_impact='Potential financial-statement reliability, liquidity, solvency, or earnings-quality risk.',
))

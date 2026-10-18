from audit_engine.models import RuleSpec, Severity
from audit_engine.rules.factory import build_rule

RULE = build_rule(RuleSpec(
    rule_id='IS-011',
    name='Revenue versus operating cash flow correlation',
    group='Handbook Rules',
    category='cross_statement',
    validation_logic='growth_gap',
    severity=Severity.HIGH,
    required_metrics=('Revenue_Growth', 'Operating_CF_Growth'),
    description='Tests revenue versus operating cash flow correlation using only supplied financial-statement metrics.',
    business_purpose='Focuses audit review on a material inconsistency, adverse condition, or statistically unusual relationship.',
    formula='growth_gap',
    threshold='No arbitrary threshold; logical condition or configurable tolerance',
    recommendation='Investigate the underlying drivers and obtain supporting evidence before relying on the reported balance.',
    risk_impact='Potential financial-statement reliability, liquidity, solvency, or earnings-quality risk.',
))

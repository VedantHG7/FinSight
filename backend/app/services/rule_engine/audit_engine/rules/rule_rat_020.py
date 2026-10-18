from audit_engine.models import RuleSpec, Severity
from audit_engine.rules.factory import build_rule

RULE = build_rule(RuleSpec(
    rule_id='RAT-020',
    name='Days sales outstanding trend',
    group='Handbook Rules',
    category='trend',
    validation_logic='increasing_trend',
    severity=Severity.MEDIUM,
    required_metrics=('dso',),
    description='Tests days sales outstanding trend using only supplied financial-statement metrics.',
    business_purpose='Focuses audit review on a material inconsistency, adverse condition, or statistically unusual relationship.',
    formula='increasing_trend',
    threshold='No arbitrary threshold; logical condition or configurable tolerance',
    recommendation='Investigate the underlying drivers and obtain supporting evidence before relying on the reported balance.',
    risk_impact='Potential financial-statement reliability, liquidity, solvency, or earnings-quality risk.',
))

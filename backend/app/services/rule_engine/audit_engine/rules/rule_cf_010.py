from audit_engine.models import RuleSpec, Severity
from audit_engine.rules.factory import build_rule

RULE = build_rule(RuleSpec(
    rule_id='CF-010',
    name='Dividend versus reserves',
    group='Handbook Rules',
    category='solvency',
    validation_logic='dividend_reserves',
    severity=Severity.HIGH,
    required_metrics=('Dividend Amount', 'Reserves'),
    description='Tests dividend versus reserves using only supplied financial-statement metrics.',
    business_purpose='Focuses audit review on a material inconsistency, adverse condition, or statistically unusual relationship.',
    formula='dividend_reserves',
    threshold='No arbitrary threshold; logical condition or configurable tolerance',
    recommendation='Investigate the underlying drivers and obtain supporting evidence before relying on the reported balance.',
    risk_impact='Potential financial-statement reliability, liquidity, solvency, or earnings-quality risk.',
))

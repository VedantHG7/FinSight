from audit_engine.models import RuleSpec, Severity
from audit_engine.rules.factory import build_rule

RULE = build_rule(RuleSpec(
    rule_id='BS-009',
    name='Negative total equity',
    group='Handbook Rules',
    category='solvency',
    validation_logic='negative_equity',
    severity=Severity.HIGH,
    required_metrics=('Equity Share Capital', 'Reserves'),
    description='Tests negative total equity using only supplied financial-statement metrics.',
    business_purpose='Focuses audit review on a material inconsistency, adverse condition, or statistically unusual relationship.',
    formula='negative_equity',
    threshold='No arbitrary threshold; logical condition or configurable tolerance',
    recommendation='Investigate the underlying drivers and obtain supporting evidence before relying on the reported balance.',
    risk_impact='Potential financial-statement reliability, liquidity, solvency, or earnings-quality risk.',
))

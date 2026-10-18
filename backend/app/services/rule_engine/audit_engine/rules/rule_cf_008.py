from audit_engine.models import RuleSpec, Severity
from audit_engine.rules.factory import build_rule

RULE = build_rule(RuleSpec(
    rule_id='CF-008',
    name='Sustained negative operating cash flow',
    group='Handbook Rules',
    category='trend',
    validation_logic='sustained_negative',
    severity=Severity.HIGH,
    required_metrics=('Cash from Operating Activity',),
    description='Tests sustained negative operating cash flow using only supplied financial-statement metrics.',
    business_purpose='Focuses audit review on a material inconsistency, adverse condition, or statistically unusual relationship.',
    formula='sustained_negative',
    threshold='No arbitrary threshold; logical condition or configurable tolerance',
    recommendation='Investigate the underlying drivers and obtain supporting evidence before relying on the reported balance.',
    risk_impact='Potential financial-statement reliability, liquidity, solvency, or earnings-quality risk.',
))

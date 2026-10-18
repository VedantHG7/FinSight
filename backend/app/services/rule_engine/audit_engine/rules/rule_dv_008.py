from audit_engine.models import RuleSpec, Severity
from audit_engine.rules.factory import build_rule

RULE = build_rule(RuleSpec(
    rule_id='DV-008',
    name='Unexpected negative cash or inventory',
    group='Handbook Rules',
    category='data_quality',
    validation_logic='negative_screen',
    severity=Severity.MEDIUM,
    required_metrics=('Cash & Bank', 'Inventory'),
    description='Tests unexpected negative cash or inventory using only supplied financial-statement metrics.',
    business_purpose='Focuses audit review on a material inconsistency, adverse condition, or statistically unusual relationship.',
    formula='negative_screen',
    threshold='No arbitrary threshold; logical condition or configurable tolerance',
    recommendation='Investigate the underlying drivers and obtain supporting evidence before relying on the reported balance.',
    risk_impact='Potential financial-statement reliability, liquidity, solvency, or earnings-quality risk.',
))

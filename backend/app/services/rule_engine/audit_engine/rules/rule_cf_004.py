from audit_engine.models import RuleSpec, Severity
from audit_engine.rules.factory import build_rule

RULE = build_rule(RuleSpec(
    rule_id='CF-004',
    name='Financing activity plausibility',
    group='Handbook Rules',
    category='cross_statement',
    validation_logic='financing_plausibility',
    severity=Severity.HIGH,
    required_metrics=('Borrowings', 'Dividend Amount', 'Cash from Financing Activity'),
    description='Tests financing activity plausibility using only supplied financial-statement metrics.',
    business_purpose='Focuses audit review on a material inconsistency, adverse condition, or statistically unusual relationship.',
    formula='financing_plausibility',
    threshold='No arbitrary threshold; logical condition or configurable tolerance',
    recommendation='Investigate the underlying drivers and obtain supporting evidence before relying on the reported balance.',
    risk_impact='Potential financial-statement reliability, liquidity, solvency, or earnings-quality risk.',
))

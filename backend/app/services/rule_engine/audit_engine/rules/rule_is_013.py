from audit_engine.models import RuleSpec, Severity
from audit_engine.rules.factory import build_rule

RULE = build_rule(RuleSpec(
    rule_id='IS-013',
    name='Net income to reserve movement plausibility',
    group='Handbook Rules',
    category='cross_statement',
    validation_logic='reserve_rollforward',
    severity=Severity.CRITICAL,
    required_metrics=('Net profit', 'Dividend Amount', 'Reserves'),
    description='Tests net income to reserve movement plausibility using only supplied financial-statement metrics.',
    business_purpose='Focuses audit review on a material inconsistency, adverse condition, or statistically unusual relationship.',
    formula='reserve_rollforward',
    threshold='No arbitrary threshold; logical condition or configurable tolerance',
    recommendation='Investigate the underlying drivers and obtain supporting evidence before relying on the reported balance.',
    risk_impact='Potential financial-statement reliability, liquidity, solvency, or earnings-quality risk.',
))

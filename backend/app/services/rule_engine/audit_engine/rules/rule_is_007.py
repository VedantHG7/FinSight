from audit_engine.models import RuleSpec, Severity
from audit_engine.rules.factory import build_rule

RULE = build_rule(RuleSpec(
    rule_id='IS-007',
    name='Interest expense reasonableness',
    group='Handbook Rules',
    category='analytical',
    validation_logic='interest_reasonableness',
    severity=Severity.MEDIUM,
    required_metrics=('Interest', 'Borrowings'),
    description='Tests interest expense reasonableness using only supplied financial-statement metrics.',
    business_purpose='Focuses audit review on a material inconsistency, adverse condition, or statistically unusual relationship.',
    formula='interest_reasonableness',
    threshold='Robust z-score against same-year peer population (configurable)',
    recommendation='Investigate the underlying drivers and obtain supporting evidence before relying on the reported balance.',
    risk_impact='Potential financial-statement reliability, liquidity, solvency, or earnings-quality risk.',
))

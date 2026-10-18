from audit_engine.models import RuleSpec, Severity
from audit_engine.rules.factory import build_rule

RULE = build_rule(RuleSpec(
    rule_id='DV-004',
    name='Mandatory field completeness',
    group='Handbook Rules',
    category='data_completeness',
    validation_logic='missing_required',
    severity=Severity.CRITICAL,
    required_metrics=('Company', 'Year'),
    description='Tests mandatory field completeness using only supplied financial-statement metrics.',
    business_purpose='Focuses audit review on a material inconsistency, adverse condition, or statistically unusual relationship.',
    formula='missing_required',
    threshold='No arbitrary threshold; logical condition or configurable tolerance',
    recommendation='Investigate the underlying drivers and obtain supporting evidence before relying on the reported balance.',
    risk_impact='Potential financial-statement reliability, liquidity, solvency, or earnings-quality risk.',
))

from audit_engine.models import RuleSpec, Severity
from audit_engine.rules.factory import build_rule

RULE = build_rule(RuleSpec(
    rule_id='DV-007',
    name='Numeric financial value validation',
    group='Handbook Rules',
    category='data_completeness',
    validation_logic='numeric_fields',
    severity=Severity.HIGH,
    required_metrics=(),
    description='Tests numeric financial value validation using only supplied financial-statement metrics.',
    business_purpose='Focuses audit review on a material inconsistency, adverse condition, or statistically unusual relationship.',
    formula='numeric_fields',
    threshold='No arbitrary threshold; logical condition or configurable tolerance',
    recommendation='Investigate the underlying drivers and obtain supporting evidence before relying on the reported balance.',
    risk_impact='Potential financial-statement reliability, liquidity, solvency, or earnings-quality risk.',
))

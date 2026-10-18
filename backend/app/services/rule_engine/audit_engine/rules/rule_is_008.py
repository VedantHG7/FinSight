from audit_engine.models import RuleSpec, Severity
from audit_engine.rules.factory import build_rule

RULE = build_rule(RuleSpec(
    rule_id='IS-008',
    name='Effective tax rate reasonableness',
    group='Handbook Rules',
    category='analytical',
    validation_logic='feature_zscore',
    severity=Severity.MEDIUM,
    required_metrics=('effective_tax_rate',),
    description='Tests effective tax rate reasonableness using only supplied financial-statement metrics.',
    business_purpose='Focuses audit review on a material inconsistency, adverse condition, or statistically unusual relationship.',
    formula='feature_zscore',
    threshold='Robust z-score against same-year peer population (configurable)',
    recommendation='Investigate the underlying drivers and obtain supporting evidence before relying on the reported balance.',
    risk_impact='Potential financial-statement reliability, liquidity, solvency, or earnings-quality risk.',
))

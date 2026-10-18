from audit_engine.models import RuleSpec, Severity
from audit_engine.rules.factory import build_rule

RULE = build_rule(RuleSpec(
    rule_id='TR-009',
    name='Margin trend stability',
    group='Handbook Rules',
    category='trend',
    validation_logic='margin_instability',
    severity=Severity.MEDIUM,
    required_metrics=('Profit_Margin', 'Operating_Margin'),
    description='Tests margin trend stability using only supplied financial-statement metrics.',
    business_purpose='Focuses audit review on a material inconsistency, adverse condition, or statistically unusual relationship.',
    formula='margin_instability',
    threshold='Robust z-score against same-year peer population (configurable)',
    recommendation='Investigate the underlying drivers and obtain supporting evidence before relying on the reported balance.',
    risk_impact='Potential financial-statement reliability, liquidity, solvency, or earnings-quality risk.',
))

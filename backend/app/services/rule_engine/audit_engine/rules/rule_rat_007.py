from audit_engine.models import RuleSpec, Severity
from audit_engine.rules.factory import build_rule

RULE = build_rule(RuleSpec(
    rule_id='RAT-007',
    name='Equity ratio',
    group='Handbook Rules',
    category='ratio',
    validation_logic='config_min',
    severity=Severity.HIGH,
    required_metrics=('Equity_Ratio',),
    description='Tests equity ratio using only supplied financial-statement metrics.',
    business_purpose='Focuses audit review on a material inconsistency, adverse condition, or statistically unusual relationship.',
    formula='config_min',
    threshold='Configurable ratio limit',
    recommendation='Investigate the underlying drivers and obtain supporting evidence before relying on the reported balance.',
    risk_impact='Potential financial-statement reliability, liquidity, solvency, or earnings-quality risk.',
))

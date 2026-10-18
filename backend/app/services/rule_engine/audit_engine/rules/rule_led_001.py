from audit_engine.models import RuleSpec, Severity
from audit_engine.rules.factory import build_rule

RULE = build_rule(RuleSpec(
    rule_id='LED-001',
    name='Accounting equation',
    group='Handbook Rules',
    category='integrity',
    validation_logic='accounting_equation',
    severity=Severity.CRITICAL,
    required_metrics=('Total Assets', 'Total Liabilities', 'Equity Share Capital', 'Reserves'),
    description='Tests accounting equation using only supplied financial-statement metrics.',
    business_purpose='Focuses audit review on a material inconsistency, adverse condition, or statistically unusual relationship.',
    formula='accounting_equation',
    threshold='No arbitrary threshold; logical condition or configurable tolerance',
    recommendation='Investigate the underlying drivers and obtain supporting evidence before relying on the reported balance.',
    risk_impact='Potential financial-statement reliability, liquidity, solvency, or earnings-quality risk.',
))

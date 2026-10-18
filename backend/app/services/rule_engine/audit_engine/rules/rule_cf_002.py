from audit_engine.models import RuleSpec, Severity
from audit_engine.rules.factory import build_rule

RULE = build_rule(RuleSpec(
    rule_id='CF-002',
    name='Cash flow to cash-balance tie-out',
    group='Handbook Rules',
    category='integrity',
    validation_logic='cash_delta_tieout',
    severity=Severity.CRITICAL,
    required_metrics=('Cash & Bank', 'Net Cash Flow'),
    description='Tests cash flow to cash-balance tie-out using only supplied financial-statement metrics.',
    business_purpose='Focuses audit review on a material inconsistency, adverse condition, or statistically unusual relationship.',
    formula='cash_delta_tieout',
    threshold='No arbitrary threshold; logical condition or configurable tolerance',
    recommendation='Investigate the underlying drivers and obtain supporting evidence before relying on the reported balance.',
    risk_impact='Potential financial-statement reliability, liquidity, solvency, or earnings-quality risk.',
))

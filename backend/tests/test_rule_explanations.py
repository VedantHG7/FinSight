import unittest
from pathlib import Path
from app.services.analysis_service import AnalysisService


class RuleExplanationTests(unittest.TestCase):
    def test_reconciliation_saves_prior_value_difference_and_tolerance(self):
        service = AnalysisService(None)
        raw = service._extract_workbook(Path(__file__).resolve().parents[2] / 'client_data.xlsx')
        rules = service._run_rules(service._preprocess(raw))
        cash = next(r for r in rules['violations'] if r['Rule ID'] == 'CF-002')
        evidence = cash['Observed']
        self.assertIn('Prior cash balance', evidence)
        self.assertAlmostEqual(evidence['Change in cash'] - evidence['Net Cash Flow'], evidence['Reconciliation difference'], places=5)
        self.assertGreater(abs(evidence['Reconciliation difference']), evidence['Tolerance'])
        self.assertIn('absolute reconciliation difference', cash['Evaluation Detail'])

    def test_xai_keeps_every_failed_rule(self):
        import pandas as pd
        service = AnalysisService(None)
        violations = [{'Company':'Fixture','Year':2025,'Rule ID':str(i),'Message':'Failed','Severity':'High','Recommendation':'Review'} for i in range(12)]
        rules = {'risk_scores':[], 'violations':violations}
        result = service._build_xai(pd.DataFrame([{'Company':'Fixture','Year':2025}]), rules, {'rows':[]})
        self.assertEqual(result['rows'][0]['Violation Count'],12)
        self.assertEqual(len(result['rows'][0]['Rule Evidence']),12)

import unittest
import json
import tempfile
from pathlib import Path

import pandas as pd

from app.services.analysis_service import AnalysisService, REQUIRED_COLUMNS


class RuleReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.service = AnalysisService(None)
        self.rules = {r.spec.rule_id: r for r in self.service._rules()}
        self.config = {'tolerance': .01, 'minimum_history': 3, 'z_score': 3,
                       'ratio_limits': {'Debt_Equity_Ratio': 2, 'Debt_Ratio': .7},
                       'required_columns': REQUIRED_COLUMNS}

    def evaluate(self, rule, records, index=-1):
        frame = pd.DataFrame(records)
        return self.rules[rule].evaluate(frame, frame.index[index], self.config)

    def test_duplicate_rules_are_not_executed(self):
        self.assertEqual(len(self.rules), 40)
        self.assertNotIn('LED-001', self.rules)
        self.assertNotIn('TR-002', self.rules)

    def test_single_observation_and_zero_dispersion_abstain(self):
        for values in ([100], [100, 100, 100]):
            result = self.evaluate('DV-015', [dict(Company=str(i), Year=2025, Sales=v) for i, v in enumerate(values)])
            self.assertEqual(result.status.value, 'skipped')
            self.assertIn('Cannot evaluate', result.message)

    def test_statistical_outlier_with_valid_population(self):
        result = self.evaluate('DV-015', [dict(Company=str(i), Year=2025, Sales=v) for i, v in enumerate([90, 100, 110, 1000])])
        self.assertEqual(result.status.value, 'fail')

    def test_threshold_boundary_and_missing_configuration(self):
        for value, expected in [(2, 'pass'), (2.01, 'fail')]:
            result = self.evaluate('RAT-005', [dict(Company='A', Year=2025, Debt_Equity_Ratio=value)])
            self.assertEqual(result.status.value, expected)
        result = self.evaluate('RAT-007', [dict(Company='A', Year=2025, Equity_Ratio=.4)])
        self.assertEqual(result.status.value, 'skipped')
        self.assertIn('threshold', result.message)

    def test_trends_require_strict_change_and_consecutive_years(self):
        for years, margins, expected in [([2023,2024,2025],[.3,.2,.1],'fail'),
                                          ([2023,2024,2025],[.2,.2,.2],'pass'),
                                          ([2021,2024,2025],[.3,.2,.1],'skipped'),
                                          ([2023,2024,2025],[.3,None,.1],'skipped')]:
            result = self.evaluate('RAT-011', [dict(Company='A',Year=y,Profit_Margin=m) for y,m in zip(years,margins)])
            self.assertEqual(result.status.value, expected)

    def test_cash_reconciliation_does_not_bridge_missing_year(self):
        result = self.evaluate('CF-002', [{'Company':'A','Year':2023,'Cash & Bank':10,'Net Cash Flow':0},
                                        {'Company':'A','Year':2025,'Cash & Bank':20,'Net Cash Flow':10}])
        self.assertEqual(result.status.value, 'skipped')

    def test_operating_cash_requires_complete_adjustment_bridge(self):
        record = {'Company':'A','Year':2025,'Net profit':100,'Depreciation':20,'Cash from Operating Activity':90}
        self.assertEqual(self.evaluate('CF-006',[record]).status.value,'skipped')
        record['Other Operating Cash Adjustments'] = -30
        self.assertEqual(self.evaluate('CF-006',[record]).status.value,'pass')
        record['Cash from Operating Activity'] = 80
        self.assertEqual(self.evaluate('CF-006',[record]).status.value,'fail')

    def test_preprocessing_preserves_invalid_source_evidence_and_schema(self):
        frame = self.service._preprocess(pd.DataFrame([{'Company':'A','Year':2025,'Sales':100,'Interest':'bad'}]))
        result = self.service._run_rules(frame)
        rows = {r['Rule ID']:r for r in result['rows']}
        self.assertEqual(rows['DV-007']['Status'],'fail')
        self.assertEqual(rows['DV-012']['Status'],'fail')
        self.assertIn('Interest',rows['DV-007']['Observed']['Invalid numeric fields'])
        self.assertEqual(result['summary']['errors'],0)

    def test_rule_features_have_explicit_definitions(self):
        record = {'Company':'A','Year':2025,'Sales':100,'Profit before tax':20,'Net profit':15,
                  'Interest':5,'Total Assets':200,'Equity Share Capital':40,'Reserves':60,
                  'Inventory':10,'Receivables':20,'Credit Sales':80,'Cost of Goods Sold':50}
        row = self.service._preprocess(pd.DataFrame([record])).iloc[0]
        for name, value in {'Equity_Ratio':.5,'Interest_Coverage_Ratio':5,'Asset_Utilization_Ratio':.5,
                            'effective_tax_rate':.25,'inventory_turnover':5,'dio':73,
                            'receivables_turnover':4,'dso':91.25}.items():
            self.assertEqual(row[name],value,name)

    def test_zero_denominators_remain_unavailable(self):
        frame = self.service._preprocess(pd.DataFrame([{'Company':'A','Year':2025,'Sales':100,
                                                       'Total Assets':0,'Interest':0,'Profit before tax':10}]))
        self.assertTrue(pd.isna(frame.iloc[0]['Interest_Coverage_Ratio']))
        self.assertTrue(pd.isna(frame.iloc[0]['Asset_Utilization_Ratio']))

    def test_date_check_survives_preprocessing(self):
        frame = self.service._preprocess(pd.DataFrame([{'Company':'A','Year':2025,'Sales':100,'Report Date':'2024-03-31'}]))
        result = self.rules['DV-018'].evaluate(frame,0,self.config)
        self.assertEqual(result.status.value,'fail')

    def test_gross_margin_requires_gross_profit_or_cost_of_goods(self):
        record = {'Company':'A','Year':2025,'Sales':100,'Expenses':80}
        frame = self.service._preprocess(pd.DataFrame([record]))
        self.assertNotIn('Gross_Profit_Margin',frame)
        record['Cost of Goods Sold'] = 60
        frame = self.service._preprocess(pd.DataFrame([record]))
        self.assertEqual(frame.iloc[0]['Gross_Profit_Margin'],.4)

    def test_cash_profit_check_uses_both_source_measures(self):
        for cash, expected in [(80,'fail'),(100,'pass'),(120,'pass')]:
            result = self.evaluate('CF-009',[{'Company':'A','Year':2025,'Net profit':100,'Cash from Operating Activity':cash}])
            self.assertEqual(result.status.value,expected)

    def test_growth_abstains_across_missing_year_and_duplicates_rejected(self):
        frame = pd.DataFrame([{'Company':'A','Year':2023,'Sales':100},{'Company':'A','Year':2025,'Sales':120}])
        self.assertTrue(pd.isna(self.service._preprocess(frame).iloc[1]['Revenue_Growth']))
        frame.loc[1,'Year'] = 2023
        with self.assertRaisesRegex(ValueError,'one record'):
            self.service._preprocess(frame)

    def test_rules_serialize_and_render_report_without_ml_dependency(self):
        raw = self.service._extract_workbook(Path(__file__).resolve().parents[2] / 'client_data.xlsx')
        frame = self.service._preprocess(raw)
        rules = self.service._run_rules(frame)
        self.assertEqual(rules['summary']['errors'],0)
        self.assertEqual(rules['summary']['total'],40 * len(frame))
        json.dumps(rules,allow_nan=False)
        ml = {'summary':{'records':0,'anomalies':None,'status':'unavailable','reason':'Test without ML dependency','missing_features':[]},'rows':[]}
        xai = self.service._build_xai(frame,rules,ml)
        report = self.service._build_report(1,frame,rules,ml,xai)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'report.pdf'
            self.service._generate_pdf(path,report)
            self.assertTrue(path.read_bytes().startswith(b'%PDF'))

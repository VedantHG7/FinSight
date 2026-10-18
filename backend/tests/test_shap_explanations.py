"""Check real saved-model attribution, sign conventions and evidence boundaries."""
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd

from app.services.analysis_service import AnalysisService
from app.services.ml_explanations import explain_rows

ARTIFACTS = Path(__file__).resolve().parents[1] / 'app/models/ml_artifacts'


class ShapExplanationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = AnalysisService(None)
        cls.features = list(joblib.load(ARTIFACTS / 'feature_columns.pkl'))
        cls.model = joblib.load(ARTIFACTS / 'isolation_forest.pkl')
        cls.scaler = joblib.load(ARTIFACTS / 'robust_scaler.pkl')
        cls.imputer = joblib.load(ARTIFACTS / 'imputer.pkl')
        baseline = np.asarray(cls.imputer.statistics_)
        # Reference, extreme input, and a partially missing extreme input.
        cls.frame = pd.DataFrame([baseline, np.abs(baseline) * 1000 + 1e6, np.abs(baseline) * 1000 + 1e6], columns=cls.features)
        cls.frame.loc[2, cls.features[0]] = np.nan
        cls.frame['Company'] = 'SHAP regression fixture'
        cls.frame['Year'] = [2023, 2024, 2025]
        cls.result = cls.service._run_ml(cls.frame)

    def test_additive_values_reproduce_real_prediction(self):
        for row in self.result['rows']:
            exp = row['SHAP']
            self.assertEqual(exp['status'], 'available')
            self.assertAlmostEqual(exp['base_value'] + sum(f['contribution'] for f in exp['features']), exp['output_value'], places=9)
            self.assertAlmostEqual(exp['output_value'], row['Anomaly Score'], places=5)
            self.assertEqual(row['Prediction'] == 'Anomaly', exp['output_value'] > 0)
            self.assertEqual(set(self.features), {f['feature'] for f in exp['features']})
        self.assertIn('Anomaly', {r['Prediction'] for r in self.result['rows']})
        json.dumps(self.result, allow_nan=False)

    def test_reference_has_zero_contributions(self):
        exp = self.result['rows'][0]['SHAP']
        self.assertTrue(all(abs(f['contribution']) < 1e-10 for f in exp['features']))
        self.assertAlmostEqual(exp['base_value'], exp['output_value'], places=10)

    def test_missing_values_never_presented_as_reported_evidence(self):
        exp = self.result['rows'][2]['SHAP']
        feature = next(f for f in exp['features'] if f['feature'] == self.features[0])
        self.assertTrue(feature['imputed'])
        self.assertIsNone(feature['observed_value'])
        self.assertEqual(feature['model_value'], feature['reference_value'])
        self.assertAlmostEqual(feature['contribution'], 0)
        self.assertIn('not reported evidence', feature['interpretation'])
        self.assertTrue(pd.isna(self.frame.loc[2, self.features[0]]))

    def test_reproducible_and_preserves_nonconsecutive_indices(self):
        observed = self.frame.loc[[1], self.features].set_axis([42])
        result = explain_rows(self.model, self.scaler, self.imputer, observed, observed.copy(), ARTIFACTS)
        again = explain_rows(self.model, self.scaler, self.imputer, observed, observed.copy(), ARTIFACTS)
        self.assertEqual(result, again)
        self.assertIn(42, result)
        self.assertEqual(len(result[42]['artifacts_sha256']), 4)

    def test_no_observations_abstains_from_shap(self):
        frame = self.frame.iloc[:1].copy()
        frame[self.features] = np.nan
        row = self.service._run_ml(frame)['rows'][0]
        self.assertEqual(row['Prediction'], 'Unavailable')
        self.assertEqual(row['SHAP']['status'], 'unavailable')
        self.assertNotIn('features', row['SHAP'])

    def test_explanation_failure_is_explicit_without_fabricating_attribution(self):
        with patch('app.services.ml_explanations.explain_rows', side_effect=ValueError('Invalid reconstruction')), self.assertLogs('app.services.analysis_service', level='ERROR'):
            row = self.service._run_ml(self.frame.iloc[:1])['rows'][0]
        self.assertNotEqual(row['Prediction'], 'Unavailable')
        self.assertEqual(row['SHAP']['status'], 'unavailable')
        self.assertNotIn('features', row['SHAP'])


if __name__ == '__main__':
    unittest.main()

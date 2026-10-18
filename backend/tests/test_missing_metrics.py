"""Run with: python -m unittest discover -s tests -v"""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.analysis import router
from app.api.routes.auth import router as auth_router
from app.services.jobs import run_once
from app.core.config import settings
from app.db.database import Base, get_db
from app.services.analysis_service import AnalysisService


SAMPLE = Path(__file__).resolve().parents[2] / 'client_data.xlsx'


class MissingMetricsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = AnalysisService(None)
        cls.raw = cls.service._extract_workbook(SAMPLE)

    def test_original_workbook_still_scores_supported_years(self):
        df = self.service._preprocess(self.raw)
        ml = self.service._run_ml(df)
        self.assertGreater(ml['summary']['records'], 0)
        self.assertEqual(len(ml['rows']), len(df))
        self.assertEqual(self.service._run_rules(df)['summary']['errors'], 0)

    def test_missing_sector_features_preserve_unknowns(self):
        df = self.service._preprocess(self.raw.drop(columns=['Raw Material Cost', 'Change in Inventory', 'Inventory']))
        for col in ['Raw Material Cost', 'Change in Inventory', 'Inventory', 'Inventory_Growth', 'Inventory_Ratio', 'Expenses']:
            self.assertTrue(df[col].isna().all(), col)
        ml = self.service._run_ml(df)
        self.assertEqual(ml['summary']['records'], len(df))
        self.assertEqual(ml['summary']['status'], 'reduced_coverage')
        self.assertTrue(all(r['Decision Score'] is not None for r in ml['rows']))
        self.assertTrue(all('Raw Material Cost' in r['Imputed Features'] for r in ml['rows']))
        self.assertTrue(all(r['Coverage Status'] in {'Low coverage', 'Reduced coverage'} for r in ml['rows']))
        self.assertTrue(df['Raw Material Cost'].isna().all())
        rules = self.service._run_rules(df)
        self.assertEqual(rules['summary']['errors'], 0)
        self.assertGreater(rules['summary']['skipped'], 0)

    def test_sparse_data_finishes_without_false_low_risk(self):
        df = self.service._preprocess(self.raw[['Company', 'Year', 'Sales']])
        rules = self.service._run_rules(df)
        ml = self.service._run_ml(df)
        xai = self.service._build_xai(df, rules, ml)
        report = self.service._build_report(1, df, rules, ml, xai)
        self.assertEqual(rules['summary']['errors'], 0)
        self.assertTrue(all(r['Risk Score'] is None for r in rules['risk_scores']))
        self.assertIsNone(report['overview']['average_risk_score'])
        self.assertEqual(ml['summary']['records'], len(df))
        self.assertTrue(all('saved training medians filled' in r['Explanation'] for r in xai['rows']))
        json.dumps(report, allow_nan=False)

    def test_zero_observed_model_features_still_abstains(self):
        df = self.service._preprocess(self.raw)
        # The saved model has more features than ML_FEATURES. Build the exact
        # model input from the artifact to avoid assuming a fixed test schema.
        import joblib
        features = joblib.load(Path(__file__).resolve().parents[1] / 'app/models/ml_artifacts/feature_columns.pkl')
        df.loc[0, features] = np.nan
        ml = self.service._run_ml(df)
        self.assertEqual(ml['rows'][0]['Prediction'], 'Unavailable')
        self.assertEqual(ml['summary']['records'], len(df) - 1)
        self.assertEqual(ml['rows'][0]['Imputed Features'], [])

    def test_partial_missing_cells_only_imputed_inside_ml(self):
        df = self.service._preprocess(self.raw)
        idx = df.index[-1]
        df.loc[idx, 'Raw Material Cost'] = np.nan
        ml = self.service._run_ml(df)
        self.assertNotEqual(ml['rows'][-1]['Prediction'], 'Unavailable')
        self.assertGreater(ml['rows'][-1]['Imputed Values'], 0)
        self.assertTrue(pd.isna(df.loc[idx, 'Raw Material Cost']))
        self.assertNotIn('Raw Material Cost', [r['feature'] for r in ml['rows'][-1]['Evidence']])

    def test_growth_does_not_fill_missing_year_values(self):
        raw = self.raw.copy()
        raw.loc[3, 'Inventory'] = np.nan
        df = self.service._preprocess(raw)
        self.assertTrue(pd.isna(df.loc[3, 'Inventory_Growth']))
        self.assertTrue(pd.isna(df.loc[4, 'Inventory_Growth']))

    def test_reported_zero_is_preserved(self):
        raw = self.raw.copy()
        raw['Inventory'] = 0
        df = self.service._preprocess(raw)
        self.assertTrue(df['Inventory'].eq(0).all())
        self.assertNotIn('Inventory', self.service._run_ml(df)['summary']['missing_features'])

    def test_alias_and_empty_validation(self):
        renamed = self.raw.rename(columns={'Sales': 'Revenue from operations'})
        self.assertTrue(self.service._preprocess(renamed)['Sales'].equals(self.raw['Sales'].astype(float).round(4)))
        with self.assertRaisesRegex(ValueError, 'numeric financial'):
            self.service._preprocess(self.raw[['Company', 'Year']])

    def test_skipped_checks_do_not_dilute_risk(self):
        rows = pd.DataFrame([
            {'Company': 'Example', 'Year': 2025, 'Rule ID': str(i), 'Severity': 'High', 'Category': 'liquidity', 'Status': status}
            for i, status in enumerate(['fail', 'pass', 'skipped'])
        ])
        score = self.service._risk_scores(rows).iloc[0]
        self.assertEqual(score['Risk Score'], 50)
        self.assertAlmostEqual(score['Coverage Percent'], 66.67)

    def test_upload_to_report_and_downloads_with_missing_columns(self):
        workbook = load_workbook(SAMPLE)
        sheet = workbook['Data Sheet']
        for row in sheet.iter_rows():
            if row[0].value in {'Raw Material Cost', 'Change in Inventory', 'Inventory'}:
                for cell in row[1:]:
                    cell.value = None
        upload = io.BytesIO()
        workbook.save(upload)
        engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        sessions = sessionmaker(bind=engine)
        def database():
            with sessions() as session:
                yield session
        app = FastAPI()
        app.include_router(router, prefix='/api')
        app.include_router(auth_router, prefix='/api')
        app.dependency_overrides[get_db] = database
        with tempfile.TemporaryDirectory() as directory, patch.object(settings, 'ANALYSIS_WORKSPACE_PATH', Path(directory)), TestClient(app) as client:
            account = client.post('/api/auth/register', json={'email': 'audit-test@example.com', 'password': 'test-passphrase-123', 'full_name': 'Test Auditor', 'organization': 'Test firm'})
            client.headers['x-csrf-token'] = account.json()['csrf_token']
            response = client.post('/api/analysis/upload', files={'file': ('missing_metrics.xlsx', upload.getvalue())})
            self.assertEqual(response.status_code, 202, response.text)
            aid = response.json()['analysis_id']
            self.assertTrue(run_once(sessions))
            self.assertEqual(client.get(f'/api/analysis/{aid}').json()['job']['state'], 'completed')
            for endpoint in ['', '/analysis', '/rules', '/ml', '/xai', '/trail', '/report', '/preprocessed.csv', '/audit-report.pdf']:
                result = client.get(f'/api/analysis/{aid}{endpoint}')
                self.assertEqual(result.status_code, 200, endpoint)
                if endpoint == '/audit-report.pdf':
                    self.assertTrue(result.content.startswith(b'%PDF'))
            report = client.get(f'/api/analysis/{aid}/report').json()
            self.assertEqual(report['overview']['analysis_status'], 'Completed with limitations')
            self.assertEqual(report['overview']['ml_status'], 'reduced_coverage')
            self.assertEqual(report['ml_summary']['records'], len(report['ml_findings']))
            self.assertTrue(all(r['Imputed Features'] for r in report['ml_findings']))
            self.assertTrue(report['limitations'])
        engine.dispose()


if __name__ == '__main__':
    unittest.main()

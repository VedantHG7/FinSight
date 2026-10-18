import io
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from openpyxl import load_workbook, Workbook
from fastapi import UploadFile
from app.services.upload_preview import preview_upload

SAMPLE = Path(__file__).resolve().parents[2] / 'client_data.xlsx'
TEMPLATE = Path(__file__).resolve().parents[2] / 'frontend' / 'public' / 'data' / 'FinSight_Template.xlsx'


class UploadPreviewTests(unittest.TestCase):
    def test_blank_template_accepts_annual_data_and_cash_flow_headings(self):
        from app.services.analysis_service import AnalysisService
        for heading in ('CASH FLOW', 'CASH FLOW:'):
            with self.subTest(heading=heading):
                book = load_workbook(TEMPLATE)
                sheet = book['Data Sheet']
                self.assertIsNone(sheet['B1'].value)
                self.assertIsNone(sheet['B9'].value)
                sheet['B1'] = 'Example Ltd'
                sheet['B2'] = 'INR crore'
                sheet['A41'] = heading
                for cell in ('B8', 'B26', 'B42'):
                    sheet[cell] = datetime(2025, 3, 31)
                for cell, value in {'B9': 100, 'B20': 22, 'B21': 18, 'B22': 12,
                                    'B27': 20, 'B28': 30, 'B29': 10, 'B31': 80,
                                    'B36': 80, 'B43': 15, 'B44': -5, 'B45': -3,
                                    'B46': 7}.items():
                    sheet[cell] = value
                result = self.preview(book)
                self.assertTrue(result['valid'], result)
                self.assertEqual(result['company'], 'Example Ltd')
                self.assertEqual(result['years'], [2025])
                self.assertEqual(result['financial_units']['label'], 'INR crore')
                self.assertEqual(result['rows'][0]['Cash from Operating Activity'], 15)
                with TemporaryDirectory() as directory:
                    path = Path(directory) / 'upload.xlsx'
                    book.save(path)
                    service = AnalysisService(None)
                    service._extract_workbook(path)
                    cash = next(cell for cell in service.provenance if cell['source_label'] == 'Cash from Operating Activity')
                    self.assertEqual(cash['statement'], 'Cash Flow')

    def test_legacy_xls_preview_and_extraction(self):
        from app.services.analysis_service import AnalysisService
        sample = Path(__file__).parent / 'fixtures' / 'legacy_sample.xls'
        result = preview_upload(UploadFile(filename='legacy.xls', file=io.BytesIO(sample.read_bytes())))
        self.assertTrue(result['valid'], result)
        self.assertEqual(result['company'], 'Legacy XLS test')
        self.assertEqual(result['years'], [2024, 2025])
        self.assertEqual(result['financial_units']['label'], 'INR crore')
        rows = AnalysisService(None)._extract_workbook(sample)
        self.assertEqual(rows['Sales'].tolist(), [100, 120])

    def preview(self, book):
        stream = io.BytesIO()
        book.save(stream)
        stream.seek(0)
        return preview_upload(UploadFile(filename='test.xlsx', file=stream))

    def test_sample_matches_analysis_and_has_hash(self):
        result = self.preview(load_workbook(SAMPLE))
        self.assertTrue(result['valid'], result)
        self.assertTrue(result['company'])
        self.assertTrue(result['years'])
        self.assertEqual(len(result['file_hash']), 64)
        self.assertEqual(len(result['rows']), len(result['years']))

    def test_missing_sheet_and_company_are_actionable(self):
        result = self.preview(Workbook())
        self.assertFalse(result['valid'])
        self.assertIn('Data Sheet', result['errors'][0])
        book = load_workbook(SAMPLE)
        book['Data Sheet']['B1'] = None
        result = self.preview(book)
        self.assertFalse(result['valid'])
        self.assertIn('B1', result['errors'][0])

    def test_invalid_value_has_source_cell(self):
        book = load_workbook(SAMPLE)
        sheet = book['Data Sheet']
        for row in sheet:
            if row[0].value == 'Sales':
                target = row[1]
                target.value = 'not a number'
                break
        result = self.preview(book)
        self.assertFalse(result['valid'])
        self.assertTrue(any(c['cell'] == target.coordinate for c in result['invalid_cells']))

    def test_missing_values_are_warnings_not_zero(self):
        book = load_workbook(SAMPLE)
        for row in book['Data Sheet']:
            if row[0].value == 'Sales':
                for cell in row[1:]:
                    cell.value = None
        result = self.preview(book)
        self.assertTrue(result['valid'], result)
        self.assertTrue(any('Sales' in r['metrics'] for r in result['missing_metrics']))

    def test_duplicate_reporting_years_are_blocked(self):
        book = load_workbook(SAMPLE)
        for row in book['Data Sheet']:
            if str(row[0].value).lower() == 'report date':
                row[2].value = row[1].value
                break
        result = self.preview(book)
        self.assertFalse(result['valid'])
        self.assertTrue(any('duplicate reporting year' in e for e in result['errors']))


if __name__ == '__main__':
    unittest.main()

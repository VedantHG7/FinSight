import tempfile
import unittest
from pathlib import Path

import pandas as pd

from app.services.financial_units import workbook_units


class FinancialUnitsTests(unittest.TestCase):
    def detect(self, *labels):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'source.xlsx'
            pd.DataFrame(labels).to_excel(path, index=False, header=False)
            return workbook_units(path)

    def test_explicit_units(self):
        for label in ('Rs. in Crores', 'INR crore', '₹ Cr'):
            self.assertEqual(self.detect(label)['label'], 'INR crore')
        self.assertEqual(self.detect('USD millions')['label'], 'USD million')

    def test_no_inference_from_shares_or_values(self):
        self.assertEqual(self.detect('Adjusted Equity Shares in Cr', 500000)['status'], 'unknown')

    def test_conflicting_declarations(self):
        self.assertEqual(self.detect('INR crore', 'USD million')['status'], 'conflicting')

    def test_missing_workbook(self):
        self.assertEqual(workbook_units('missing.xlsx')['status'], 'unknown')

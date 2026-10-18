"""Read-only upload preflight using the analysis parser; no jobs or clients created."""
import hashlib
import math
import tempfile
import zipfile
from pathlib import Path
from openpyxl.utils import get_column_letter

import pandas as pd
from fastapi import HTTPException
from app.core.config import settings
from app.services.analysis_service import AnalysisService, REQUIRED_COLUMNS, ID_COLUMNS, _safe_string, _records
from app.services.financial_units import workbook_units


def preview_upload(upload):
    suffix = Path(upload.filename or '').suffix.lower()
    if suffix not in {'.xlsx', '.xls'}:
        raise HTTPException(400, 'Choose an Excel workbook (.xlsx or .xls).')
    with tempfile.TemporaryDirectory(prefix='finsight-preview-') as directory:
        path = Path(directory) / ('workbook' + suffix)
        digest = hashlib.sha256()
        size = 0
        with path.open('wb') as output:
            while chunk := upload.file.read(65536):
                size += len(chunk)
                if size > settings.MAX_UPLOAD_SIZE:
                    raise HTTPException(413, 'Workbook exceeds the 10 MB upload limit.')
                digest.update(chunk)
                output.write(chunk)
        if suffix == '.xlsx':
            if not zipfile.is_zipfile(path):
                raise HTTPException(400, 'The file is not a valid XLSX workbook. Save it as an Excel workbook and try again.')
            with zipfile.ZipFile(path) as archive:
                if len(archive.infolist()) > 2000 or sum(e.file_size for e in archive.infolist()) > 100*1024*1024:
                    raise HTTPException(413, 'The expanded workbook is too large.')
                if 'xl/workbook.xml' not in archive.namelist():
                    raise HTTPException(400, 'The file is not a valid XLSX workbook.')
        result = {'file_hash': digest.hexdigest(), 'valid': False, 'errors': [], 'warnings': [],
                  'company': '', 'years': [], 'rows': [], 'columns': [], 'missing_metrics': [],
                  'invalid_cells': [], 'financial_units': workbook_units(path)}
        try:
            with pd.ExcelFile(path) as book:
                result['sheets'] = book.sheet_names
                if 'Data Sheet' not in book.sheet_names:
                    result['errors'].append('Add a sheet named Data Sheet with financial statement sections and Report Date rows.')
                    return result
                header = book.parse('Data Sheet', header=None, nrows=1)
                if header.shape[1] < 2 or not _safe_string(header.iloc[0, 1]):
                    result['errors'].append('Enter the company name in Data Sheet cell B1.')
                    return result
                sheet = book.parse('Data Sheet', header=None)
                section = ''
                for index, row in sheet.iterrows():
                    label = _safe_string(row.iloc[0]).upper()
                    if label in {'PROFIT & LOSS', 'BALANCE SHEET', 'CASH FLOW', 'QUARTERS'}:
                        section = label
                    if label != 'REPORT DATE' or section not in {'PROFIT & LOSS', 'BALANCE SHEET', 'CASH FLOW'}:
                        continue
                    seen = set()
                    for column in range(1, len(row)):
                        value = row.iloc[column]
                        if pd.isna(value):
                            continue
                        cell = f'Data Sheet!{get_column_letter(column + 1)}{index + 1}'
                        try:
                            # The analysis reader expects Excel dates, not bare year numbers.
                            if isinstance(value, (int, float)):
                                raise ValueError()
                            year = pd.to_datetime(value).year
                            if not 1900 <= year <= 2200:
                                raise ValueError()
                        except (ValueError, TypeError, OverflowError):
                            result['errors'].append(f'{cell}: enter a full reporting date, such as 2025-03-31.')
                            continue
                        if year in seen:
                            result['errors'].append(f'{cell}: duplicate reporting year {year} in {section}. Keep one annual column per year.')
                        seen.add(year)
                if result['errors']:
                    return result
            service = AnalysisService(None)
            raw = service._extract_workbook(path)
            processed = service._preprocess(raw)
            result['company'] = str(raw.Company.iloc[0])
            result['years'] = [int(year) for year in raw.Year]
            result['columns'] = [c for c in raw.columns if c not in ID_COLUMNS + ['Report Date']]
            result['rows'] = _records(raw.drop(columns=['Report Date'], errors='ignore'))
            for cell in service.provenance:
                if cell['metric'] not in result['columns'] and cell['source_label'] not in result['columns']:
                    continue
                try:
                    valid = math.isfinite(float(cell['value']))
                except (ValueError, TypeError):
                    valid = False
                if not valid:
                    result['invalid_cells'].append(cell)
            for _, row in processed.iterrows():
                missing = [c for c in REQUIRED_COLUMNS if c not in ID_COLUMNS and pd.isna(row[c])]
                if missing:
                    result['missing_metrics'].append({'year': int(row.Year), 'metrics': missing})
            if result['invalid_cells']:
                result['errors'].append('Replace non-numeric financial values at the listed cells with numbers, or clear them to mark them unavailable.')
            if result['missing_metrics']:
                result['warnings'].append('Some key metrics are unavailable. Affected checks may be skipped and model coverage may be reduced. Add the missing values where available.')
            if result['financial_units']['status'] != 'detected':
                result['warnings'].append('Currency and scale are unspecified or conflicting. Add a single explicit declaration such as INR crore or USD million in the first 15 rows, then preview again; otherwise continue with units unspecified.')
            ignored = [s for s in result['sheets'] if s != 'Data Sheet']
            if ignored:
                result['warnings'].append('Financial values are read only from Data Sheet. Other sheets are not analysed: ' + ', '.join(ignored))
            result['valid'] = not result['errors']
        except ImportError:
            result['errors'].append('This Excel format needs an unavailable reader. Save the workbook as .xlsx and try again.')
        except (ValueError, IndexError, KeyError):
            result['errors'].append('No usable financial records could be read. Check Data Sheet, statement headings (PROFIT & LOSS, BALANCE SHEET, CASH FLOW), Report Date rows, valid dates, and numeric amounts.')
        except Exception:
            result['errors'].append('The workbook could not be read. Open it in Excel, save a fresh .xlsx copy, and try again.')
        return result

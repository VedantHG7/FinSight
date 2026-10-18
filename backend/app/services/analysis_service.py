from __future__ import annotations

import ast
import json
import math
import logging
import shutil
import sys
import uuid
from xml.sax.saxutils import escape
from datetime import datetime
from pathlib import Path
from openpyxl.utils import get_column_letter
from typing import Any

import joblib
import numpy as np
import pandas as pd
from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.financial_units import workbook_units
from app.db.models import Analysis, AnalysisEvent, AnalysisStatus, Client, User

RULE_ROOT = Path(__file__).resolve().parent / "rule_engine"
if str(RULE_ROOT) not in sys.path:
    sys.path.insert(0, str(RULE_ROOT))

from audit_engine.rules.factory import build_rule  # noqa: E402
from audit_engine import rules as rules_pkg  # noqa: E402
import importlib  # noqa: E402
import pkgutil  # noqa: E402


ID_COLUMNS = ["Company", "Year"]
DROP_COLUMNS = ["Report Date", "PRICE:", "Adjusted Equity Shares in Cr", "Face value", "New Bonus Shares", "No. of Equity Shares"]
REQUIRED_COLUMNS = [
    "Company", "Year", "Sales", "Operating Profit", "Profit before tax", "Net profit",
    "Equity Share Capital", "Reserves", "Borrowings", "Total Assets", "Total Liabilities",
    "Cash from Operating Activity", "Cash from Investing Activity", "Cash from Financing Activity", "Net Cash Flow",
]
ML_FEATURES = [
    "Profit_Margin", "Operating_Margin", "ROE", "ROA", "Debt_to_Equity", "Interest_Coverage",
    "Working_Capital_Ratio", "Asset_Utilization", "Receivable_Ratio", "Inventory_Ratio",
    "Expense_Ratio", "Depreciation_Ratio", "Operating_CF_Ratio", "Cash_to_Debt", "Cash_Margin",
]
GROWTH_COLUMNS = {
    "Sales": "Revenue_Growth", "Net profit": "Profit_Growth", "Borrowings": "Borrowing_Growth",
    "Total Assets": "Asset_Growth", "Reserves": "Reserve_Growth",
    "Cash from Operating Activity": "Operating_CF_Growth", "Receivables": "Receivable_Growth",
    "Inventory": "Inventory_Growth", "Cash & Bank": "Cash_Growth",
}
SEVERITY_WEIGHTS = {"Critical": 10, "High": 7, "Medium": 5, "Low": 2}
CATEGORY_WEIGHTS = {
    "integrity": 1.50, "fraud": 1.50, "compliance": 1.40, "solvency": 1.35,
    "liquidity": 1.30, "cash_flow": 1.25, "profitability": 1.20, "trend": 1.10,
    "efficiency": 1.10, "data_validation": 1.00,
}

# Operational coverage labels, not calibrated model-confidence estimates.
MIN_RULE_COVERAGE = 0.5
MIN_ML_COVERAGE = 0.8
METRIC_ALIASES = {
    "revenue": "Sales", "revenue from operations": "Sales",
    "net profit": "Net profit", "profit before tax": "Profit before tax",
    "cash and bank": "Cash & Bank", "inventories": "Inventory",
}


def _safe_string(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _is_year(value: Any) -> bool:
    try:
        pd.to_datetime(value)
        return True
    except Exception:
        return False


def _safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    result = numerator / denominator.replace(0, np.nan)
    return result.replace([np.inf, -np.inf], np.nan)


def _finite_value(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if not math.isfinite(float(value)) else round(float(value), 6)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    return value


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return [{k: _finite_value(v) for k, v in row.items()} for row in df.to_dict(orient="records")]


def _artifact_json(path: Path, fallback: Any = None) -> Any:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


class AnalysisService:
    def __init__(self, db: Session, checkpoint=None):
        self.db = db
        self.checkpoint = checkpoint
        self.provenance = []
        self.workspace = Path(settings.ANALYSIS_WORKSPACE_PATH)

    def process_analysis(self, analysis_id: int) -> dict[str, Any]:
        analysis = self._analysis(analysis_id)
        root = self._root(analysis.id)
        try:
            if self.checkpoint:
                self.checkpoint('Validating workbook', 5)
            raw_df = self._extract_workbook(Path(analysis.file_path))
            pre_df = self._preprocess(raw_df)
            companies = sorted(pre_df['Company'].dropna().astype(str).str.strip().unique())
            if len(companies) != 1:
                raise ValueError('Upload must contain exactly one company.')
            company = companies[0]
            from app.db.models import Membership
            owner = self.db.get(Membership, analysis.user_id)
            client = self.db.query(Client).join(Membership, Membership.user_id == Client.user_id).filter(
                Membership.organization_id == owner.organization_id, Client.company_name == company).first()
            if not client:
                client = Client(user_id=analysis.user_id, company_name=company)
                self.db.add(client)
                self.db.flush()
            analysis.client_id = client.id
            self.db.commit()
            self._write_json(root / 'raw' / 'source_cells.json', {'cells': self.provenance})
        except Exception:
            self.db.rollback()
            raise

        try:
            self._event(analysis.id, "Upload", "completed", f"Validated Excel workbook for {company}.")
            self._save_csv(raw_df, root / "raw" / "financial_dataset.csv")
            pre_path = root / "preprocessed" / f"preprocessed_{analysis.id}.csv"
            self._save_csv(pre_df, pre_path)
            analysis.status = AnalysisStatus.preprocessed
            self._event(analysis.id, "Preprocessing", "completed", f"Generated {len(pre_df)} company-year rows and {len(pre_df.columns)} metrics/features.")

            rules = self._run_rules(pre_df)
            self._write_json(root / "rules" / "rule_results.json", rules)
            analysis.status = AnalysisStatus.rules_applied
            self._event(analysis.id, "Rule Engine", "completed", f"Executed {rules['summary']['total']} rule checks.")

            ml = self._run_ml(pre_df)
            self._write_json(root / "ml" / "ml_results.json", ml)
            analysis.status = AnalysisStatus.ml_completed
            self._event(analysis.id, "ML Anomaly Detection", ml['summary']['status'], f"Scored {ml['summary']['records']} of {len(pre_df)} observations. {ml['summary']['reason']}")

            xai = self._build_xai(pre_df, rules, ml)
            self._write_json(root / "explainability" / "xai_results.json", xai)
            analysis.status = AnalysisStatus.xai_completed
            self._event(analysis.id, "Explainable AI", "completed", f"Built {len(xai['rows'])} client-specific explanations.")

            report = self._build_report(analysis.id, pre_df, rules, ml, xai)
            self._write_json(root / "report" / "audit_report.json", report)
            self._generate_pdf(root / "report" / f"audit_report_{analysis.id}.pdf", report)
            analysis.status = AnalysisStatus.completed
            self._event(analysis.id, "Audit Report", "completed", "Generated detailed audit report PDF.")
            self.db.commit()
            return {"analysis_id": analysis.id, "redirect": f"/app/audit-report/{analysis.id}", **self.summary(analysis.id)}
        except Exception:
            self.db.rollback()
            raise

    def summary(self, analysis_id: int) -> dict[str, Any]:
        analysis = self._analysis(analysis_id)
        report = _artifact_json(self._root(analysis_id) / "report" / "audit_report.json", {})
        return {
            "analysis_id": analysis.id,
            "status": analysis.status.value if hasattr(analysis.status, "value") else analysis.status,
            "filename": analysis.filename,
            "company": analysis.client.company_name,
            "created_at": analysis.created_at.isoformat() if analysis.created_at else None,
            "overview": report.get("overview", {}),
        }

    def preprocessed(self, analysis_id: int) -> dict[str, Any]:
        analysis = self._analysis(analysis_id)
        df = pd.read_csv(self.artifact_path(analysis_id, "preprocessed"))
        raw_path = self._root(analysis_id) / "raw" / "financial_dataset.csv"
        raw_df = pd.read_csv(raw_path) if raw_path.exists() else pd.DataFrame()
        metric_columns = [column for column in df.columns if column not in ID_COLUMNS]
        source_columns = [column for column in raw_df.columns if column not in ID_COLUMNS]
        source_cells = int(raw_df[source_columns].notna().sum().sum()) if source_columns else 0
        processed_cells = int(df[metric_columns].notna().sum().sum()) if metric_columns else 0
        total_processed_cells = len(df) * len(metric_columns)
        return {
            "analysis_id": analysis.id,
            "company": analysis.client.company_name,
            "columns": df.columns.tolist(),
            "rows": _records(df),
            "raw_columns": raw_df.columns.tolist(),
            "financial_units": workbook_units(analysis.file_path),
            "raw_rows": _records(raw_df) if not raw_df.empty else [],
            "validation": {
                "source_records": len(raw_df),
                "processed_records": len(df),
                "source_metrics": len(source_columns),
                "processed_metrics": len(metric_columns),
                "source_values_present": source_cells,
                "processed_values_present": processed_cells,
                "processed_values_missing": total_processed_cells - processed_cells,
                "processed_completeness_percent": round((processed_cells / total_processed_cells) * 100, 2) if total_processed_cells else 0,
            },
        }

    def rules(self, analysis_id: int) -> dict[str, Any]:
        self._analysis(analysis_id)
        return _artifact_json(self._root(analysis_id) / "rules" / "rule_results.json", {})

    def ml(self, analysis_id: int) -> dict[str, Any]:
        self._analysis(analysis_id)
        return _artifact_json(self._root(analysis_id) / "ml" / "ml_results.json", {})

    def xai(self, analysis_id: int) -> dict[str, Any]:
        self._analysis(analysis_id)
        return _artifact_json(self._root(analysis_id) / "explainability" / "xai_results.json", {})

    def report(self, analysis_id: int) -> dict[str, Any]:
        self._analysis(analysis_id)
        return _artifact_json(self._root(analysis_id) / "report" / "audit_report.json", {})

    def trail(self, analysis_id: int) -> dict[str, Any]:
        self._analysis(analysis_id)
        events = self.db.query(AnalysisEvent).filter(AnalysisEvent.analysis_id == analysis_id).order_by(AnalysisEvent.id).all()
        return {"analysis_id": analysis_id, "events": [{
            "id": e.id, "stage": e.stage, "status": e.status, "message": e.message,
            "details": e.details, "created_at": e.created_at.isoformat() if e.created_at else None,
        } for e in events]}

    def artifact_path(self, analysis_id: int, kind: str) -> Path:
        self._analysis(analysis_id)
        root = self._root(analysis_id)
        if kind == "preprocessed":
            return root / "preprocessed" / f"preprocessed_{analysis_id}.csv"
        if kind == "pdf":
            return root / "report" / f"audit_report_{analysis_id}.pdf"
        raise HTTPException(status_code=404, detail="Unknown artifact")

    def _analysis(self, analysis_id: int) -> Analysis:
        analysis = self.db.query(Analysis).filter(Analysis.id == analysis_id).first()
        if not analysis:
            raise HTTPException(status_code=404, detail="Analysis not found")
        return analysis

    def _root(self, analysis_id: int) -> Path:
        return self.workspace / str(analysis_id)

    def _event(self, analysis_id: int, stage: str, status: str, message: str, details: str | None = None) -> None:
        # Release this stage's transaction before the separate job session updates
        # its checkpoint. In particular SQLite permits only one writer at a time.
        self.db.commit()
        if self.checkpoint:
            progress = {'Upload': 15, 'Preprocessing': 30, 'Rule Engine': 50, 'ML Anomaly Detection': 70, 'Explainable AI': 85, 'Audit Report': 95}.get(stage, 0)
            self.checkpoint(stage, progress)
        self.db.add(AnalysisEvent(analysis_id=analysis_id, stage=stage, status=status, message=message, details=details))
        self.db.commit()

    def _save_csv(self, df: pd.DataFrame, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False, encoding="utf-8")

    def _write_json(self, path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + '.tmp')
        temporary.write_text(json.dumps(data, indent=2, default=_finite_value), encoding="utf-8")
        temporary.replace(path)

    def _extract_workbook(self, file_path: Path) -> pd.DataFrame:
        self.provenance = []
        data_df = pd.read_excel(file_path, sheet_name="Data Sheet", header=None)
        company = _safe_string(data_df.iloc[0, 1]) or file_path.stem
        section_map = {"PROFIT & LOSS": "Profit & Loss", "BALANCE SHEET": "Balance Sheet", "CASH FLOW": "Cash Flow", "QUARTERS": "Quarters"}
        extracted: dict[str, list[dict[str, Any]]] = {}
        for label, statement_name in section_map.items():
            start = next((i for i in range(len(data_df)) if _safe_string(data_df.iloc[i, 0]).upper() == label), None)
            if start is None:
                continue
            report_row = next((i for i in range(start + 1, min(len(data_df), start + 30)) if _safe_string(data_df.iloc[i, 0]).lower() == "report date"), None)
            if report_row is None:
                continue
            year_cols = []
            for col in range(1, data_df.shape[1]):
                value = data_df.iloc[report_row, col]
                if not pd.isna(value) and _is_year(value):
                    year_cols.append((col, pd.to_datetime(value).year))
            section_records = []
            for col, year in year_cols:
                total_counter = 0
                row_data = {"Year": year, "Report Date": data_df.iloc[report_row, col]}
                for row in range(report_row + 1, len(data_df)):
                    metric = _safe_string(data_df.iloc[row, 0])
                    if not metric:
                        continue
                    if metric.upper() in section_map:
                        break
                    if statement_name == "Balance Sheet" and metric == "Total":
                        total_counter += 1
                        metric = "Total Liabilities" if total_counter == 1 else "Total Assets"
                    value = data_df.iloc[row, col]
                    if not pd.isna(value):
                        row_data[metric] = value
                        if statement_name != 'Quarters':
                            self.provenance.append({'year': int(year), 'metric': METRIC_ALIASES.get(metric.strip().lower(), metric.strip()),
                                'source_label': _safe_string(data_df.iloc[row, 0]), 'sheet': 'Data Sheet',
                                'cell': f'{get_column_letter(col + 1)}{row + 1}', 'statement': statement_name, 'value': _finite_value(value)})
                section_records.append(row_data)
            extracted[statement_name] = section_records
        merged: dict[int, dict[str, Any]] = {}
        for statement in ("Profit & Loss", "Balance Sheet", "Cash Flow"):
            for row in extracted.get(statement, []):
                merged.setdefault(row["Year"], {"Company": company, "Year": row["Year"]}).update(row)
        if not merged:
            raise ValueError("No financial records were extracted from the Data Sheet.")
        df = pd.DataFrame(list(merged.values())).drop_duplicates()
        df.dropna(axis=1, how="all", inplace=True)
        return df.sort_values(["Company", "Year"]).reset_index(drop=True)

    def _preprocess(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy().drop(columns=[c for c in DROP_COLUMNS if c != 'Report Date'], errors="ignore")
        for column in list(df.columns):
            canonical = METRIC_ALIASES.get(str(column).strip().lower(), str(column).strip())
            if canonical != column:
                if canonical in df.columns:
                    df[canonical] = df[canonical].combine_first(df[column])
                    df.drop(columns=[column], inplace=True)
                else:
                    df.rename(columns={column: canonical}, inplace=True)
        if df.empty or not set(ID_COLUMNS).issubset(df.columns):
            raise ValueError("The workbook must identify a company and reporting year with usable financial data.")
        years = pd.to_numeric(df['Year'], errors='coerce')
        if years.isna().any() or ((years % 1) != 0).any() or not years.between(1900, 2200).all() or df['Company'].isna().any() or df['Company'].astype(str).str.strip().eq('').any():
            raise ValueError("Each record must have a company and valid reporting year.")
        df['Year'] = years.astype(int)
        if df.duplicated(ID_COLUMNS).any():
            raise ValueError('Each company must have only one record per reporting year.')
        df = df.sort_values(ID_COLUMNS).reset_index(drop=True)
        source_columns = list(df.columns)
        invalid_numeric = {}
        for col in [c for c in df.columns if c not in ID_COLUMNS + ['Report Date']]:
            converted = pd.to_numeric(df[col], errors="coerce")
            invalid = df[col].notna() & (converted.isna() | converted.isin([np.inf, -np.inf]))
            for index in df.index[invalid]:
                invalid_numeric.setdefault(index, []).append(col)
            df[col] = converted
        df.replace([np.inf, -np.inf], np.nan, inplace=True)
        if not df.drop(columns=ID_COLUMNS + ['Report Date'], errors='ignore').notna().any().any():
            raise ValueError("No usable numeric financial metrics were found in the workbook.")
        expense_fields = ["Raw Material Cost", "Change in Inventory", "Power and Fuel", "Other Mfr. Exp", "Employee Cost", "Selling and admin", "Other Expenses", "Depreciation", "Interest"]
        if "Expenses" not in df.columns and all(c in df.columns for c in expense_fields):
            df["Expenses"] = df[expense_fields].sum(axis=1, min_count=len(expense_fields))
        if "Operating Profit" not in df.columns and {"Sales", "Expenses"}.issubset(df.columns):
            if "Other Income" in df.columns:
                df["Operating Profit"] = df["Sales"] - df["Expenses"] + df["Other Income"]
        # Missing source data stays missing. This also makes all derived calculations safe.
        needed = set(REQUIRED_COLUMNS + expense_fields + list(GROWTH_COLUMNS) + ['Expenses', 'Other Assets', 'Receivables', 'Cash & Bank'])
        for column in sorted(needed - set(df.columns)):
            df[column] = np.nan
        df.replace([np.inf, -np.inf], np.nan, inplace=True)
        equity = df["Equity Share Capital"] + df["Reserves"]
        df["Profit_Margin"] = _safe_divide(df["Net profit"], df["Sales"])
        df["Operating_Margin"] = _safe_divide(df["Operating Profit"], df["Sales"])
        df["ROE"] = _safe_divide(df["Net profit"], equity)
        df["ROA"] = _safe_divide(df["Net profit"], df["Total Assets"])
        df["Debt_to_Equity"] = _safe_divide(df["Borrowings"], equity)
        df["Debt_Equity_Ratio"] = df["Debt_to_Equity"]
        df["Debt_Ratio"] = _safe_divide(df["Borrowings"], df["Total Assets"])
        df["Interest_Coverage"] = _safe_divide(df["Profit before tax"], df["Interest"] + 1)
        df["Working_Capital_Ratio"] = _safe_divide(df["Cash & Bank"], df["Total Liabilities"] + 1)
        df["Asset_Utilization"] = _safe_divide(df["Sales"], df.get("Other Assets", np.nan))
        df["Receivable_Ratio"] = _safe_divide(df.get("Receivables", np.nan), df["Sales"])
        df["Inventory_Ratio"] = _safe_divide(df.get("Inventory", np.nan), df["Sales"])
        df["Expense_Ratio"] = _safe_divide(df["Expenses"], df["Sales"])
        df["Total Expenses"] = df["Expenses"]
        df["gross_margin"] = _safe_divide(df["Sales"] - df["Expenses"], df["Sales"])
        df["Depreciation_Ratio"] = _safe_divide(df["Depreciation"], df["Total Assets"])
        df["Operating_CF_Ratio"] = _safe_divide(df["Cash from Operating Activity"], df["Sales"])
        df["Cash_to_Debt"] = _safe_divide(df["Cash & Bank"], df["Borrowings"] + 1)
        df["Cash_Margin"] = _safe_divide(df["Cash from Operating Activity"], df["Net profit"])
        for source, target in GROWTH_COLUMNS.items():
            if source in df.columns:
                df[target] = df.groupby("Company")[source].pct_change(fill_method=None)
                df.loc[df.groupby('Company')['Year'].diff().ne(1), target] = np.nan
        df["Revenue_CAGR_3Y"] = df.groupby("Company")["Sales"].transform(self._cagr)
        df["Profit_CAGR_3Y"] = df.groupby("Company")["Net profit"].transform(self._cagr)
        df["Revenue_Volatility"] = df.groupby("Company")["Sales"].transform(lambda x: x.rolling(3, min_periods=1).std())
        df["Profit_Volatility"] = df.groupby("Company")["Net profit"].transform(lambda x: x.rolling(3, min_periods=1).std())
        df["Operating_CF_Volatility"] = df.groupby("Company")["Cash from Operating Activity"].transform(lambda x: x.rolling(3, min_periods=1).std())
        df.replace([np.inf, -np.inf], np.nan, inplace=True)
        # Separate rule features preserve the saved model's existing input definitions.
        def derive(name, numerator, denominator):
            if name not in df.columns:
                df[name] = _safe_divide(numerator, denominator)
        derive('Equity_Ratio', equity, df['Total Assets'])
        derive('Interest_Coverage_Ratio', df['Profit before tax'] + df['Interest'], df['Interest'])
        derive('Asset_Utilization_Ratio', df['Sales'], df['Total Assets'])
        derive('effective_tax_rate', df['Profit before tax'] - df['Net profit'], df['Profit before tax'])
        if 'Gross Profit' in df:
            derive('Gross_Profit_Margin', df['Gross Profit'], df['Sales'])
        if 'Cost of Goods Sold' in df:
            derive('Gross_Profit_Margin', df['Sales'] - df['Cost of Goods Sold'], df['Sales'])
            derive('inventory_turnover', df['Cost of Goods Sold'], df['Inventory'])
            derive('dio', 365 * df['Inventory'], df['Cost of Goods Sold'])
        if 'Credit Sales' in df:
            derive('receivables_turnover', df['Credit Sales'], df['Receivables'])
            derive('dso', 365 * df['Receivables'], df['Credit Sales'])
        numeric_cols = [c for c in df.columns if c not in ID_COLUMNS + ['Report Date']]
        df[numeric_cols] = df[numeric_cols].round(4)
        df.attrs['source_columns'] = source_columns
        df.attrs['invalid_numeric'] = invalid_numeric
        return df.sort_values(["Company", "Year"]).reset_index(drop=True)

    def _cagr(self, series: pd.Series, years: int = 3) -> pd.Series:
        result = np.full(len(series), np.nan)
        values = series.values
        for i in range(years, len(values)):
            start, end = values[i - years], values[i]
            result[i] = ((end / start) ** (1 / years)) - 1 if start > 0 and end > 0 else np.nan
        return pd.Series(result, index=series.index)

    def _rules(self):
        loaded = []
        for _, module_name, is_pkg in pkgutil.iter_modules(rules_pkg.__path__):
            # Retain retired definitions for old artifacts, but do not double-count
            # BS-001 and IS-010 in new runs.
            if is_pkg or module_name.startswith("__") or module_name in {"factory", "rule_led_001", "rule_tr_002"}:
                continue
            module = importlib.import_module(f"audit_engine.rules.{module_name}")
            if hasattr(module, "RULE"):
                loaded.append(module.RULE)
        return sorted(loaded, key=lambda rule: rule.spec.rule_id)

    def _run_rules(self, df: pd.DataFrame) -> dict[str, Any]:
        rows = []
        config = {
            "required_columns": REQUIRED_COLUMNS,
            "tolerance": 0.01,
            "minimum_history": 3,
            "z_score": 3.0,
            "ratio_limits": {"Debt_Equity_Ratio": 2.0, "Debt_Ratio": 0.7},
        }
        loaded_rules = self._rules()
        for index in df.index:
            for rule in loaded_rules:
                try:
                    result = rule.evaluate(df, index, config)
                    observed = {k: _finite_value(v) for k, v in (result.observed or {}).items()}
                    rows.append({
                        "Company": result.company, "Year": result.year, "Rule ID": result.rule_id,
                        "Rule Name": rule.spec.name, "Group": rule.spec.group, "Category": rule.spec.category,
                        "Severity": result.severity.value, "Status": result.status.value,
                        "Message": self._rule_message(result.status.value, rule.spec, observed, result.message),
                        "Observed": observed, "Recommendation": rule.spec.recommendation, "Risk Impact": rule.spec.risk_impact,
                        "Formula": rule.spec.formula, "Threshold": rule.spec.threshold,
                        "Evaluation Detail": self._evaluation_detail(rule.spec, config) if result.status.value in {'pass', 'fail'} else result.message,
                    })
                except Exception as exc:
                    row = df.loc[index]
                    rows.append({"Company": row.get("Company"), "Year": int(row.get("Year", 0)), "Rule ID": rule.spec.rule_id, "Rule Name": rule.spec.name, "Group": rule.spec.group, "Category": rule.spec.category, "Severity": rule.spec.severity.value, "Status": "error", "Message": str(exc), "Observed": {}, "Recommendation": rule.spec.recommendation, "Risk Impact": rule.spec.risk_impact})
        rule_df = pd.DataFrame(rows)
        scores = self._risk_scores(rule_df)
        return {"summary": self._rule_summary(rule_df), "risk_scores": _records(scores), "rows": rows, "violations": [r for r in rows if r["Status"] == "fail"]}

    def _evaluation_detail(self, spec, config):
        logic = spec.validation_logic
        if logic in {'accounting_equation', 'cash_delta_tieout', 'reserve_rollforward', 'ocf_reconciliation_proxy'}:
            return f"The absolute reconciliation difference must not exceed {config['tolerance']} in the supplied financial units. See the recorded difference and prior-period input below."
        if logic == 'financing_plausibility':
            return f"Flagged when the absolute difference exceeds the larger of {config['tolerance']} and {config['z_score']} times the absolute financing cash flow. This is a simplified financing proxy."
        if logic in {'config_max', 'config_min'}:
            direction = 'upper' if logic == 'config_max' else 'lower'
            return f"Configured {direction} limit for {spec.required_metrics[0]}: {config['ratio_limits'][spec.required_metrics[0]]}."
        if logic in {'declining_trend', 'increasing_trend', 'sustained_negative'}:
            return f"Requires {config['minimum_history']} consecutive annual observations with no missing values. Directional trends require a strict change each year."
        if logic in {'feature_zscore', 'outlier', 'feature_volatility', 'common_size_shift', 'margin_instability', 'expense_spike', 'interest_reasonableness', 'cash_flow_composition'}:
            return f"Flagged when the absolute robust deviation score exceeds {config['z_score']} using available same-year observations."
        return 'This check tests the stated sign or financial relationship; it does not use an additional numerical cutoff.'

    def _rule_message(self, status: str, spec: Any, observed: dict[str, Any], fallback: str) -> str:
        if status == "pass":
            return "Passed: required relationship is within the expected range."
        if status == "skipped":
            return fallback.replace("[", "").replace("]", "").replace("'", "")
        parts = [f"Failed because {spec.name.lower()} triggered."]
        if observed:
            vals = ", ".join(f"{k}={v}" for k, v in observed.items() if v is not None)
            if vals:
                parts.append(f"Evidence: {vals}.")
        parts.append(f"Expected: {spec.threshold}.")
        return " ".join(parts)

    def _rule_summary(self, rule_df: pd.DataFrame) -> dict[str, Any]:
        counts = rule_df["Status"].value_counts().to_dict()
        sev = rule_df[rule_df["Status"] == "fail"]["Severity"].value_counts().to_dict()
        return {"total": len(rule_df), "passed": int(counts.get("pass", 0)), "failed": int(counts.get("fail", 0)), "skipped": int(counts.get("skipped", 0)), "errors": int(counts.get("error", 0)), "severity": sev}

    def _risk_scores(self, rule_df: pd.DataFrame) -> pd.DataFrame:
        out = []
        for (company, year), data in rule_df.groupby(["Company", "Year"]):
            evaluated = data[data['Status'].isin(['pass', 'fail'])]
            coverage = len(evaluated) / len(data) if len(data) else 0
            max_score = sum(SEVERITY_WEIGHTS.get(r['Severity'], 0) * CATEGORY_WEIGHTS.get(str(r['Category']).lower(), 1.0) for _, r in evaluated.iterrows())
            failed = data[data["Status"] == "fail"]
            obtained = sum(SEVERITY_WEIGHTS.get(r["Severity"], 0) * CATEGORY_WEIGHTS.get(str(r["Category"]).lower(), 1.0) for _, r in failed.iterrows())
            risk = round((obtained / max_score) * 100, 2) if max_score and coverage >= MIN_RULE_COVERAGE else None
            level = "Unavailable" if risk is None else "Low" if risk <= 20 else "Moderate" if risk <= 40 else "Significant" if risk <= 60 else "High" if risk <= 80 else "Critical"
            out.append({"Company": company, "Year": int(year), "Passed Rules": int((data["Status"] == "pass").sum()), "Failed Rules": int((data["Status"] == "fail").sum()), "Skipped Rules": int((data["Status"] == "skipped").sum()), "Critical Failures": int(((failed["Severity"] == "Critical")).sum()), "High Failures": int(((failed["Severity"] == "High")).sum()), "Medium Failures": int(((failed["Severity"] == "Medium")).sum()), "Low Failures": int(((failed["Severity"] == "Low")).sum()), "Obtained Score": round(obtained, 2), "Maximum Score": round(max_score, 2), "Risk Score": risk, "Risk Level": level})
            out[-1].update({'Evaluated Rules': len(evaluated), 'Total Rules': len(data), 'Coverage Percent': round(coverage * 100, 2), 'Coverage Note': 'Risk reflects evaluated checks only; classification requires at least 50% rule coverage.'})
        return pd.DataFrame(out)

    def _run_ml(self, df: pd.DataFrame) -> dict[str, Any]:
        artifacts = Path(__file__).resolve().parents[1] / "models" / "ml_artifacts"
        model = joblib.load(artifacts / "isolation_forest.pkl")
        scaler = joblib.load(artifacts / "robust_scaler.pkl")
        feature_columns = list(joblib.load(artifacts / "feature_columns.pkl"))
        imputer = joblib.load(artifacts / "imputer.pkl")
        X = df.reindex(columns=feature_columns).apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
        missing = X.columns[X.isna().all()].tolist()
        coverage = X.notna().mean(axis=1)
        # A row with no observed model feature would only be a prediction about
        # training medians, not about this company or year.
        eligible = X.notna().any(axis=1)
        predictions, decisions, explanations = {}, {}, {}
        explanation_error = 'No observed model features are available to explain.'
        missing_before = int(X.loc[eligible].isna().sum().sum())
        if eligible.any():
            filled = pd.DataFrame(imputer.transform(X.loc[eligible]), columns=X.columns, index=X.loc[eligible].index)
            scaled = pd.DataFrame(scaler.transform(filled), columns=X.columns, index=filled.index)
            predictions = dict(zip(filled.index, model.predict(scaled)))
            decisions = dict(zip(filled.index, model.decision_function(scaled)))
            try:
                from app.services.ml_explanations import explain_rows
                explanations = explain_rows(model, scaler, imputer, X, filled, artifacts, self.checkpoint)
            except (ImportError, ValueError, RuntimeError):
                logging.getLogger(__name__).exception('SHAP explanation unavailable')
                explanation_error = 'SHAP could not be computed or verified. The prediction is available, but its feature attribution is unavailable.'
        rows = []
        for i, row in df.iterrows():
            available = i in predictions
            missing_for_year = X.columns[X.loc[i].isna()].tolist()
            reduced = available and bool(missing_for_year)
            low_coverage = available and coverage.loc[i] < MIN_ML_COVERAGE
            reason = ('No observed ML features for this year.') if not available else ('Less than 80% of model features were observed. Missing inputs were filled with saved training medians; treat this prediction cautiously.' if low_coverage else 'Missing features were filled with saved training medians for ML only. Interpret this prediction with reduced coverage.' if reduced else '')
            rows.append({"Company": row["Company"], "Year": int(row["Year"]), "Prediction": ("Anomaly" if predictions[i] == -1 else "Normal") if available else "Unavailable", "Decision Score": round(float(decisions[i]), 6) if available else None, "Anomaly Score": round(float(-decisions[i]), 6) if available else None, "Evidence": self._feature_evidence(df, i, feature_columns) if available else [], 'Coverage Percent': round(float(coverage.loc[i]) * 100, 2), 'Coverage Status': 'Unavailable' if not available else 'Low coverage' if low_coverage else 'Reduced coverage' if reduced else 'Full coverage', 'Missing Features': missing_for_year, 'Imputed Features': missing_for_year if available else [], 'Imputed Values': len(missing_for_year) if available else 0, 'Reason': reason})
            rows[-1]['SHAP'] = explanations.get(i, {'status': 'unavailable', 'reason': explanation_error if available else 'No observed model features are available to explain.'})
            rows[-1]['Evidence Method'] = 'Descriptive deviation within this upload; not model attribution'
        scored = len(predictions)
        reduced_rows = sum(r['Coverage Status'] in {'Reduced coverage', 'Low coverage'} for r in rows)
        low_coverage_rows = sum(r['Coverage Status'] == 'Low coverage' for r in rows)
        status = 'unavailable' if not scored else 'partial' if scored < len(rows) else 'reduced_coverage' if reduced_rows else 'completed'
        reason = ('No years had an observed ML feature.') if not scored else (f'{reduced_rows} of {scored} scored years used saved training medians for missing ML features; {low_coverage_rows} years had less than 80% observed features. These predictions have reduced coverage.' if reduced_rows else 'All model features were observed in scored years.')
        imputed_features = [c for c in feature_columns if any(c in r['Imputed Features'] for r in rows)]
        return {"summary": {"records": scored, 'total_records': len(rows), 'unavailable_records': len(rows) - scored, 'reduced_coverage_records': reduced_rows, 'low_coverage_records': low_coverage_rows, 'status': status, 'reason': reason, 'missing_features': missing, 'imputed_features': imputed_features, 'coverage_percent': round(float(coverage.mean()) * 100, 2), "anomalies": sum(1 for r in rows if r["Prediction"] == "Anomaly") if scored else None, "missing_values_imputed": missing_before}, "rows": rows}

    def _feature_evidence(self, df: pd.DataFrame, index: int, features: list[str]) -> list[dict[str, Any]]:
        numeric = df.reindex(columns=features).apply(pd.to_numeric, errors="coerce")
        med = numeric.median(numeric_only=True)
        std = numeric.std(numeric_only=True).replace(0, np.nan)
        row = numeric.loc[index]
        z = ((row - med).abs() / std).replace([np.inf, -np.inf], np.nan).sort_values(ascending=False)
        evidence = []
        for feature, score in z.dropna().head(5).items():
            evidence.append({"feature": feature, "value": _finite_value(row[feature]), "client_median": _finite_value(med[feature]), "deviation": _finite_value(score)})
        return evidence

    def _build_xai(self, df: pd.DataFrame, rules: dict[str, Any], ml: dict[str, Any]) -> dict[str, Any]:
        scores = {(r["Company"], int(r["Year"])): r for r in rules["risk_scores"]}
        ml_rows = {(r["Company"], int(r["Year"])): r for r in ml["rows"]}
        violations = rules["violations"]
        out = []
        for _, row in df.iterrows():
            key = (row["Company"], int(row["Year"]))
            year_violations = [v for v in violations if (v["Company"], int(v["Year"])) == key]
            score = scores.get(key, {})
            pred = ml_rows.get(key, {})
            recs = []
            if score.get("Risk Level") in {"High", "Critical", "Significant"}:
                recs.append("Prioritize substantive testing for this year and reconcile high-severity rule evidence with source schedules.")
            if pred.get("Prediction") == "Anomaly":
                recs.append("Perform analytical review over the ML evidence features and obtain management explanations for unusual movements.")
            for v in year_violations[:3]:
                recs.append(v.get("Recommendation", "Investigate supporting evidence."))
            if pred.get('Prediction') == 'Unavailable' or score.get('Risk Score') is None:
                recs.append('Obtain the missing financial metrics before drawing an overall conclusion; unavailable checks are not passes.')
            elif pred.get('Coverage Status') in {'Reduced coverage', 'Low coverage'}:
                recs.append('Review the ML result alongside the observed metrics and obtain missing features where possible.')
            if not recs:
                recs.append("Continue standard audit procedures; no elevated hybrid signal was identified.")
            out.append({
                "Company": key[0], "Year": key[1], "Rule Risk Score": score.get("Risk Score"), "Rule Risk Level": score.get("Risk Level"),
                "ML Prediction": pred.get("Prediction"), "Decision Score": pred.get("Decision Score"), "Anomaly Score": pred.get("Anomaly Score"),
                "ML Coverage Percent": pred.get("Coverage Percent"), "ML Coverage Status": pred.get("Coverage Status"),
                "ML Imputed Features": pred.get("Imputed Features", []),
                "Violation Count": len(year_violations),
                "Highest Severity": self._highest_severity(year_violations),
                "Rule Evidence": year_violations,
                "ML Evidence": pred.get("Evidence", []),
                "SHAP": pred.get('SHAP'),
                "Explanation": self._xai_text(key[1], year_violations, score, pred),
                "Recommendations": list(dict.fromkeys(recs)),
            })
        return {"rows": out}

    def _highest_severity(self, rows: list[dict[str, Any]]) -> str | None:
        order = ["Critical", "High", "Medium", "Low"]
        severities = {r.get("Severity") for r in rows}
        return next((s for s in order if s in severities), None)

    def _xai_text(self, year: int, violations: list[dict[str, Any]], score: dict[str, Any], pred: dict[str, Any]) -> str:
        parts = [f"For {year}, rule-based risk is {score.get('Risk Score')}% ({score.get('Risk Level', 'Unavailable')})." if score.get('Risk Score') is not None else f"For {year}, risk classification is unavailable because rule coverage is insufficient."]
        parts.append(f"Evaluated {score.get('Evaluated Rules', 0)} of {score.get('Total Rules', 0)} checks ({score.get('Coverage Percent', 0)}% coverage).")
        parts.append(f"The rule engine found {len(violations)} failed checks.")
        if violations:
            parts.append("Key failed checks include " + "; ".join(f"{v['Rule ID']} - {v['Message']}" for v in violations[:3]))
        if pred.get('Prediction') == 'Unavailable':
            parts.append('ML assessment unavailable: ' + pred.get('Reason', 'Insufficient data.'))
        elif pred:
            parts.append(f"The Isolation Forest classified the year as {pred.get('Prediction')} with anomaly score {pred.get('Anomaly Score')}.")
            if pred.get('Coverage Status') in {'Reduced coverage', 'Low coverage'}:
                parts.append(f"ML used {pred.get('Coverage Percent')}% observed features ({pred.get('Coverage Status')}); saved training medians filled {pred.get('Imputed Values')} missing features: {', '.join(pred.get('Imputed Features', []))}.")
            explanation = pred.get('SHAP') or {}
            if explanation.get('status') == 'available':
                parts.append(explanation['summary'])
                parts.append('SHAP compares with a synthetic training-median profile; contributions explain model behavior, not fraud or causation.')
            else:
                parts.append(explanation.get('reason', 'SHAP was not recorded for this analysis.'))
        return " ".join(parts)

    def _build_report(self, analysis_id: int, df: pd.DataFrame, rules: dict[str, Any], ml: dict[str, Any], xai: dict[str, Any]) -> dict[str, Any]:
        scores = [r['Risk Score'] for r in rules['risk_scores'] if r['Risk Score'] is not None]
        missing_metrics = [c for c in df.columns if c not in ID_COLUMNS and df[c].isna().all()]
        limitations = []
        limitations.append('SHAP explains the anomaly margin relative to a synthetic training-median profile. It is approximate model attribution, not fraud probability or proof of causation.')
        if any((r.get('SHAP') or {}).get('status') != 'available' for r in ml['rows'] if r.get('Prediction') != 'Unavailable'):
            limitations.append('SHAP attribution is unavailable for one or more scored years; do not interpret descriptive movements as model explanations.')
        if missing_metrics:
            limitations.append('Unavailable metrics (not assumed zero or not applicable): ' + ', '.join(missing_metrics))
        if rules['summary']['skipped'] or rules['summary']['errors']:
            limitations.append(f"{rules['summary']['skipped']} checks skipped and {rules['summary']['errors']} checks errored. Risk uses evaluated checks only; years below 50% coverage are not classified.")
        if ml['summary']['status'] != 'completed':
            limitations.append('ML: ' + ml['summary']['reason'])
        if ml['summary'].get('imputed_features'):
            limitations.append('ML features filled with saved training medians (predictions have reduced coverage): ' + ', '.join(ml['summary']['imputed_features']))
        overview = {
            "analysis_id": analysis_id,
            "company": str(df["Company"].iloc[0]),
            "years": [int(y) for y in df["Year"].tolist()],
            "records": len(df),
            "features": len(df.columns),
            "rule_failures": rules["summary"]["failed"],
            "ml_anomalies": ml["summary"]["anomalies"],
            "average_risk_score": round(float(np.mean(scores)), 2) if scores and len(scores) == len(rules['risk_scores']) else None,
            'analysis_status': 'Completed with limitations' if limitations else 'Completed',
            'rule_coverage_percent': round(100 * (rules['summary']['passed'] + rules['summary']['failed']) / rules['summary']['total'], 2) if rules['summary']['total'] else 0,
            'ml_status': ml['summary']['status'],
        }
        return {"overview": overview, 'limitations': limitations, 'missing_metrics': missing_metrics, 'ml_summary': ml['summary'], "risk_scores": rules["risk_scores"], "rule_findings": rules["violations"], "ml_findings": ml["rows"], "xai": xai["rows"], "preprocessed_preview": _records(df)}

    def _generate_pdf(self, path: Path, report: dict[str, Any]) -> None:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        path.parent.mkdir(parents=True, exist_ok=True)
        styles = getSampleStyleSheet()
        doc = SimpleDocTemplate(str(path), pagesize=A4, title="FinSight Audit Report")
        story = [Paragraph("FinSight Audit Report", styles["Title"]), Spacer(1, 12)]
        overview = report["overview"]
        story.append(Paragraph(escape(f"Client: {overview['company']}"), styles["Heading2"]))
        story.append(Paragraph(f"Years: {min(overview['years'])} - {max(overview['years'])}", styles["Normal"]))
        risk_text = f"{overview['average_risk_score']}%" if overview['average_risk_score'] is not None else 'Unavailable'
        anomaly_text = overview['ml_anomalies'] if overview['ml_anomalies'] is not None else 'Unavailable'
        story.append(Paragraph(f"Rule failures: {overview['rule_failures']} | ML anomalies: {anomaly_text} | Average risk score: {risk_text}", styles["Normal"]))
        ml_status = str(overview.get('ml_status', 'N/A')).replace('_', ' ')
        story.append(Paragraph(f"{overview.get('analysis_status', 'Completed')} | Rule coverage: {overview.get('rule_coverage_percent', 'N/A')}% | ML: {ml_status}", styles['Normal']))
        ml_summary = report.get('ml_summary', {})
        if ml_summary:
            story.append(Paragraph(f"ML observed feature coverage: {ml_summary.get('coverage_percent', 'N/A')}% | Scored years: {ml_summary.get('records', 0)} of {ml_summary.get('total_records', 0)} | Missing feature values filled: {ml_summary.get('missing_values_imputed', 0)}", styles['Normal']))
        if report.get('limitations'):
            story.append(Paragraph('Analysis coverage and limitations', styles['Heading2']))
            for limitation in report['limitations']:
                story.append(Paragraph(escape(limitation), styles['BodyText']))
        story.append(Spacer(1, 12))
        self._pdf_table(story, "Risk Scores", report["risk_scores"], ["Year", "Risk Score", "Risk Level", "Coverage Percent", "Failed Rules", "Skipped Rules"])
        self._pdf_table(story, "Rule Findings", report["rule_findings"][:25], ["Year", "Rule ID", "Rule Name", "Severity", "Message"])
        self._pdf_table(story, "ML Findings", report["ml_findings"], ["Year", "Prediction", "Decision Score", "Anomaly Score", "Coverage Percent", "Imputed Values"])
        story.append(Paragraph("Explainable AI Findings and Recommendations", styles["Heading2"]))
        for row in report["xai"]:
            story.append(Paragraph(escape(f"{row['Year']}: {row['Explanation']}"), styles["BodyText"]))
            explanation = row.get('SHAP') or {}
            if explanation.get('status') == 'available':
                story.append(Paragraph(escape(f"SHAP anomaly margin: reference {explanation['base_value']:.6f} + total contributions {explanation['contribution_sum']:.6f} = {explanation['output_value']:.6f}. Above zero is flagged. These are score units, not probabilities."), styles['BodyText']))
                self._pdf_table(story, 'Largest SHAP contributions', [
                    {'Metric': item['label'], 'Input': item['model_value'], 'Source': 'Filled median' if item['imputed'] else 'Observed/derived',
                     'Reference': item['reference_value'], 'Contribution': round(item['contribution'], 6)}
                    for item in explanation['features'][:6]], ['Metric', 'Input', 'Source', 'Reference', 'Contribution'])
            story.append(Paragraph(escape("Recommendations: " + " ".join(row["Recommendations"])), styles["BodyText"]))
            story.append(Spacer(1, 8))
        doc.build(story)

    def _pdf_table(self, story: list[Any], title: str, rows: list[dict[str, Any]], columns: list[str]) -> None:
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
        styles = getSampleStyleSheet()
        story.append(Paragraph(title, styles["Heading2"]))
        cell_style = ParagraphStyle('table-cell', parent=styles['Normal'], fontSize=7, leading=9)
        header_style = ParagraphStyle('table-header', parent=cell_style, textColor=colors.white)
        data = [[Paragraph(escape(c), header_style) for c in columns]] + [[Paragraph(escape(str(row[c]) if row.get(c) is not None else 'Unavailable'), cell_style) for c in columns] for row in rows[:30]]
        widths = [451 / len(columns)] * len(columns)
        if 'Message' in columns:
            widths = [35, 45, 100, 50, 221]
        table = Table(data, colWidths=widths, repeatRows=1)
        table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#131b2e")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c6c6cd")), ("FONTSIZE", (0, 0), (-1, -1), 7), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story.append(table)
        story.append(Spacer(1, 12))

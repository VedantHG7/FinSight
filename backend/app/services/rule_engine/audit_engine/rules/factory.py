from __future__ import annotations
import math
import pandas as pd
from audit_engine.base import BaseRule
from audit_engine.models import RuleResult, RuleSpec, Severity, Status


def _z(value, values):
    values = pd.Series(values).dropna()
    if len(values) < 3 or pd.isna(value): return None
    median = values.median(); mad = (values - median).abs().median()
    return None if mad == 0 else 0.6745 * (value - median) / mad


def _company(row):
    value = row.get("Company", "")
    return "" if pd.isna(value) else str(value)


def _year(row):
    value = row.get("Year", 0)
    if pd.isna(value):
        return 0
    try:
        return int(value)
    except Exception:
        return 0


def _result(spec, row, status, message, observed=None):
    if status == Status.SKIPPED:
        message = f"Cannot evaluate: {message}"
    return RuleResult(
        spec.rule_id,
        status,
        spec.severity,
        _company(row),
        _year(row),
        message,
        observed or {}
    )


def _missing_values(vals):
    return [m for m, v in vals.items() if pd.isna(v)]


def _first_prior(frame, row, metric):
    prior = frame.loc[
        (frame.Company == row.Company) & (frame.Year == row.Year - 1),
        metric
    ].tail(1)
    if not len(prior) or pd.isna(prior.iloc[0]):
        return None
    return prior.iloc[0]


class DeclarativeRule(BaseRule):
    def __init__(self, spec): self.spec = spec
    def evaluate(self, frame, index, config):
        row = frame.loc[index]; logic = self.spec.validation_logic; tol = config["tolerance"];
        missing = [m for m in self.spec.required_metrics if m not in frame.columns]
        if missing: return _result(self.spec, row, Status.SKIPPED, f"Unavailable metrics: {missing}")
        vals = {m: row.get(m) for m in self.spec.required_metrics}
        if logic in {"config_min", "config_max"} and self.spec.required_metrics[0] not in config.get("ratio_limits", {}):
            return _result(self.spec, row, Status.SKIPPED, "No approved threshold configured", vals)
        if logic == "missing_required": failed = any(pd.isna(row.get(c)) or str(row.get(c)).strip() == "" for c in ("Company", "Year"))
        elif logic == "numeric_fields":
            invalid = frame.attrs.get("invalid_numeric", {}).get(index, [])
            failed = bool(invalid)
            vals["Invalid numeric fields"] = invalid
            for c in frame.columns:
                if c in {"Company", "Report Date"}:
                    continue
                value = row.get(c)
                if pd.isna(value):
                    continue
                try:
                    float(value)
                except Exception:
                    failed = True
                    break
        elif logic == "required_columns":
            required = config.get("required_columns")
            source_columns = frame.attrs.get("source_columns")
            if not required or source_columns is None:
                return _result(self.spec, row, Status.SKIPPED, "Source schema evidence unavailable")
            absent = sorted(set(required) - set(source_columns))
            vals["Missing source columns"] = absent
            failed = bool(absent)
        else:
            missing_values = _missing_values(vals)
            if missing_values:
                return _result(self.spec, row, Status.SKIPPED, f"Unavailable metric values: {missing_values}", vals)
            if logic == "negative_screen": failed = any((pd.notna(v) and v < 0) for v in vals.values())
            elif logic == "year_date_match":
                date = pd.to_datetime(row["Report Date"], errors="coerce")
                failed = pd.isna(date) or date.year != int(row["Year"])
            elif logic == "accounting_equation":
                vals.update({'Difference': row['Total Assets'] - row['Total Liabilities'], 'Tolerance': tol})
                failed = abs(vals['Difference']) > tol
            elif logic == "negative_equity": failed = row["Equity Share Capital"] + row["Reserves"] < 0
            elif logic in {"feature_zscore", "outlier", "feature_volatility", "common_size_shift", "margin_instability"}:
                scores = {metric: _z(row[metric], frame.loc[frame["Year"] == row["Year"], metric]) for metric in self.spec.required_metrics}
                if any(z is None for z in scores.values()):
                    return _result(self.spec, row, Status.SKIPPED, "Need at least three same-year observations and nonzero median absolute deviation", vals)
                failed = any(abs(z) > config["z_score"] for z in scores.values())
                vals.update({f"robust_z: {metric}": z for metric, z in scores.items()})
            elif logic == "config_max":
                vals['Upper limit'] = config['ratio_limits'][self.spec.required_metrics[0]]
                failed = row[self.spec.required_metrics[0]] > vals['Upper limit']
            elif logic == "config_min":
                vals['Lower limit'] = config['ratio_limits'][self.spec.required_metrics[0]]
                failed = row[self.spec.required_metrics[0]] < vals['Lower limit']
            elif logic == "negative_value": failed = pd.notna(row[self.spec.required_metrics[0]]) and row[self.spec.required_metrics[0]] < 0
            elif logic in {"declining_trend", "increasing_trend", "sustained_negative"}:
                metric = self.spec.required_metrics[0]
                window = frame.loc[(frame.Company == row.Company) & (frame.Year <= row.Year)].sort_values("Year").tail(config["minimum_history"])
                history = window[metric]
                if len(history) < config["minimum_history"] or history.isna().any() or not window.Year.diff().dropna().eq(1).all():
                    return _result(self.spec, row, Status.SKIPPED, f"Insufficient history for {metric}", vals)
                failed = (
                    history.diff().dropna().lt(0).all() if logic == "declining_trend"
                    else history.diff().dropna().gt(0).all() if logic == "increasing_trend"
                    else (history < 0).all()
                )
                vals.update({'History window': config['minimum_history'], 'History values': history.tolist()})
            elif logic == "expense_spike":
                prior_val = _first_prior(frame, row, "Total Expenses")
                if prior_val is None:
                    return _result(self.spec, row, Status.SKIPPED, "Unavailable prior-year Total Expenses", vals)
                z = _z(row["Total Expenses"], frame.loc[frame.Year == row.Year, "Total Expenses"])
                if z is None:
                    return _result(self.spec, row, Status.SKIPPED, "Insufficient same-year comparison data or zero dispersion", vals)
                vals["robust_z"] = z
                failed = z is not None and abs(z) > config["z_score"]
            elif logic == "growth_gap":
                left, right = self.spec.required_metrics
                if pd.isna(row[left]) or pd.isna(row[right]):
                    return _result(self.spec, row, Status.SKIPPED, f"Unavailable metric values: {left}, {right}", vals)
                failed = row[left] > 0 and row[right] < 0
            elif logic == "reserve_rollforward":
                prior_val = _first_prior(frame, row, "Reserves")
                if prior_val is None:
                    return _result(self.spec, row, Status.SKIPPED, "Unavailable prior-year Reserves", vals)
                failed = abs((row["Reserves"] - prior_val) - (row["Net profit"] - row["Dividend Amount"])) > tol
                vals.update({'Prior reserves': prior_val, 'Change in reserves': row['Reserves'] - prior_val, 'Profit less dividends': row['Net profit'] - row['Dividend Amount'], 'Reconciliation difference': (row['Reserves'] - prior_val) - (row['Net profit'] - row['Dividend Amount']), 'Tolerance': tol})
            elif logic == "cash_delta_tieout":
                prior_val = _first_prior(frame, row, "Cash & Bank")
                if prior_val is None:
                    return _result(self.spec, row, Status.SKIPPED, "Unavailable prior-year Cash & Bank", vals)
                failed = abs((row["Cash & Bank"] - prior_val) - row["Net Cash Flow"]) > tol
                vals.update({'Prior cash balance': prior_val, 'Change in cash': row['Cash & Bank'] - prior_val, 'Reconciliation difference': (row['Cash & Bank'] - prior_val) - row['Net Cash Flow'], 'Tolerance': tol})
            elif logic == "financing_plausibility":
                prior_val = _first_prior(frame, row, "Borrowings")
                if prior_val is None:
                    return _result(self.spec, row, Status.SKIPPED, "Unavailable prior-year Borrowings", vals)
                failed = abs(row["Cash from Financing Activity"] - (row["Borrowings"] - prior_val - row["Dividend Amount"])) > max(tol, abs(row["Cash from Financing Activity"]) * config["z_score"])
                vals.update({'Prior borrowings': prior_val, 'Debt change less dividends': row['Borrowings'] - prior_val - row['Dividend Amount'], 'Reconciliation difference': row['Cash from Financing Activity'] - (row['Borrowings'] - prior_val - row['Dividend Amount']), 'Allowed difference': max(tol, abs(row['Cash from Financing Activity']) * config['z_score'])})
            elif logic == "ocf_reconciliation_proxy":
                expected = row["Net profit"] + row["Depreciation"] + row["Other Operating Cash Adjustments"]
                difference = row["Cash from Operating Activity"] - expected
                vals.update({"Expected operating cash flow": expected, "Reconciliation difference": difference, "Tolerance": tol})
                failed = abs(difference) > tol
            elif logic == "dividend_reserves": failed = row["Dividend Amount"] > max(row["Reserves"], 0)
            elif logic == "interest_reasonableness":
                z = _z(row["Interest"], frame.loc[frame.Year == row.Year, "Interest"])
                if z is None:
                    return _result(self.spec, row, Status.SKIPPED, "Insufficient same-year comparison data or zero dispersion", vals)
                vals["robust_z"] = z
                failed = z is not None and abs(z) > config["z_score"]
            elif logic == "relationship_adverse":
                left, right = self.spec.required_metrics
                if pd.isna(row[left]) or pd.isna(row[right]):
                    return _result(self.spec, row, Status.SKIPPED, f"Unavailable metric values: {left}, {right}", vals)
                failed = row[left] > 0 and row[right] < 0
            elif logic == "ocf_below_profit":
                if pd.isna(row.get("Cash from Operating Activity")) or pd.isna(row.get("Net profit")):
                    return _result(self.spec, row, Status.SKIPPED, "Unavailable metric values: Cash from Operating Activity, Net profit", vals)
                failed = row["Cash from Operating Activity"] < row["Net profit"]
            elif logic == "cash_ocf_divergence":
                if pd.isna(row.get("Cash_Growth")) or pd.isna(row.get("Cash from Operating Activity")):
                    return _result(self.spec, row, Status.SKIPPED, "Unavailable metric values: Cash_Growth, Cash from Operating Activity", vals)
                failed = row["Cash_Growth"] < 0 and row["Cash from Operating Activity"] > 0
            elif logic == "cash_flow_composition":
                z = _z(row["Cash from Financing Activity"], frame.loc[frame.Year == row.Year, "Cash from Financing Activity"])
                if z is None:
                    return _result(self.spec, row, Status.SKIPPED, "Insufficient same-year comparison data or zero dispersion", vals)
                failed = z is not None and abs(z) > config["z_score"]
            else: return _result(self.spec, row, Status.SKIPPED, f"Unsupported logic: {logic}")
        return _result(self.spec, row, Status.FAIL if failed else Status.PASS, "Validation triggered" if failed else "Validation passed", vals)


def build_rule(spec): return DeclarativeRule(spec)

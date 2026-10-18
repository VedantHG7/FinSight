# Missing-metric regression checks

From `backend`, run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests use the repository's `client_data.xlsx`. The upload test removes the
inventory and raw-material source values in memory and runs the API against an
isolated SQLite database and temporary artifact directory. It does not modify
the original workbook or the PostgreSQL database.

## Coverage policy

- Missing financial values remain null in preprocessing, exports and rules.
  Missing values do not imply zero or sector non-applicability.
- Derived values require their inputs. Missing expense components do not produce
  a partial sum labeled as total expenses. Growth does not forward-fill gaps.
- Rule risk uses only pass/fail checks in its weighted denominator. At least
  50% of checks must be evaluated for a year's risk classification. An aggregate
  risk score is withheld if any year cannot be classified.
- ML uses the saved feature order, training imputer and scaler for every year
  with at least one observed model feature. Even wholly absent features are
  filled with saved training medians in the model input. The year is labeled
  `Reduced coverage` when any feature is filled, and `Low coverage` when less
  than 80% of features are observed. A year with no observed model features
  has no defensible prediction and is marked `Unavailable`.
- Imputation applies only to ML input, never to reported financial values,
  rule checks or explanation evidence. Reports list imputed features and
  coverage. Reduced-coverage predictions are signals, not calibrated confidence.
- The 50% rule-score threshold and 80% low-coverage label are operational
  settings in `analysis_service.py`, not calibrated confidence measures.
  The current model still has manufacturing-oriented features. Its predictions
  for other sectors require separate validation; no sector is guessed.
- Existing analyses retain their saved artifacts. Re-upload to apply the new
  policy. Supported workbook structure and file types remain unchanged.

## Workspace regression tests

The suite also exercises registration, cookie sessions, logout/expiry, CSRF checks,
organization isolation (including PDF/CSV downloads), role-bound invitations,
file limits and generated storage names, queue cancellation/retry, recovery after
lease expiry, source workbook cell references, review approval rules, and optimistic
concurrency. All automated backend tests use temporary databases and artifacts.

Use a Python runtime with the backend dependencies installed. On the current
Windows machine the Store Python 3.13 runtime works; the older .venv is blocked
by Application Control for some ML libraries.

Browser verification is available in frontend/tests/workspace.smoke.mjs. Start
the API, worker, and frontend first, then run npm --prefix frontend run test:workspace.
It uses a fresh QA workspace with a generated password, uploads client_data.xlsx,
checks refresh recovery and review persistence, and verifies desktop/mobile layout.
It leaves its local QA workspace and analysis in the database for inspection;
these are isolated from other accounts. It requires a Playwright-compatible Edge
installation (or set PLAYWRIGHT_CHANNEL to another installed browser channel).

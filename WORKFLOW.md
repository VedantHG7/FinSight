# FinSight workflow

## SHAP model explanations

New uploads include SHAP explanations of the actual Isolation Forest anomaly
margin. Open ML Anomaly Detection or Explainable AI, select a reporting year,
and inspect the signed feature contributions and suggested source checks.
Positive contributions push toward anomaly; negative contributions push away.
The reference is a synthetic profile of saved training medians, not an industry
benchmark. Filled inputs are labeled, and a score is not a fraud probability.

Older saved analyses remain unchanged. Upload the workbook as a new analysis to
generate SHAP; previous report files and review decisions remain preserved.
Details and verification commands are in docs/SHAP_EXPLANATIONS.md.

## Start the application

PostgreSQL must be running and backend/.env must contain your DATABASE_URL.
Use the working Python 3.13 installation with backend/requirements.txt installed.
The older backend/.venv can be blocked by Windows Application Control on this machine.

From the repository root, run ./start-local.ps1. It starts the local API, worker,
and frontend in hidden processes, with logs in output/services. You can pass
-PythonPath with the absolute path to a different configured Python executable.

Startup now verifies a prediction and SHAP explanation using the saved model
artifacts before launching services. The worker also performs this check before
claiming jobs. Run `python -m app.check_runtime` from `backend` to diagnose the ML
runtime independently. A failed check reports the dependency error and exits;
the HTTP health endpoint alone does not establish ML readiness.

On 10 October 2026, the previously observed Windows Application Control block on
SciPy's `levyst` extension was no longer reproducible. Imports, model predictions,
SHAP and all 55 backend tests passed with the existing Python 3.13 installation;
no Windows policy changes or dependency reinstall were needed. If the block
returns, ask the device administrator to review the reported package rather than
disabling Application Control.

Alternatively, keep these three terminals running:

1. In backend: python -m uvicorn main:app --host 127.0.0.1 --port 8000
2. In backend: python -m app.worker
3. In frontend: npm run dev -- --host 127.0.0.1

Open http://127.0.0.1:5173/app. The frontend proxies /api to the backend, keeping
session cookies and protected downloads on the same origin.

## Accounts and existing data

### Password recovery

The sign-in page has a **Forgot your password?** link. Recovery emails contain a
single-use link valid for 30 minutes. Resetting a password revokes all sessions and
requires sign-in again. Signed-in users can select **Password** in the workspace
header to change their password using the current one; this also signs out all
devices. Requests for unknown account emails receive the same public response as
requests for known accounts. Reset requests are rate limited.

Configure an SMTP relay in `backend/.env` before using email recovery:

```dotenv
PUBLIC_APP_URL=http://127.0.0.1:5173
SMTP_HOST=your-smtp-host
SMTP_PORT=587
SMTP_USERNAME=your-smtp-username
SMTP_PASSWORD=your-smtp-password
SMTP_FROM_EMAIL=your-verified-sender@example.com
SMTP_USE_TLS=true
SMTP_USE_SSL=false
```

For an SMTP relay on port 465, set `SMTP_USE_SSL=true` and `SMTP_USE_TLS=false`.
Use the actual HTTPS application URL for `PUBLIC_APP_URL` when hosted. If SMTP is
not configured, the recovery request reports that the feature is unavailable;
it does not claim an email was sent. Do not commit mail credentials to the repo.

For a Gmail sender, use `smtp.gmail.com` on port 587 with TLS. The account owner
must enable Google 2-Step Verification, create an app password for FinSight, and
enter it as `SMTP_PASSWORD` in `backend/.env`. Use the app password, not the
regular Google account password. Restart the API after updating `.env`.

Create your account at /register. Creating a workspace makes you its admin.
Team invitations are one-time, email-bound links expiring after three days;
share them manually with the intended new member. A user belongs to one workspace.

Admins can invite members, upload, and approve findings. Analysts can upload,
assign, investigate, and comment. Reviewers can investigate and approve findings;
they cannot upload, cancel, or retry analyses. Resolved and Accepted decisions
require a review note. Conflicting concurrent edits return 409 and require reload.

Older analyses are preserved but not assigned to a new registrant automatically.
After creating the intended admin account, a trusted local operator can run,
from backend:

    python -m app.import_legacy --email YOUR_ADMIN_EMAIL

This assigns only the old audit@finsight.local development user's analyses and
clients to that admin. The import is explicit and repeatable; it does not change
source files. Old analyses do not have source-cell provenance: re-upload to capture it.

## Persistent processing

Uploads return HTTP 202 with an analysis ID. The worker processes saved jobs;
refreshing, closing the browser, or signing out does not cancel them. Progress is
updated at completed pipeline checkpoints, not estimated elapsed time. Cancel
requests take effect at the next checkpoint, not in the middle of ML computation.

The PostgreSQL worker uses an advisory lock to serialize processing. Jobs hold a
90-second lease renewed every 20 seconds. If a worker dies, a new worker reclaims
the job after lease expiry, up to three interrupted attempts. Processing restarts
from the saved workbook. Failed and cancelled jobs support manual retry. Completed
analyses cannot be rerun in place, preserving reviewed evidence; use a new upload.
This version intentionally processes one workbook at a time on a shared filesystem.
SQLite is supported for isolated tests, not concurrent production workers.

The generated PDF remains the original analysis report. Review decisions and
comments are stored separately and appear in Finding review and the audit trail;
they do not silently change the original report or financial evidence.

## Deployment boundaries

For a hosted deployment, use HTTPS, set COOKIE_SECURE=true, configure explicit
BACKEND_CORS_ORIGINS, and serve /api through the same origin as the frontend.
Run the API and worker under a process supervisor, using the same database and
persistent artifact volume. Back up both together. API startup creates the additive
workspace tables; no existing table is dropped. Future schema changes need explicit
versioned migrations rather than relying on create_all to alter tables.

Passwords use scrypt; only hashes of opaque session tokens are stored. Sessions
expire after 12 hours and logout revokes the current session. Mutations require a
session CSRF token. Login/register attempts are rate limited. Production perimeter
limits should also bound request bodies before multipart parsing and overall traffic.
Email verification, password recovery, MFA/SSO, retention controls, and a formal
security assessment are follow-up work before broad public deployment.

## From workbook to report

1. Upload an `.xlsx` or `.xls` workbook. The current reader expects a `Data
   Sheet` with year columns and financial-statement sections. Each upload must
   identify one company, valid reporting years and at least one usable numeric
   financial metric.
2. Metric aliases are normalized, and available ratios and growth rates are
   calculated. An absent metric stays empty in the preprocessed CSV. It is not
   treated as a reported zero, and a derived metric is left empty when its
   inputs are missing.
3. Each audit rule runs independently when its source metrics are available.
   Otherwise it is marked `Skipped` with a reason. Rule risk uses only checked
   rules in its denominator, and each year shows its checked-rule coverage.
   The risk classification is withheld below 50% checked-rule coverage.
4. For each year, the ML step orders features exactly as the saved model expects.
   Missing feature values, including an entire missing metric, are filled with
   the model's saved training medians **only in the ML input**. The saved scaler
   then transforms that input and the Isolation Forest returns an anomaly
   prediction and score. A year with no real observed model feature is marked
   `Unavailable` because a prediction based entirely on training medians would
   contain no company-specific evidence.
5. A scored year is labeled `Full coverage` when all model features were
   observed, `Reduced coverage` when any value was filled, or `Low coverage`
   when less than 80% of model features were observed. The ML page lists the
   exact features filled for each year. Coverage is a data-completeness measure,
   **not** a calibrated prediction probability or accuracy score.
6. The XAI page combines available rule findings and the ML result. The report
   and PDF show rule coverage, ML coverage, missing metrics, filled ML features,
   skipped checks and limitations alongside the available findings.

The current saved ML model includes manufacturing-related features. Median
imputation lets other companies complete the workflow, but predictions for
companies with many structurally absent features should be treated as weaker
signals until the model is validated on those sectors. Re-upload a workbook to
produce new artifacts with this workflow; saved analyses do not recalculate.

## Check the implementation

From `backend`, run `python -m unittest discover -s tests -v`. From `frontend`,
run `npm run build`. The backend test suite includes a workbook with raw
material and inventory fields removed, a sparse workbook, and an upload through
report/PDF download using an isolated temporary database.

## Preview before analysis

New analysis now opens a workbook preview before queueing a job. The preview uses
our existing extraction and preprocessing rules, shows company, years, source
values and detected monetary units, and reports missing key metrics by year.
Invalid financial values include source-cell references. Missing Data Sheet,
company name, invalid dates and duplicate annual columns block confirmation.
Fix errors in Excel, select the corrected workbook and preview again. Missing
metrics and unspecified units can be acknowledged explicitly before proceeding.
Values are never rescaled by the preview. Other sheets are not analysed.

Preview uploads are temporary and create no clients or analysis jobs. The browser
sends the preview's SHA-256 fingerprint on confirmation; the API revalidates and
rejects changed files. Existing direct API uploads remain backward compatible.

Validation: backend/tests/test_upload_preview.py plus the preview integration test
in test_workspace.py; frontend/tests/upload-preview.smoke.mjs checks confirmation,
file replacement, invalid input, and desktop/mobile layouts with API fixtures.

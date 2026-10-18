# FinSight: accounts, user data and implementation documentation

As implemented on 3 October 2026. This document describes the local application and the recent UI, account, client-history, background-processing and finding-review work. It distinguishes working features from remaining deployment work. Configuration examples contain placeholders, not live credentials.

## 1. What is used for account data?

| Component | Current implementation |
| --- | --- |
| Account and application database | PostgreSQL, accessed through SQLAlchemy and the psycopg driver |
| API | Python FastAPI with Pydantic request validation |
| Browser application | React 18, React Router 6, Vite 5, Tailwind 3 and shared CSS |
| Password protection | Python `hashlib.scrypt`, with a fresh random salt per password |
| Authentication | Custom server-side sessions; an opaque token in an HttpOnly cookie |
| Workspace access | Membership-based authorization checked by the API |
| Background processing | Persistent PostgreSQL job records and a separate Python worker |
| Workbook and report storage | Local filesystem under `backend/runtime/analyses` by default |
| Financial processing | Existing pandas, NumPy, openpyxl, scikit-learn and joblib pipeline; ReportLab PDF generation |

There is no Firebase, Supabase, Auth0 or JWT authentication integration in this implementation. The queue uses the application database; Redis and Celery are not required. SQLite is used for isolated backend tests.

```mermaid
flowchart LR
    Browser[React browser application] -->|Session cookie and CSRF header| API[FastAPI]
    API -->|Users, workspaces, sessions, jobs and reviews| DB[(PostgreSQL)]
    API -->|Save workbook and serve protected downloads| Files[(Local artifact storage)]
    Worker[Python worker] -->|Claim jobs and update progress| DB
    Worker -->|Read workbooks and write results| Files
    Browser -->|Poll job status| API
```

## 2. User data collected and stored

Registration collects a full name, email address, password and workspace name. Invitation registration also carries an invitation token and joins the invited workspace. The password is converted into a salted hash before database storage.

| Table | Stored data | Purpose |
| --- | --- | --- |
| `users` | ID, unique email, password hash, full name, legacy role, active flag, creation/update timestamps | Account identity |
| `organizations` | ID, name, creation time | A workspace shared by a team |
| `memberships` | User ID, organization ID, workspace role | Workspace membership and permissions |
| `auth_sessions` | SHA-256 session-token hash, user ID, CSRF token, expiry | Server-side login sessions |
| `login_attempts` | ID, SHA-256 hashes of normalized email and request client address, timestamp | Persistent authentication throttling |
| `workspace_invitations` | Invitation-token hash, workspace ID, invited email, role, expiry, used flag | One-time team invitations |
| `clients` | ID, owning user ID, company name, timestamps | Client/company association |
| `analyses` | ID, user ID, client ID, original filename, stored file path, pipeline status, timestamps | Workbook analysis records |
| `analysis_jobs` | Analysis ID, job state/stage/progress, attempts, lease token/expiry, cancellation flag, error, workbook SHA-256, timestamps | Durable processing queue |
| `analysis_events` | Analysis ID, stage, status, message, details, creation time | Processing and review activity trail |
| `finding_reviews` | Analysis ID plus finding key, review status, assignee, version, last editor/time | Current review decision |
| `review_events` | Analysis ID, finding key, author, comment, before/after changes, creation time | Review history; changes are serialized JSON in a text column |

The existing `audit_findings` and `reports` models remain in the project. Current finding views read the generated JSON artifacts; reviewer decisions live separately in `finding_reviews` and `review_events`.

Key relationships:

- Each user currently belongs to **one workspace**. `memberships.user_id` is the primary key, so multiple memberships per account are not supported.
- Workspace permissions come from `memberships.role`. The older `users.role` field is not the authority for these permissions.
- An analysis belongs to a user and client. Workspace ownership is determined through the analysis user's membership, rather than a direct organization column on the analysis.
- A finding review is uniquely identified by its analysis ID and finding key.

Names, emails, company names, comments and financial files are not encrypted by the application at rest. Password hashing and token hashing protect those specific credentials; they do not encrypt the entire database. Hashed email/address identifiers are pseudonymous identifiers, not guaranteed anonymous data.

## 3. Registration, login and session behavior

### Registration

1. The API trims and lowercases the email and checks its format. This does not verify ownership of the mailbox.
2. Passwords must contain at least 12 characters; the request schema permits up to 256 characters.
3. Full name is required, with a request limit of 120 characters. Workspace names are limited to 160 characters.
4. Public registration creates a new workspace and makes the account its admin.
5. Invitation registration validates the token, email, expiry and unused state, then grants the invitation's workspace and role.
6. Email addresses are globally unique. Successful registration signs the user in immediately.

### Password storage

The stored format is `scrypt$<salt>$<derived-key-in-hex>`. A random salt is generated with `secrets.token_hex(16)`. Scrypt uses `n=32768`, `r=8`, `p=3` and a 64 MiB memory ceiling. Verification uses `hmac.compare_digest`.

Plaintext passwords are not saved in the application database or returned in API responses. Scrypt parameters are currently defined in code; the stored string includes the scheme, salt and hash, rather than separate per-password parameter metadata. Although bcrypt appears in dependencies, the new account implementation uses scrypt.

### Login and throttling

Incorrect passwords, unknown users, inactive accounts and accounts without membership receive the same general login error. Unknown-user checks still perform scrypt work.

Login and registration share database-backed attempt counting over 15 minutes. A request is blocked when there are already at least 8 records for that email identifier or 40 for that client-address identifier. Requests that reach this check are recorded before credential validation; this is not exclusively a failed-password counter. Successful login clears records for that email. Older attempt records are cleaned up opportunistically.

The address comes from `request.client.host`; a hosted reverse proxy needs appropriate trusted-proxy configuration. This implementation is not a strict atomic distributed rate limiter.

### Session cookie

| Setting | Value |
| --- | --- |
| Name | `finsight_session` |
| Value | Random opaque token from `secrets.token_urlsafe(32)` |
| Database representation | SHA-256 hash of the token |
| Lifetime | Fixed 12 hours, with matching cookie Max-Age of 43,200 seconds |
| Browser protections | HttpOnly, SameSite=Lax, Path=/api |
| Secure flag | Controlled by `COOKIE_SECURE`; false for current local HTTP use |

The API checks session expiry, account activity and membership on authenticated requests. Login and registration replace the session represented by the current browser cookie. Other device sessions remain valid. Logout deletes the current session and cookie. There is no sliding session renewal or sign-out-all-devices feature. Expired rows are cleaned up when a session is issued.

Authenticated mutations require an `X-CSRF-Token` matching the session's random CSRF token. The token is stored in the session row and returned in the account response. When an Origin header is present, it must match the configured allowlist. Login and registration also perform this origin check.

The API adds `Cache-Control: no-store`, `X-Content-Type-Options: nosniff` and `Referrer-Policy: no-referrer` response headers.

### What is kept in the browser?

Account/workspace details and the CSRF token are kept in JavaScript memory. The authentication token is in the HttpOnly cookie, which application JavaScript cannot read. API calls use `credentials: 'include'`.

The browser's `localStorage` contains `finsight:analysisId` to remember the selected analysis. This ID is a navigation convenience and grants no access by itself. It is cleared on logout or a detected expired session. The application does not save passwords or authentication tokens in localStorage.

On reload, `/api/auth/me` restores account state from the cookie. Protected routes redirect unauthenticated users to login. An expired-session response clears the browser's account state.

## 4. Workspace access and team roles

All workspace members can see that workspace's analysis history, findings, reports and member list. The API checks workspace ownership for analysis endpoints, including PDF and CSV downloads. Requests for an analysis outside the current workspace return 404.

| Action | Admin | Analyst | Reviewer |
| --- | --- | --- | --- |
| View history, evidence, reports and members | Yes | Yes | Yes |
| Upload, cancel or retry analyses | Yes | Yes | No |
| Create team invitations | Yes | No | No |
| Assign findings and add comments | Yes | Yes | Yes |
| Set Open or Investigating | Yes | Yes | Yes |
| Transition to Resolved or Accepted | Yes | No | Yes |

Assignees must belong to the same workspace. Transitioning a finding to Resolved or Accepted requires a nonempty review note. An analyst can comment on or reassign an already resolved/accepted finding if its status remains unchanged. Any member may reopen a finding to Open or Investigating.

Invitations expire after three days, are single use and match a specific email. Only their token hashes are saved. The administrator receives a registration link to share manually; email delivery is not implemented. Existing registered emails cannot join another workspace through invitations.

Authorization is enforced in application queries. PostgreSQL row-level security and per-client permissions are not implemented. The current workflow does not enforce a separate preparer and approver; an admin/reviewer can approve their own finding.

## 5. Client history, file storage and processing

The workspace dashboard provides persistent history, text search, state filtering and pagination. History is scoped to the team rather than a shared development account. A pending upload initially uses a temporary client label. After workbook validation, the worker matches an existing company name within the workspace or creates a client record. Name matching is not legal-entity verification or deduplication.

### Upload validation and artifact locations

The endpoint accepts `.xlsx` and `.xls`, with a default 10 MiB upload limit. It strips path components from the submitted filename and generates a random physical filename. XLSX validation checks ZIP structure, `xl/workbook.xml`, at most 2,000 entries and at most 100 MiB of declared expanded content. XLS validation checks the OLE file signature. Full financial-data validation occurs in the worker.

The workbook reader expects a `Data Sheet`, a company name, valid years and usable numeric financial metrics. Accepting the file container does not guarantee that its data can be analyzed. Legacy `.xls` parsing additionally depends on the appropriate pandas Excel engine being installed; `xlrd` is not listed in the current requirements. `.xlsx` is the verified workflow.

Default locations, relative to the repository root:

```text
backend/runtime/analyses/
  incoming/<random-name>.xlsx        Original retained workbook
  <analysis-id>/
    raw/financial_dataset.csv
    raw/source_cells.json
    preprocessed/preprocessed_<id>.csv
    rules/rule_results.json
    ml/ml_results.json
    explainability/xai_results.json
    report/audit_report.json
    report/audit_report_<id>.pdf
```

`ANALYSIS_WORKSPACE_PATH` overrides the root. Relative paths resolve from the backend process's working directory. The `incoming` directory retains source workbooks; it is not automatically cleared after processing. Failed enqueue operations remove their partially saved upload. JSON results are written to temporary files and replaced atomically.

The workbook SHA-256 is stored with the job. It is a fingerprint, not a digital signature; automatic re-verification is not implemented. Downloads are served through authenticated API endpoints.

### Background jobs

Upload returns HTTP 202 and an analysis ID after saving the workbook and database records. A separate `python -m app.worker` process runs the pipeline. Refreshing, navigating away or logging out does not cancel the job.

| Behavior | Implementation |
| --- | --- |
| Queue | Persisted jobs, selected in creation order |
| Concurrency | PostgreSQL advisory lock serializes processing to one workbook at a time globally |
| Worker ownership | Per-claim random token and a 90-second lease, renewed every 20 seconds |
| Crash recovery | A running job with an expired lease can be reclaimed, up to three interrupted attempts |
| Recovery position | Processing restarts from the saved workbook, not from the last completed calculation |
| Ordinary processing failure | Marked Failed; user can request manual retry |
| Cancellation | Immediate for queued work; running work stops at a pipeline checkpoint |
| Manual retry | Failed/cancelled jobs requeue under the same ID, resetting attempt/progress state |
| Completed results | Cannot be rerun in place; upload again to create a new analysis |
| Progress | Stage milestones, not an estimate of elapsed or remaining time |

The frontend polls the current job approximately every two seconds and history every five seconds. Results and downloads require completion; attempting to open them early returns 409. Summary and activity information remain available during processing.

There is no queue notification service, automatic worker supervisor or horizontal processing throughput in this milestone. API and worker need the same database and accessible artifact storage.

## 6. Evidence drill-down and finding review

Rule findings use keys such as `rule:<year>:<rule-id>`; ML findings use `ml:<year>`. Review pages combine generated evidence with a separate editable review record.

Captured workbook provenance includes metric name, original label, year, statement, sheet, cell address and value. Source-cell references are shown for the selected finding's year. This is contextual evidence, not an exact dependency graph for each rule or multiyear calculation. Older artifacts without `source_cells.json` display an explanation; re-uploading captures provenance.

The UI supports searching findings, opening evidence from rule/report views, assigning an owner, setting a status and recording notes. It displays up to 200 matching findings at once and asks the user to narrow the search when necessary.

Review states are Open, Investigating, Resolved and Accepted. Comments are limited to 4,000 characters. Each save includes the current version. The server locks/checks the record and returns 409 if another user has changed it, preventing silent overwrite. A never-reviewed finding starts at version 0; each saved version increments by one.

Review history records the author, timestamp, comment and changes to status, assignee and version. It is append-only through the current application API, but is not a cryptographically immutable ledger. Review notes do not modify the source evidence or get inserted into the original generated PDF. Formal report sign-off, review attachments and a reviewed-report export are not implemented.

## 7. Frontend and UI changes

| Area | Delivered change |
| --- | --- |
| Visual consistency | Shared navy/teal palette, typography, spacing, cards, buttons and table treatments |
| Landing page | Financial product layout with clearly labeled illustrative chart data |
| Navigation | Consistent application shell, responsive navigation and mobile layouts |
| Accessibility | Visible keyboard focus, skip links and reduced-motion support |
| Icons | Local SVG icon component replacing reliance on external Material Symbols |
| Upload | Drag/drop, workbook validation, actionable error states and navigation to durable processing |
| Accounts | Registration/login, account restoration, protected routes and sign-out |
| Workspace | Searchable analysis history, processing states and team invitation page |
| Review | Evidence links, source-cell table, assignments, decisions and event history |
| API connection | Shared API client and Vite `/api` proxy targeting `127.0.0.1:8000` |

Inter and JetBrains Mono font imports still use Google Fonts, with system-font fallbacks. Typography is not entirely self-hosted.

The earlier upload “Failed to fetch” issue was diagnosed as the API being unavailable. The local launcher now starts the API, worker and frontend together. Network/API failures also have clearer browser messages; the backend must still be running.

Main routes:

| Route | Screen |
| --- | --- |
| `/`, `/onboarding` | Public product landing page |
| `/register`, `/login` | Account creation and login |
| `/app` | Workspace history |
| `/app/new` | New workbook upload |
| `/app/team` | Members and invitations |
| `/app/processing/:analysisId` | Persistent job status |
| `/app/reviews/:analysisId` | Finding evidence and review |
| `/app/analysis/:analysisId` | Financial analytics |
| `/app/rules/:analysisId`, `/app/ml/:analysisId`, `/app/xai/:analysisId` | Rule, ML and explanation views |
| `/app/trail/:analysisId`, `/app/audit-report/:analysisId` | Activity trail and report |

Existing missing-metric safeguards are preserved: missing financial values remain missing, rule checks can be skipped, and ML training-median imputation applies only to model input. Coverage labels and report limitations remain visible. Account work does not establish new financial-model accuracy or sector validation.

## 8. API reference

All paths below begin with `/api`. Authenticated state-changing requests require the session cookie and `X-CSRF-Token`. Registration/login perform origin checks without requiring a pre-existing session.

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/auth/register` | Create/join workspace and issue session; 201 |
| POST | `/auth/login` | Validate credentials and issue session |
| GET | `/auth/me` | Current user, organization and CSRF token |
| POST | `/auth/logout` | Revoke current session |
| GET | `/auth/members` | List current workspace members |
| POST | `/auth/invitations` | Admin creates invitation; 201 |
| POST | `/analysis/upload` | Multipart field `file`; queue analysis; 202 |
| GET | `/analysis?q=&state=&page=1` | Workspace history, 20 analyses per page |
| GET | `/analysis/{id}` | Analysis summary and job state |
| POST | `/analysis/{id}/cancel` | Request cancellation |
| POST | `/analysis/{id}/retry` | Requeue failed/cancelled job |
| GET | `/analysis/{id}/trail` | Analysis activity |
| GET | `/analysis/{id}/{view}` | Completed `analysis`, `rules`, `ml`, `xai` or `report` view |
| GET | `/analysis/{id}/preprocessed.csv` | Protected CSV download |
| GET | `/analysis/{id}/audit-report.pdf` | Protected PDF download |
| GET | `/analysis/{id}/findings` | Findings and current review state |
| GET | `/analysis/{id}/finding?key=...` | Evidence, source cells and review history |
| PUT | `/analysis/{id}/finding` | Save `key`, `status`, `assignee_id`, `comment`, `version` |
| GET | `/health` | Public lightweight API health response |

Common errors: 400 invalid workbook/invitation; 401 missing/expired login; 403 role/CSRF/origin rejection; 404 inaccessible/missing analysis; 409 conflicting review, duplicate email or unavailable state; 413 oversized workbook; 422 invalid input or missing decision note; 429 authentication throttling.

FastAPI's interactive reference is available at `http://127.0.0.1:8000/docs` while the backend runs. `/api/health` is not a complete database/worker-readiness check.

## 9. Files added or updated

Paths in this table are relative to the project root.

| File | Responsibility |
| --- | --- |
| `backend/app/core/security.py` | Password hashing, sessions, CSRF, role and ownership checks |
| `backend/app/api/routes/auth.py` | Registration, login, logout, account, members and invitations |
| `backend/app/db/models.py` | Additive workspace/session/job/review tables |
| `backend/app/api/routes/analysis.py` | Protected history, queued uploads, cancellation/retry, evidence, reviews and downloads |
| `backend/app/services/jobs.py` | Upload validation/storage, durable queue, lease handling and worker execution |
| `backend/app/worker.py` | Dedicated processing loop |
| `backend/app/services/analysis_service.py` | Processing saved analyses, checkpoints, provenance and atomic JSON output |
| `backend/app/import_legacy.py` | Explicit transfer of legacy development data to an intended admin |
| `backend/main.py`, `backend/app/core/config.py` | Authentication routing, CORS/security headers and cookie configuration |
| `frontend/src/api.js` | Shared cookie/CSRF API requests and session-expiry handling |
| `frontend/src/Accounts.jsx` | Auth context, route protection, registration/login and team UI |
| `frontend/src/Workspace.jsx` | History dashboard and processing status |
| `frontend/src/Reviews.jsx` | Evidence and review interface |
| `frontend/src/App.jsx` | Protected routing, upload and dashboard integration |
| `frontend/src/design-system.css`, `frontend/src/index.css`, `frontend/tailwind.config.js` | Shared visual system and responsive styling |
| `frontend/src/Icon.jsx`, `frontend/public/finsight.svg` | Local icons and brand asset |
| `frontend/src/pages/Onboarding.jsx`, `frontend/src/main.jsx`, `frontend/index.html` | Landing page and visual-system integration |
| `frontend/vite.config.js`, `frontend/package.json` | API proxy and workspace smoke-test command |
| `backend/tests/test_workspace.py`, `backend/tests/test_missing_metrics.py` | Account/workflow regressions and existing financial-data regressions |
| `frontend/tests/workspace.smoke.mjs` | Browser workflow and responsive checks |
| `start-local.ps1` | Local API, worker and frontend launcher |
| `WORKFLOW.md`, `backend/tests/README.md` | Operating and verification instructions |

## 10. Configuration and local startup

Use PostgreSQL and a Python environment with `backend/requirements.txt` installed. The verified local runtime is Python 3.13. New code uses `datetime.UTC`, requiring Python 3.11 or newer despite the older requirements-file comment mentioning 3.10. The older local `.venv` encountered Windows Application Control restrictions on this machine.

Relevant configuration is read from `backend/.env` when starting in the backend directory:

| Setting | Purpose |
| --- | --- |
| `DATABASE_URL` | PostgreSQL connection, e.g. `postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE` |
| `COOKIE_SECURE` | False for local HTTP; true for hosted HTTPS |
| `BACKEND_CORS_ORIGINS` | Explicit list of allowed frontend origins |
| `ANALYSIS_WORKSPACE_PATH` | Persistent workbook/artifact directory |
| `MAX_UPLOAD_SIZE` | Maximum saved upload bytes; default 10 MiB |
| `VITE_API_URL` | Optional frontend API-base override; default `/api` |

Existing `SECRET_KEY` and `ACCESS_TOKEN_EXPIRE_MINUTES` settings do not control this new session implementation. Sessions use random database-backed tokens and a fixed 12-hour expiry. Likewise, the new upload endpoint accepts Excel formats even though the older `ALLOWED_EXTENSIONS` setting also lists CSV.

From the repository root:

```powershell
.\start-local.ps1
```

An optional `-PythonPath` selects a configured Python executable. The launcher starts hidden processes and writes logs to `output/services`. It is a local development launcher, not a Windows service or automatic restart supervisor.

Alternatively, run these in three separate terminals:

```powershell
# Terminal 1, working directory: backend
python -m uvicorn main:app --host 127.0.0.1 --port 8000

# Terminal 2, working directory: backend
python -m app.worker

# Terminal 3, working directory: frontend
npm run dev -- --host 127.0.0.1
```

Open `http://127.0.0.1:5173/register` to create an account. There is no preset shared administrator login. The development proxy keeps `/api` requests and protected downloads on the frontend origin.

## 11. Schema initialization and existing analyses

API and worker startup use SQLAlchemy `Base.metadata.create_all()` to create missing tables. Existing tables and saved artifact paths are preserved. This is additive initialization, not a versioned migration system: `create_all()` does not alter existing columns. Alembic is installed as a dependency, but this milestone does not add a versioned migration history.

Legacy analyses are not automatically granted to the first new registrant. After the intended administrator creates an account, a trusted local operator can run this from `backend`:

```powershell
python -m app.import_legacy --email YOUR_ADMIN_EMAIL
```

The importer identifies the old development account and its development marker, moves its client/analysis ownership to the selected admin and disables the old account. Original files stay in place. Repeating the import after successful transfer leaves no additional legacy data to move. Older analyses do not gain source-cell provenance retrospectively.

## 12. Verification performed

The implementation milestone was checked with 20 passing backend unit tests, a successful frontend production build, and a browser smoke test against local PostgreSQL plus the running worker. Browser checks covered registration, upload, refresh during processing, report navigation, saved reviews, source-cell evidence, history/team screens and logout/login at desktop and mobile widths. No browser JavaScript errors or layout overflow were observed in those smoke checks.

These are implementation checks, not a penetration test, performance benchmark or financial-model certification. This documentation update does not rerun or replace those checks.

To reproduce backend checks from `backend`, using the configured Python runtime:

```powershell
python -m unittest discover -s tests -v
```

From the repository root:

```powershell
npm --prefix frontend run build
# Start the API, worker and frontend before the browser test:
npm --prefix frontend run test:workspace
```

Backend tests use temporary databases and artifact directories. Browser tests use a fresh local QA workspace and generated password, and leave their QA analysis in PostgreSQL for inspection. The browser test requires a Playwright-compatible installed Edge, or another installed channel selected through `PLAYWRIGHT_CHANNEL`.

## 13. Data lifecycle and remaining work

Account records, source workbooks, artifacts and review history persist across application restarts. There is no automatic account/analysis deletion, retention schedule or user data-export workflow. Session and attempt cleanup is opportunistic; invitation cleanup is not scheduled. Diagnostic logs can contain internal paths and exception details.

Backups must cover **both PostgreSQL and the artifact directory**, with a coordinated restore procedure. Copying only the database does not preserve workbook/report files. No automated backup or application-level storage encryption was added in this milestone.

Before broader hosted use, remaining work includes:

- HTTPS deployment, `COOKIE_SECURE=true`, explicit origins, a persistent shared volume, process supervision and monitored backups.
- Email verification/delivery, password recovery/change, MFA or SSO, and session/device management.
- Account deactivation, role editing, invitation revocation and workspace-switching workflows.
- Versioned database migrations and documented retention/deletion procedures.
- Per-client access rules if team-wide access is insufficient; independent review/sign-off if required.
- Worker readiness monitoring, resource limits and throughput improvements if processing volume grows.
- Reviewed-report export and more precise calculation-level evidence lineage.

The current milestone supplies a working local team workflow from account creation through reviewed findings. These remaining features should not be represented as already implemented or as evidence of regulatory compliance.

# FinSight

Financial workbook analysis with audit rules, machine learning anomaly detection,
explanations, and workspace reviews.

## Project layout

- `frontend/`: React application.
- `backend/`: Python API, processing worker, tests, and saved model artifacts.
- `deploy/` and `compose.yaml`: container deployment configuration.
- `docs/`: implementation and deployment notes.

## Local setup

1. Install Python 3.13, Node.js compatible with the frontend dependencies, and PostgreSQL.
2. Install backend dependencies with `python -m pip install -r backend/requirements.txt`.
3. Copy `backend/.env.example` to `backend/.env`, then set your local database
   credentials and a random secret. Create the `finsight_db` database in PostgreSQL.
4. From `frontend/`, run `npm ci`.
5. Follow [WORKFLOW.md](WORKFLOW.md) to start the API, worker, and frontend.

Environment files, logs, databases, uploaded workbooks, and generated reports are
local data and must not be committed. The downloadable blank workbook template
and saved ML model artifacts are application assets and are included.

Some backend tests require a local `client_data.xlsx` at the project root. This
workbook is excluded from version control; supply an appropriate test workbook
before running those tests. See [backend/tests/README.md](backend/tests/README.md).

## Deployment

See [the deployment guide](docs/ORACLE_FREE_DEPLOYMENT.md). Set production secrets
on the host; never put real credentials into the example environment files.

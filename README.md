# AMRIN

AMRIN is a React/Vite railway condition monitoring and maintenance console. The FastAPI backend provides persistent local development data, authentication, alerts, maintenance workflows, telemetry, and a protected future ML event ingestion contract. It does not control railway signalling or hardware.

## Windows development

Use two PowerShell terminals from the repository root. Keep local `.env` files private; do not overwrite an existing one.

### Terminal 1 — FastAPI backend

```powershell
Set-Location .\backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# Edit backend\.env and set a private JWT_SECRET_KEY before enabling authentication.
alembic upgrade head
python -m app.cli create-admin
python -m app.cli seed-demo
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

`create-admin` prompts for the first administrator; the password is hidden. Demo records use source `demo`. The seeded demo worker has no password. For the optional ML ingestion API, set a separate high-entropy `ML_INGEST_TOKEN` in `backend/.env`; see [the ML contract](docs/ml-integration-contract.md).

### Terminal 2 — React/Vite frontend

```powershell
# Run these commands from the repository root.
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# In root .env, set VITE_API_BASE_URL=http://localhost:8000/api and VITE_DEMO_AUTH=false.
npm ci
npm run dev
```

Restart Vite after changing `.env`. Keep `ML_INGEST_TOKEN`, JWT secrets, and all backend-only values out of root `.env` and every `VITE_` variable.

## Local demo mode

`mock-server/server.py` is a separate in-memory UI demo server. Run it instead of FastAPI when intentionally using the mock-data workflow and demo auth. Its seed resets on restart; it is not persistent or suitable for railway operations. `/simulation/simulator` is a standalone decision-support simulation and does not require a live ML service or railway connection. `/simulator` and `/simulation` redirect to that standalone page.

## Build

```powershell
npm run build
npm run lint
```

## Tests and database setup

The backend dependencies are pinned in `backend/requirements.txt`; its Alembic migrations create a fresh database. From the repository root, use the backend directory and run migrations before starting the API:

```powershell
Set-Location .\backend
python -m pip install -r requirements.txt
alembic upgrade head
python -m pytest
```

The test suite uses isolated temporary SQLite databases. The frontend uses the committed npm lockfile (`npm ci`) and has ESLint and Prettier scripts. CI runs the backend tests and the production Vite build on pushes and pull requests.

SQLite is the local persistent default in `backend/instance/`. Set backend `DATABASE_URL` to a PostgreSQL SQLAlchemy URL for deployment. Run Alembic migrations before starting the API. Never commit `.env`, databases, uploaded evidence, virtual environments, or generated build outputs.

## Main routes

The React app includes Command Center, Alerts, Live Map, Tasks, Hardware, and AI Detection. Access is role-gated by the API and UI. See [backend setup and API behavior](backend/README.md) and the [implementation handoff](docs/implementation-handoff.md).

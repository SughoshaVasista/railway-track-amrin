# AMRIN FastAPI backend

This backend provides the persistent SQLAlchemy schema, demo seed, server-side authentication/account approval, alert/task maintenance, and the device/sensor/map/dashboard/switch/model/AI read APIs. `mock-server/server.py` remains a separate in-memory demo.

## Windows PowerShell setup

From the repository root:

```powershell
Set-Location .\backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Set a private random `JWT_SECRET_KEY` in `backend/.env` before enabling authentication. Do not share it or put it in a `VITE_` variable. Then initialize the database, create the first administrator, optionally seed demo data, and start the API:

```powershell
alembic upgrade head
python -m app.cli create-admin
python -m app.cli seed-demo
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

`create-admin` prompts for a name, email, username, and password. The password is entered with hidden terminal input and is never printed. It refuses to create an account if any administrator already exists. Do not use the seeded worker as a login account; it intentionally has no password hash. `seed-demo` is idempotent: a second run inserts no duplicate sample records.

The API listens on `http://127.0.0.1:8000`; health is available at `/api/health`. SQLite is the persistent local default under `backend/instance/`. `DATABASE_URL` can use a PostgreSQL SQLAlchemy URL when the matching driver is installed. `JWT_ACCESS_TOKEN_MINUTES`, `CORS_ORIGINS`, `UPLOAD_FOLDER`, `MAX_CONTENT_LENGTH`, `ENVIRONMENT`, `ML_INGEST_TOKEN`, and `SENSOR_INGEST_TOKEN` are configurable through `backend/.env` or process environment. `SENSOR_INGEST_TOKEN` enables Raspberry Pi sensor ingestion; see [the simulator telemetry setup](../docs/raspberry-pi-telemetry.md).

## Authentication behavior

- `POST /api/auth/login` accepts `{ "username": "email-or-username", "password": "..." }` and returns a signed Bearer token plus the role/name/worker/city fields used by the frontend.
- `POST /api/auth/register` accepts the current signup shape. Every new account is a pending worker. Requests for `operator` or `admin` are recorded as requested roles for audit but never grant privileges.
- `GET /api/auth/me` validates the token and returns safe account fields.
- `POST /api/auth/forgot-password` and `POST /api/auth/reset-password` provide one-time, 30-minute reset links. Configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, and `FRONTEND_BASE_URL` to deliver mail. In development only, the reset link is written to the backend console when SMTP is unset. Responses do not reveal whether an account exists. Resetting a password invalidates earlier reset links and existing JWT sessions.
- `GET /api/users?limit=100&offset=0` returns paginated, non-secret profile data to admins. Password hashes and reset tokens are never returned. There is no API for retrieving passwords.
- `POST /api/users/{user_id}/reset-password` lets an authenticated non-demo admin set a new password when an account cannot receive email. It invalidates the user's sessions and reset links and records the action in the audit log.
- `GET /api/users/pending`, `POST /api/users/{user_id}/approve`, `POST /api/users/{user_id}/reject`, and `GET /api/workers` require an approved active admin account.
- Approval creates a stable worker ID. Rejected/pending users cannot sign in. API authorization checks the account's current database role and approval state for each request, so disabling or changing an account invalidates its access immediately.
- Public registration passwords require at least 10 characters; CLI administrator passwords require at least 12. Passwords use Argon2 hashes and are never included in API responses.

## Alerts, tasks, and evidence

Alert actions are administrator-only, validated against explicit lifecycle transitions, and written with `AlertHistory` and `EventLog` records. Task lists are limited to the authenticated worker; admins can list/filter all tasks. Task completion requires at least one repair evidence image. The database has a partial unique index preventing multiple open tasks for the same alert.

Evidence accepts JPEG, PNG, GIF, and WebP only. The upload is bounded by `MAX_CONTENT_LENGTH`, its file signature must match its declared MIME type, its stored name is randomized, and it is stored under `UPLOAD_FOLDER`. The private `GET /api/tasks/{task_id}/evidence/{evidence_id}` route checks task ownership/admin role; it never accepts a filesystem path or token in a URL. API clients must send the Bearer token in the `Authorization` header when retrieving an evidence image.

## Telemetry and simulation reads

Device, sensor, diagnostics, track, train, switch status, dashboard summary/event log, model status, and AI detection routes use database records. Sensor history is bounded to the most recent 1,000 rows and accepts `1h`, `6h`, `24h`, `7d`, and `30d` windows. Map routes are available to approved admins/workers; device/model/dashboard administration reads are admin-only. The model and detection endpoints report no live ML service until an actual integration reports data. Switch decisions are advisory simulation records only and never operate railway equipment. To let `train-sim/controller.py` submit a decision, set `AMRIN_API_TOKEN` in that process to an administrator's Bearer token; it is never put in a URL or checked into source.

The optional `POST /api/integrations/ml/events` endpoint accepts version 1 events from a separate ML service. Set a private `ML_INGEST_TOKEN` in `backend/.env` to enable it; it uses `X-ML-API-Key` and is independent from user JWT authentication. Ingestion is disabled when the token is missing, validates registered devices and bounded payloads, rejects image URLs/base64, and atomically records an alert, ML-origin event, and audit entries. It does not load a model or send device commands. See [`docs/ml-integration-contract.md`](../docs/ml-integration-contract.md) for payload and retry behavior.

For a safe manual local reset, stop Uvicorn first, make a backup if needed, then remove only `backend/instance/amrin.db` and its SQLite journal files from that directory. Re-run `alembic upgrade head`, create the first admin, and optionally run `python -m app.cli seed-demo`. Uploaded evidence is stored separately under `UPLOAD_FOLDER` and is not removed by a database reset.

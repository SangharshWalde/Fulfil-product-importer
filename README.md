# Fulfil Product Importer

A production-ready FastAPI application for importing CSV product data at scale with real-time progress, robust session management, CRUD operations, webhook notifications, and duplicate-safe upserts.

## Features

- Import large CSVs with batching and progress streaming (Server-Sent Events)
- Products CRUD with case-insensitive `sku` uniqueness
- Webhooks: create/update/delete and test, with last status tracking
- Robust SQLAlchemy session handling (safe rollback, no session corruption)
- Clean, responsive UI served from `/static` (works on desktop and mobile)
- Optional Celery integration for worker-based imports

## Tech Stack

- FastAPI, Uvicorn, Pydantic
- SQLAlchemy (SQLite or Postgres via `psycopg2-binary`)
- HTTPX for webhook calls
- Aiofiles for efficient file I/O
- Celery + Redis (optional)

## Quick Start (Local)

```bash
# Python 3.11 recommended
python -m venv .venv
. .venv/Scripts/activate  # Windows
# or: source .venv/bin/activate  # macOS/Linux

pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
# Open http://127.0.0.1:8000/
```

### Environment Variables

- `DATABASE_URL`
  - Default: SQLite file under `app/data.db` if unset
  - Local demo: `sqlite:////tmp/data.db` (ephemeral)
  - Recommended (free): Neon Postgres `postgres://<user>:<pass>@<host>:5432/<db>?sslmode=require`
- `USE_CELERY`
  - `false` by default (runs import in-process)
  - Set `true` with `CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND` to use workers
- `IMPORT_BATCH_SIZE`
  - Optional; default `1000`

## CSV Format

- Required header: `sku`
- Optional headers: `name`, `description`, `active`
- Invalid rows are skipped; import continues

## API Overview

- `GET /` — serves UI
- Products
  - `GET /products` — list (filters + pagination)
  - `POST /products` — create
  - `PUT /products/{id}` — update
  - `DELETE /products/{id}` — delete
  - `DELETE /products` — bulk delete
- Import
  - `POST /upload` — upload CSV and start import
  - `GET /jobs/{job_id}` — job status
  - `GET /jobs/{job_id}/events` — SSE stream for progress
- Webhooks
  - `GET /webhooks` — list
  - `POST /webhooks` — create
  - `PUT /webhooks/{id}` — update
  - `DELETE /webhooks/{id}` — delete
  - `POST /webhooks/{id}/test` — send test event and record result

## Deployment (Render + Neon Postgres)

- Create Neon Postgres and copy the connection string (`postgres://...`)
- Render Web Service settings:
  - Build: `pip install -r requirements.txt`
  - Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Environment:
  - `DATABASE_URL=<paste Neon connection string>`
  - `USE_CELERY=false`
  - Optional: `PYTHON_VERSION=3.11.9`
- For demo without DB: `DATABASE_URL=sqlite:////tmp/data.db` (data resets per deploy)

## Notes

- SQLite on free PaaS is best with an ephemeral path (e.g., `/tmp`). For persistence, use Postgres.
- Session handling is hardened: all writes commit safely or rollback and log without corrupting sessions.

## License

MIT
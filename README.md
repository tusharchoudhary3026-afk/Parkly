# Parkly Smart Parking

Software-only parking booking and operations platform. The feature scope follows `Smart_Parking_System_Feature_Scope_and_Workflow.pdf`; hardware control, ANPR, automatic penalties, and Phase 2 work are excluded.

## Run from VS Code

1. Open the `C:\Parkly` folder in VS Code and start Docker Desktop.
2. In the VS Code terminal, run `docker compose up -d --no-build`.
3. Open the website at http://localhost:3000 and API docs at http://localhost:8000/docs.

The local API source is mounted from `backend`, so code edits are used on the next API restart. This command uses the existing local Docker images. To follow API and web logs, run `docker compose logs -f api web` and press Ctrl+C to stop following them. To stop the site, run `docker compose down`; this keeps the local database volume.

For a fresh machine without the local images, copy `.env.example` to `.env`, set a private `JWT_SECRET`, and run `docker compose up --build`. If package downloads fail checksum verification, keep hash checking enabled and retry once the package index/download path is healthy.

The payment flow is a simulator and always displays **TEST MODE**. Seeded records are marked **SYNTHETIC**. Forecast output is an **ESTIMATE**.

On a fresh local database, the API startup applies migrations and creates the synthetic demo dataset. Demo-only staff accounts use `attendant@synthetic.test`, `manager@synthetic.test`, or `auditor@synthetic.test`; their shared demo password is `Synthetic-Demo-Only-2026!`. Do not reuse these accounts or credentials outside a local demo.

The location picker is an extension beyond the numbered PDF scope. It starts at Madhya Pradesh → Gwalior, supports cascading city/area/venue selection and search, and labels the seeded venues synthetic. Starter reference data is in `backend/app/seed_data/locations_in.py`; extend it only with verified names and keep demo venues labelled synthetic. “Other” submissions remain private to the submitting account until a manager reviews them with a reason. Shared location records do not grant a venue parking inventory; only an operator-managed lot with slots is bookable.

## Development

Backend: `cd backend; python -m venv .venv; .venv\\Scripts\\activate; pip install -e ".[dev]"; uvicorn app.main:app --reload`

Backend tests: `cd backend; pytest`. For acceptance tests requiring concurrency, run `docker compose --profile test up --build --abort-on-container-exit` against the PostgreSQL test database.

Run the full PostgreSQL acceptance suite against the mounted current source with `docker compose --profile test run --build --rm --volume "${PWD}/backend:/srv" --workdir /srv api-test`. Run Ruff without downloading packages from PyPI with `docker run --rm -v "${PWD}/backend:/io" -w /io ghcr.io/astral-sh/ruff:0.17.3 check app tests`.

Apply migrations: `cd backend; alembic upgrade head`. Seed demo data: `python -m app.seed`.

## Scope and claims

`CHECKLIST.md` maps every numbered PDF feature to its current state. `TEST_REPORT.md` records only checks that have actually been run. Provider-managed TLS and database encryption at rest are deployment settings and are not claimed for local development.

# Deployment notes

Local deployment uses `docker compose up --build`, PostgreSQL 16, FastAPI, and the Next.js app. Copy `.env.example` to `.env`; replace all local secrets before deployment. Never expose the compose database password or development event API key to the internet.

For a real deployment, use managed PostgreSQL with backups, TLS at the hosting provider, encryption-at-rest enabled, a secret manager, per-source event credentials, rate limiting at the edge, restricted CORS, monitoring, and a restore drill. Verify each provider setting before claiming TLS or storage encryption. These production controls have not been configured or verified by this repository.

Run migrations with `cd backend && alembic upgrade head`; seed only development databases with `python -m app.seed`. Avoid seeding production. Configure `DATABASE_URL`, `JWT_SECRET`, and `EVENT_API_KEY` through the deployment secret store. Configure independent event-source credentials with `EVENT_SOURCE_KEYS=source:key,...` in production. Payment remains TEST MODE; no real money is processed.

The API applies per-process sliding-window limits to authentication (10/minute), booking actions (30/minute), and event ingestion (120/minute). These in-memory limits protect a single local process; multi-replica production deployments must enforce shared limits at the gateway or with a shared store.

# End-to-end tests

Playwright drives the **real frontend** (Vite) against the **real FastAPI app** and a real Postgres.
Only two things are replaced, in `server.py`: retrieval (PostgresML is not available in CI) and the
LLM (no API key, no cost, deterministic text). Everything else is the code that ships: SSE streaming,
Markdown rendering, persistence, feedback, regenerate, search, export, filters, charts.

## Run locally

```bash
# 1. a DISPOSABLE database (the server applies migrations and inserts test rows)
docker compose exec db psql -U postgres -c "CREATE DATABASE e2e"      # adjust user/port to your .env

# 2. backend deps (once) and Playwright (once)
cd backend && uv sync && cd ..
cd frontend && npm install --legacy-peer-deps && cd ..
cd e2e && npm install && npx playwright install chromium

# 3. run
DATABASE_URL=postgresql://postgres:postgres@localhost:5433/e2e \
E2E_PYTHON=../backend/.venv/bin/python \
npx playwright test
```

Ports 8000 (API) and 3000 (frontend) must be free, so stop `docker compose` first, or the tests
will reuse the running servers (and then talk to your real database and LLM).

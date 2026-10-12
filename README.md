# BCB RAG

RAG chatbot over Banco Central do Brasil (BCB) regulations. It scrapes normativos from the BCB API, chunks them, embeds them inside PostgreSQL (PostgresML + pgvector) and answers questions in Portuguese or English with clickable citations to the original BCB page. The pipeline runs automatically every day, and everything it does is logged and visible in the UI.

See `bcb-rag-plan.md` for the full plan, `PHASE4.md` for the retrieval/answering notes and `PLANO_LOGS_PIPELINE.md` for the logging design.

## Features

- **Chat** with persistent conversations (history sidebar, reopen or delete past chats), PT/EN answers and `[n]` citation chips that show the passage used.
- **Hybrid retrieval:** exact match on the document number in the title (e.g. "Comunicado nº 34.977") combined with semantic search (pgvector cosine).
- **Documents dashboard:** live view (auto-refresh every 5 s) of every document in the database, with chunk and vectorization progress.
- **Logs page:** pipeline runs and events, plus a log of every question (retrieved chunks, latency, status).
- **Scheduled pipeline:** scrape → chunk → embed once a day, no manual commands.
- **CI:** GitHub Actions builds both images and publishes them to GHCR.

## Architecture

```
React (Vite, :3000) --> FastAPI (:8000) --> Anthropic API (answers)
                            |
                            v
              PostgreSQL + pgvector + PostgresML (:5433 on host)
                            ^
      pipeline service: scheduler -> scrape -> chunk -> embed (daily)
```

| Service | Description | Port |
|---|---|---|
| `db` | PostgresML image (Postgres 15, pgvector, `pgml.embed`) | 5433 (host) / 5432 (inside Docker) |
| `api` | FastAPI backend (hot reload; `backend/app` is bind-mounted) | 8000 |
| `pipeline` | Scheduler that runs scrape → chunk → embed daily | – |
| `frontend` | React 18 + TypeScript + Vite UI | 3000 |

Inside containers use `db:5432`; scripts run on your Mac (such as `check_docs.py`) use `localhost:5433`.

## Quick start

```bash
cp .env.example .env          # fill ANTHROPIC_API_KEY etc.
chmod -R a+rX backend/app     # the container user must be able to read the bind mount
docker compose up --build -d
docker compose exec api alembic upgrade head   # first run / after pulling new migrations
curl http://localhost:8000/api/health
```

Frontend: <http://localhost:3000>

## Configuration (`.env`)

```properties
POSTGRES_USER=postgresml
POSTGRES_PASSWORD=postgresml
POSTGRES_DB=postgresml
DATABASE_URL=postgresql://postgresml:postgresml@db:5432/postgresml

ANTHROPIC_API_KEY=your-anthropic-api-key
ANTHROPIC_MODEL=claude-haiku-5-5

EMBEDDING_MODEL=intfloat/multilingual-e5-base
EMBEDDING_DIM=768

TZ=America/Sao_Paulo

# Pipeline automation (see below)
PIPELINE_SCHEDULE_TIME=06:00
PIPELINE_TZ=America/Sao_Paulo
PIPELINE_SCRAPE_DAYS=2
PIPELINE_EMBED_BATCH_SIZE=32
PIPELINE_RUN_ON_START=false
```

Embeddings are generated inside Postgres by PostgresML, so no external embedding API key is needed.

## Data pipeline

### Automatic (default)

The `pipeline` service runs `app.worker.scheduler`, which executes scrape → chunk → embed every day at `PIPELINE_SCHEDULE_TIME` in `PIPELINE_TZ`.

| Variable | Default | Meaning |
|---|---|---|
| `PIPELINE_SCHEDULE_TIME` | `06:00` | Daily run time (HH:MM) |
| `PIPELINE_TZ` | `$TZ` or `America/Sao_Paulo` | Time zone for the schedule |
| `PIPELINE_SCRAPE_DAYS` | `2` | Days back to scrape each run (re-scraped documents are deduplicated by URL/hash) |
| `PIPELINE_EMBED_BATCH_SIZE` | `32` | Chunks per embedding batch |
| `PIPELINE_RUN_ON_START` | `false` | Also run once when the service starts |

Behaviour:

- A failing stage does not stop the next ones; chunk and embed also pick up any backlog from earlier runs.
- A Postgres advisory lock prevents two pipelines from running at the same time (scheduler vs. manual run).
- Every stage is recorded in `pipeline_runs` / `pipeline_events` and appears in **Logs → Execuções**.
- The containers must be running at the scheduled time. If your machine is off, that day's run is skipped.

```bash
docker compose logs -f pipeline      # shows "Next run at ..."
```

### Manual

```bash
# Whole pipeline once
docker compose exec pipeline python -m app.worker.pipeline --days 7

# Or one stage at a time
docker compose exec api python -m app.worker.scrape --days 30
docker compose exec api python -m app.worker.chunk
docker compose exec api python -m app.worker.embed --batch-size 32
```

Each stage exits with code 1 if any item failed, so it is safe to use in scripts.

Check what is in the database and what is vectorized:

```bash
python check_docs.py                         # on the Mac (localhost:5433)
docker compose exec api python check_docs.py # inside the container
```

It prints documents, chunks and vectorization status, then a summary of pipeline runs and query logs.

### Scraper sources (`backend/app/scraping/sources.py`)

| `source_name` | Document type |
|---|---|
| `bcb_comunicados_ccs` | Comunicado (query `CCS`) |
| `bcb_resolucoes` | Resolução BCB |
| `bcb_circulares` | Circular BCB |
| `bcb_instrucoes_normativas` | Instrução Normativa |

### Testing the RAG pipeline from the CLI

```bash
docker compose exec api python -m app.worker.test_rag --language pt
```

Runs sample questions and saves results to `rag_test_results_pt.json`.

## Frontend

Sidebar navigation:

| Page | What it shows |
|---|---|
| **Conversa** | Chat. The active conversation is remembered across reloads (`localStorage`) and stored server-side. |
| **Documentos** | Live dashboard: totals, % vectorized, per-type filter chips, search, paginated table with a vectorization bar per document. Auto-refreshes every 5 s (pausable). |
| **Logs** | **Execuções** (pipeline runs, expandable events, filters) and **Consultas** (every question: latency, status, retrieved chunks). |

Design: IBM Plex Sans + Source Serif 4, plain CSS tokens with automatic dark mode, PT/EN switcher.

## API

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Status, timestamp, embedding model |
| POST | `/api/chat` | Body: `question`, `language` (`pt`/`en`), optional `conversation_id`. Returns `answer`, `sources`, `retrieved_chunks`, `conversation_id`. Logged to `query_logs` and persisted. |
| GET | `/api/documents` | Latest ingested documents |
| GET | `/api/conversations` | List conversations (title, last update) |
| GET | `/api/conversations/{id}` | Full message history |
| DELETE | `/api/conversations/{id}` | Delete a conversation |
| GET | `/api/admin/documents` | Dashboard data: summary, counts by type, paginated documents with chunk/embedding counts (`q`, `doc_type`, `limit`, `offset`) |
| GET | `/api/admin/runs` | Pipeline runs (filter by stage/status) |
| GET | `/api/admin/runs/{id}` · `/events` | Run detail and its events |
| GET | `/api/admin/queries` | Question log |
| GET | `/api/admin/stats/pipeline` · `/stats/queries` | Aggregated statistics |

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "O que diz o Comunicado nº 34.977?", "language": "pt"}'
```

## Database

Schema is managed with Alembic (`backend/migrations`; `0001` initial, `0002` logging tables).

| Table | Purpose |
|---|---|
| `documents` | One row per normativo: `source`, `url` (unique), `title`, `doc_type`, `published_at`, `language`, `content_hash`, `raw_text`, `fetched_at` |
| `chunks` | `document_id`, `chunk_index`, `text`, `token_count`, `embedding vector(768)`, `embedding_model`; HNSW cosine index |
| `conversations` / `messages` | Persistent chat history, with cited `sources` as JSONB |
| `pipeline_runs` | One row per stage execution: status, duration, items total/ok/failed, params, error |
| `pipeline_events` | Per-item warnings/errors of a run (document/chunk id, message, details) |
| `query_logs` | One row per question: answer, retrieved chunks and scores, models, latency, status |
| `ingest_runs` | Legacy scraper history (superseded by `pipeline_runs`) |

Quick query:

```bash
docker compose exec -e PGPASSWORD=postgresml db psql -h localhost -U postgresml -d postgresml -c \
"SELECT id, doc_type, published_at::date, left(title,60), length(raw_text) FROM documents ORDER BY published_at DESC;"
```

## Observability

`track_run(stage, params)` (`backend/app/observability/async_tracker.py`) wraps each worker stage. It uses its own autocommit connection so log rows survive worker rollbacks, and it never raises if logging itself fails. `log_query()` records each chat request. Both feed the **Logs** page and `check_docs.py`.

## CI / container images

`.github/workflows/docker-build.yml` ("Build and publish Docker images"):

1. Builds the API (`-f backend/Dockerfile .`) and frontend (`./frontend`) images and runs smoke tests (`import app.main`, `dist/index.html` exists).
2. On push to `main`, logs in to GHCR with `GITHUB_TOKEN` and pushes `ghcr.io/<owner>/rag-banco-central-api` and `…-frontend`, tagged `latest` and the commit SHA.

To pull without logging in, set each package to **Public** (GitHub → profile → Packages → package → Package settings → Change visibility).

## Development

- Backend: Python 3.14, dependencies in `backend/pyproject.toml`; lint with `ruff`, types with `mypy`. `backend/app` is bind-mounted into `api` and `pipeline`, so code edits apply without a rebuild (the API reloads itself; restart `pipeline` after changing worker code).
- Rebuild only when dependencies or the Dockerfile change: `docker compose up -d --build`.
- Tests: `pytest` (`tests/`), covering the BCB scraper, chunker and RAG components.
- Frontend: `frontend/`. The Dockerfile installs with `--legacy-peer-deps` because of a Vite / `@vitejs/plugin-react` peer conflict. Type-check with `npx tsc --noEmit`.

## Known issues

- **Resoluções BCB return empty content.** The search API lists them, but the content endpoint (`exibeoutrasnormas`) returns an empty `conteudo`, so the scraper skips them and reports `done_with_errors`. Comunicados ingest normally. Under investigation.
- Token counts in `query_logs` are not filled yet (the answer function does not return usage).
- The legacy `ingest_runs` insert in the scraper may fail silently; `pipeline_runs` is the source of truth.
- Previous conversation turns are stored but not yet passed to the LLM as context.

## Roadmap

- Fill token usage in `query_logs`.
- Use prior turns as conversation context.
- Fix Resoluções content endpoint.

## License

MIT. Contributions via fork and pull request are welcome.

## Acknowledgments

- Banco Central do Brasil for the public API.
- Anthropic for the language model.
- PostgresML, pgvector and the open-source embedding models.

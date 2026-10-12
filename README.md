# BCB RAG

RAG chatbot over Banco Central do Brasil (BCB) regulations. It scrapes normativos from the BCB API, chunks them, embeds them inside PostgreSQL (PostgresML + pgvector) and answers questions in Portuguese or English with clickable citations to the original BCB page. The pipeline runs automatically every day, and everything it does is logged and visible in the UI.

See `bcb-rag-plan.md` for the full plan, `PHASE4.md` for the retrieval/answering notes and `PLANO_LOGS_PIPELINE.md` for the logging design.

## Features

- **Chat** with persistent conversations (history sidebar, reopen or delete past chats), PT/EN answers and `[n]` citation chips that show the passage used.
- **Hybrid retrieval:** exact match on the document number in the title (e.g. "Comunicado nº 34.977") combined with semantic search (pgvector cosine).
- **Documents dashboard:** live view (auto-refresh every 5 s) of every document in the database, with chunk and vectorization progress.
- **Logs page:** pipeline runs and events, plus a log of every question (retrieved chunks, latency, status).
- **Conversation context:** the last messages of the chat are sent to the LLM, and short follow-ups ("e o prazo?") are expanded with the previous question for retrieval.
- **Token and cost tracking:** input/output tokens and an estimated USD cost per question, with totals on the Logs page.
- **Retrieval evaluation:** a question set and a script that reports hit-rate@k and MRR for semantic-only vs hybrid retrieval.
- **Scheduled pipeline:** scrape → chunk → embed once a day, no manual commands.
- **CI:** GitHub Actions builds both images, runs the test suite against a real Postgres (pgvector), and publishes the images to GHCR.

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

# LLM cost tracking (USD per million tokens; 0 = record tokens only)
LLM_PRICE_INPUT_PER_MTOK=0
LLM_PRICE_OUTPUT_PER_MTOK=0
HISTORY_MAX_MESSAGES=6

# Pipeline automation (see below)
PIPELINE_SCHEDULE_TIME=06:00
PIPELINE_TZ=America/Sao_Paulo
PIPELINE_SCRAPE_DAYS=2
PIPELINE_EMBED_BATCH_SIZE=32
PIPELINE_RUN_ON_START=false
```

Embeddings are generated inside Postgres by PostgresML, so no external embedding API key is needed.

`LLM_PRICE_*` are the prices of `ANTHROPIC_MODEL` per million tokens (see Anthropic's pricing page). They are not hard-coded because they change; leave them at `0` and only token counts are recorded. `HISTORY_MAX_MESSAGES` is how many previous messages (user + assistant) are sent as context.

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
# Backfill a single source far back (e.g. old Comunicados)
docker compose exec api python -m app.worker.scrape --days 2000 --source bcb_comunicados_ccs
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

## Conversation context and cost tracking

- On each `/api/chat` call the last `HISTORY_MAX_MESSAGES` messages of the conversation are loaded and sent to Claude as earlier turns (retrieved passages are only attached to the new question, so the prompt does not grow with old context).
- If the new question is short (8 words or fewer) the previous user question is prepended **for retrieval only**, so "e o prazo disso?" still finds the right document.
- The Anthropic `usage` of every answer is stored in `query_logs` (`tokens_in`, `tokens_out`) together with `cost_usd` when the `LLM_PRICE_*` variables are set. The Logs page shows the total estimated cost, total tokens, and the per-question breakdown.

## Retrieval evaluation

```bash
docker compose exec api python -m app.evaluation.run_eval            # top-5; details go to /tmp/eval_results.json in the container
docker compose exec api python -m app.evaluation.run_eval --k 3
```

The question set lives in `backend/app/evaluation/dataset.json`: identifier questions ("Resolução BCB nº 598") and natural-language ones, each with the document(s) that must be retrieved (matched as whole numbers in the title). The script runs every question twice, **semantic-only** and **hybrid**, and prints hit-rate@k and MRR overall, for verified questions only, and per question type.

### Results

Corpus: BCB Resoluções from the last 30 days plus Comunicados CCS (backfilled), top-5, 12 questions (8 by identifier, 4 natural language). Run of 2026-10-12:

| Retrieval | Hit-rate@5 | MRR | Identifier questions | Natural-language questions |
|---|---|---|---|---|
| Semantic only | 67% | 0.500 | 50% (MRR 0.41) | 100% (MRR 0.69) |
| **Hybrid** (title-number + semantic) | **100%** | **0.896** | **100%** (MRR 1.00) | 100% (MRR 0.69) |

How to read it:

- The hybrid step fixes exactly what embeddings are bad at: exact document numbers ("Resolução BCB nº 598"). Semantic-only misses 4 of 8 of those because the e5 model cannot tell 589 from 598.
- It does not change natural-language questions (same score in both modes), as expected. Their MRR of 0.69 (the right document at rank #1 to #4) is the room left for a reranker.
- The identifier questions are the ones the hybrid step was designed around, so that gap is a measured design validation, not an independent benchmark. The set is small (12 questions); treat the numbers as indicative until it grows.
- The three natural-language questions marked unverified retrieve the documents I expected, but whether those documents truly answer them still needs a human read.

Entries with `"verified": false` are drafts whose expected document I could not confirm against the database: open the Documentos page, correct `expected_titles`, and set `verified` to `true`. Extend the file as the corpus grows; 30 to 50 questions make the numbers meaningful.

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
| GET | `/api/admin/queries` | Question log (tokens, cost, latency, retrieved chunks) |
| GET | `/api/admin/stats/pipeline` · `/stats/queries` | Aggregated statistics |

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "O que diz o Comunicado nº 34.977?", "language": "pt"}'
```

## Database

Schema is managed with Alembic (`backend/migrations`; `0001` initial, `0002` logging tables, `0003` `query_logs.cost_usd`). After pulling new migrations run `docker compose exec api alembic upgrade head`; until `0003` is applied, question logging and the Logs page will fail.

| Table | Purpose |
|---|---|
| `documents` | One row per normativo: `source`, `url` (unique), `title`, `doc_type`, `published_at`, `language`, `content_hash`, `raw_text`, `fetched_at` |
| `chunks` | `document_id`, `chunk_index`, `text`, `token_count`, `embedding vector(768)`, `embedding_model`; HNSW cosine index |
| `conversations` / `messages` | Persistent chat history, with cited `sources` as JSONB |
| `pipeline_runs` | One row per stage execution: status, duration, items total/ok/failed, params, error |
| `pipeline_events` | Per-item warnings/errors of a run (document/chunk id, message, details) |
| `query_logs` | One row per question: answer, retrieved chunks and scores, models, tokens, `cost_usd`, latency, status |
| `ingest_runs` | Legacy table, no longer written (superseded by `pipeline_runs`) |

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
2. Runs the test suite inside the API image against a `pgvector/pgvector:pg16` service container: `alembic upgrade head`, then `pytest` with `RUN_DB_TESTS=1`.
3. On push to `main`, logs in to GHCR with `GITHUB_TOKEN` and pushes `ghcr.io/<owner>/rag-banco-central-api` and `…-frontend`, tagged `latest` and the commit SHA.

To pull without logging in, set each package to **Public** (GitHub → profile → Packages → package → Package settings → Change visibility).

## Testing

```bash
docker compose exec api python -m pytest -q                      # unit tests (database tests are skipped)
docker compose exec -e RUN_DB_TESTS=1 api python -m pytest -q    # also runs the database tests
```

| File | Covers |
|---|---|
| `test_retrieval_numbers.py` | Document-number extraction for hybrid retrieval ("Resolução 598", "34.977", English forms) |
| `test_conversation_context.py` | Message building from history, retrieval-query expansion, cost maths |
| `test_answering_usage.py` | History reaches the Anthropic call, usage returned (Anthropic client faked) |
| `test_scheduler.py` | Next-run calculation, DST, time parsing |
| `test_pipeline.py` | Stage runner: exit codes and exceptions never stop later stages |
| `test_eval_metrics.py` | Hit-rate/MRR maths and dataset validity |
| `test_bcb_normativos.py`, `test_bcb_fetch_fallback.py` | Scraper parsing and endpoint fallback (HTTP mocked) |
| `test_chunker.py`, `test_rag.py` | Chunker and context building |
| `test_db_admin_api.py` | Admin API (runs, events, queries, stats, documents dashboard), title-number SQL and conversation history against real Postgres |

`RUN_DB_TESTS=1` writes and deletes a few rows in the database `DATABASE_URL` points to, so prefer a scratch database. In CI that is the service container.

## Development

- Backend: Python 3.14, dependencies in `backend/pyproject.toml`; lint with `ruff`, types with `mypy`. `backend/app` is bind-mounted into `api` and `pipeline`, so code edits apply without a rebuild (the API reloads itself; restart `pipeline` after changing worker code).
- Rebuild only when dependencies or the Dockerfile change: `docker compose up -d --build`.
- Frontend: `frontend/`. The Dockerfile installs with `--legacy-peer-deps` because of a Vite / `@vitejs/plugin-react` peer conflict. Type-check with `npx tsc --noEmit`.

## Known issues

- **Resoluções BCB** return an empty `conteudo` from `exibeoutrasnormas`; the scraper now falls back to `exibenormativo` and other spellings of the type, and the error message lists what was tried. Check **Logs → Execuções** if a run still reports `done_with_errors`.
- The evaluation set has a few unverified draft entries (`"verified": false`) and is small; treat the scores as indicative until it is extended.
- The database tests and CI workflow were written without a Postgres available to run them locally; the first CI run is their first real execution.

## Roadmap

- Grow the evaluation set (30 to 50 verified questions) and try reranking.
- Authentication on `/api/admin/*`.
- Deployed demo and screenshots.

## License

MIT. Contributions via fork and pull request are welcome.

## Acknowledgments

- Banco Central do Brasil for the public API.
- Anthropic for the language model.
- PostgresML, pgvector and the open-source embedding models.

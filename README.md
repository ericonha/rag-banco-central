# BCB RAG

RAG chatbot over Banco Central do Brasil (BCB) regulations. It scrapes normativos from the BCB API, chunks them, embeds them inside PostgreSQL (PostgresML + pgvector) and answers questions in Portuguese or English with citations to the original BCB page.

See `bcb-rag-plan.md` for the full plan and `PHASE4.md` for the retrieval/answering notes.

## Architecture

```
React (Vite, :3000) --> FastAPI (:8000) --> Anthropic API (answers)
                            |
                            v
              PostgreSQL + pgvector + PostgresML (:5433 on host)
                            ^
        workers: scrape -> chunk -> embed   (run via docker compose exec)
```

| Service | Description | Port |
|---|---|---|
| `db` | PostgresML image (Postgres 15, pgvector, `pgml.embed`) | 5433 |
| `api` | FastAPI backend and worker scripts | 8000 |
| `frontend` | React 18 + TypeScript + Vite chat UI | 3000 |

## Quick start

```bash
cp .env.example .env          # fill ANTHROPIC_API_KEY etc.
docker compose up --build -d
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
```

Embeddings are generated inside Postgres by PostgresML, so no external embedding API key is needed.

## Data pipeline

Run the three stages in order. Each one only processes what is still pending.

```bash
# 1. Scrape new documents (default: last 7 days)
docker compose exec api python -m app.worker.scrape --days 30

# 2. Split documents into chunks
docker compose exec api python -m app.worker.chunk

# 3. Embed chunks with PostgresML (default batch size: 32)
docker compose exec api python -m app.worker.embed --batch-size 32
```

Check what is in the database and what is vectorized:

```bash
python check_docs.py
```

It prints total documents, documents with embeddings, chunks, and per-document chunk/vector counts (connects to `localhost:5433`).

### Scraper sources (`backend/app/scraping/sources.py`)

| `source_name` | Document type |
|---|---|
| `bcb_comunicados_ccs` | Comunicado (query `CCS`) |
| `bcb_resolucoes` | Resolução BCB |
| `bcb_circulares` | Circular BCB |
| `bcb_instrucoes_normativas` | Instrução Normativa |

Each run is recorded in `ingest_runs` (status, new documents, errors).

### Testing the RAG pipeline from the CLI

```bash
docker compose exec api python -m app.worker.test_rag --language pt
```

Runs sample questions and saves results to `rag_test_results_pt.json`.

## API

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Status, timestamp, embedding model |
| POST | `/api/chat` | Body: `question`, `language` (`pt`/`en`), optional `conversation_id`. Returns `answer`, `sources`, `retrieved_chunks` |
| GET | `/api/documents` | Ingested documents with chunk counts |
| GET | `/api/conversations/{conversation_id}` | Conversation history |

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "Quais são os requisitos de capital mínimo?", "language": "pt"}'
```

## Database

Schema is managed with Alembic (`backend/migrations`).

| Table | Purpose |
|---|---|
| `documents` | One row per normativo: `source`, `url` (unique), `title`, `doc_type`, `published_at`, `language`, `content_hash`, `raw_text`, `fetched_at` |
| `chunks` | `document_id`, `chunk_index`, `text`, `token_count`, `embedding vector(768)`, `embedding_model`; HNSW cosine index |
| `conversations` / `messages` | Chat memory per conversation, with cited `sources` as JSONB |
| `ingest_runs` | Scraper run history |

Quick query:

```bash
docker compose exec -e PGPASSWORD=postgresml db psql -h localhost -U postgresml -d postgresml -c \
"SELECT id, doc_type, published_at::date, left(title,60), length(raw_text) FROM documents ORDER BY published_at DESC;"
```

## Development

- Backend: Python 3.14, dependencies in `backend/pyproject.toml`; lint with `ruff`, types with `mypy`.
- Tests: `pytest` (`tests/`), covering the BCB scraper, chunker and RAG components.
- Frontend: `frontend/` (see `frontend/README.md`). The Dockerfile installs with `--legacy-peer-deps` because of a Vite / `@vitejs/plugin-react` peer conflict.

## Known issues

- **Resoluções BCB return empty content.** The search API lists them, but the content endpoint (`exibeoutrasnormas`) returns an empty `conteudo`, so the scraper skips them and reports `done_with_errors`. Comunicados ingest normally. Under investigation.

## Roadmap

- **Pipeline and query logging:** `pipeline_runs`, `pipeline_events` and `query_logs` tables, a `track_run` context manager for scrape/chunk/embed, and per-question metadata (retrieved chunks and scores, tokens, latency). See `PLANO_LOGS_PIPELINE.md`.
- Admin "Logs" page in the frontend.
- Daily scheduled scrape (cron in a container).

## License

MIT. Contributions via fork and pull request are welcome.

## Acknowledgments

- Banco Central do Brasil for the public API.
- Anthropic for the language model.
- PostgresML, pgvector and the open-source embedding models.

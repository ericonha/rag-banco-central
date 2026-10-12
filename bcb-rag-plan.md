# BCB RAG Project: Implementation Plan

A daily scraper for Banco Central do Brasil (BCB) content, with embeddings generated and stored inside PostgreSQL (PostgresML + pgvector), a chat API that answers with citations, and a small React frontend that also shows current data. Everything runs in Docker.

## 1. Decisions so far

| Topic | Decision |
|---|---|
| Source | BCB (Brazil), mainly regulations (normativos), plus communications |
| Numeric data | Official BCB APIs (SGS / Olinda Open Data), not HTML scraping |
| Text content | `httpx` + BeautifulSoup |
| Languages | Switchable (pt / en) in UI and answers |
| LLM | Anthropic API (model configurable via env var) |
| Embeddings | Generated inside Postgres with PostgresML (`pgml.embed`), open-source multilingual Hugging Face model, no external embedding API. Exact model chosen in the Phase 0 spike (see section 10) |
| PDFs | Out of scope for now |
| Updates | Daily, only new documents and communications |
| First load | Last 7 days |
| Citations | Always, with link to the original BCB page |
| Chat memory | Yes, per conversation, no auth |
| Backend | FastAPI |
| Database | PostgreSQL via the PostgresML Docker image, with pgvector for storage and search |
| Scheduler | Cron inside a container |
| Python | 3.14 (stable; see note in section 9) |
| Goal | Portfolio project for AI Engineer roles in Europe |

## 2. Architecture

```
            +-----------------+
            |  React (Vite)   |  chat + data dashboard
            +--------+--------+
                     | HTTP / SSE
            +--------v--------+        +----------------------+
            |  FastAPI (api)  +------->+  Anthropic API (chat)|
            +--------+--------+        +----------------------+
                     |
                     |  SQL + vector search
            +--------v--------+
            | PostgresML + pgvector|
            | (pgml.embed in SQL) |
            +--------^--------+
                     |
            +--------+--------+
            | worker (cron)   +----> BCB pages and BCB APIs
            | scraper+ingest  |
            +-----------------+
```

Three containers plus the frontend: `db`, `api`, `worker`, `web`. Orchestrated with `docker compose`.

## 3. Repository layout

```
bcb-rag/
  docker-compose.yml
  .env.example
  README.md
  backend/
    pyproject.toml
    Dockerfile
    app/
      config.py            # settings from env
      db/                  # models, session, migrations (Alembic)
      scraping/            # sources, fetchers, parsers
      ingest/              # chunking, embedding, upsert
      rag/                 # retrieval, prompt, answer
      api/                 # FastAPI routers
      worker/              # entrypoints for cron jobs
    tests/
  frontend/
    Dockerfile
    src/                   # chat, data dashboard, i18n
  docs/
```

## 4. Phases

### Phase 0: Project setup and PostgresML spike
1. Create repo, `.gitignore`, `.env.example` (API keys, DB URL, model names).
2. Backend with `uv` (or pip) and `pyproject.toml`, Python 3.14 base image.
3. `docker-compose.yml` with `db` using a pgvector image, plus a healthcheck.
4. Pre-commit with `ruff` and `mypy` (or `pyright`).

5. **Spike (do this before anything else).** Start the PostgresML image and confirm, in `psql`:
   - how to connect (user, password, database, port) and that `CREATE EXTENSION IF NOT EXISTS vector;` and `CREATE EXTENSION IF NOT EXISTS pgml;` work;
   - that `SELECT pgml.embed('<model>', 'texto de teste');` works for a multilingual model, and note the vector length and the time of the first call (model download) and later calls;
   - that the result casts to `vector(N)` and an HNSW index can be created on it.
   Candidates to test, in order: `intfloat/multilingual-e5-base` (768 dims), `intfloat/multilingual-e5-large` (1024), `BAAI/bge-m3` (1024). If none works, fall back to Ollama (`bge-m3`) for embeddings and keep plain pgvector.

   Findings so far: the image needs a keep-alive `command` in Compose (`sleep infinity`), otherwise its entrypoint exits and loops. Credentials are `postgresml` / `postgresml` / database `postgresml`; `vector` and `pgml` extensions are created. Spike result: `intfloat/multilingual-e5-small` (384) and `intfloat/multilingual-e5-base` (768) both work with `pgml.embed` after raising Docker's memory limit; the base model ranks a related Portuguese sentence closer than an unrelated one with a slightly wider gap. **Decision: `intfloat/multilingual-e5-base`, 768 dimensions.**

**Done when:** `docker compose up db` starts, you can connect, `vector` and `pgml` are enabled, and `pgml.embed` returns a vector for a Portuguese sentence with a known dimension.

### Phase 1: Database schema
Tables (via Alembic migrations):
- `documents`: id, source, url (unique), title, doc_type, published_at, language, content_hash, raw_text, fetched_at
- `chunks`: id, document_id (FK), chunk_index, text, embedding `vector(N)`, token_count
- `conversations`: id (UUID), created_at, language
- `messages`: id, conversation_id (FK), role, content, sources (JSONB), created_at
- `ingest_runs`: id, started_at, finished_at, status, new_docs, errors

Index: HNSW (or IVFFlat) on `chunks.embedding` with cosine distance. `N` is the dimension of the model that passed the Phase 0 spike (e.g. 768 for multilingual-e5-base).

**Done when:** migrations run cleanly on an empty DB and a test vector can be inserted and queried.

### Phase 2: Scraper
1. Define a `Source` interface: `list_new(since) -> list[DocRef]` and `fetch(DocRef) -> Document`.
2. Implement the first source for BCB regulations. Inspect the real pages and network calls first (some BCB pages load content via JSON endpoints, which is easier than parsing HTML).
3. Use `httpx` with timeouts, retries with backoff, a clear User-Agent, and polite rate limiting. Check `robots.txt` and the site's terms.
4. Clean HTML to text (BeautifulSoup), keep title, date, type, and URL.
5. Deduplicate by URL and `content_hash`; only insert or update when new or changed.
6. Save HTML fixtures for tests so parsers can be tested offline.

**Done when:** a CLI command `python -m app.worker.scrape --days 7` stores the last week's documents.

### Phase 3: Chunking and embedding
1. Chunk by structure first (articles, sections), then by size (about 500 to 800 tokens, small overlap).
2. Insert chunks with `embedding = NULL` plus metadata (title, URL, date, doc type).
3. Embed inside the database in batches, e.g. `UPDATE chunks SET embedding = pgml.embed(:model, 'passage: ' || text)::vector(N) WHERE embedding IS NULL AND id IN (SELECT id ... LIMIT 32)`. The `passage: ` / `query: ` prefixes apply to the e5 models; check what the chosen model expects.
4. Make the embedding model a config value and store the model name per chunk, so a model change triggers re-embedding instead of silent mixing.
5. Measure embedding time on CPU for the first load (a week of documents) and note it in the README.

**Done when:** after the backfill, `chunks` is populated and a similarity query returns sensible results for a Portuguese test question.

### Phase 4: Retrieval and answering (RAG core)
1. Retrieve top-k chunks by cosine similarity, filtered by optional date or doc type. The query is embedded in the same SQL statement: `ORDER BY embedding <=> pgml.embed(:model, 'query: ' || :question)::vector(N)`.
2. Optional improvement: hybrid search (pgvector + Postgres full text) and a reranking step.
3. Prompt design: system prompt requires answering only from the provided context, citing sources by number, and saying "I don't know" when the context is insufficient.
4. Call the Anthropic API; return answer text plus a structured `sources` list (title, URL, date, snippet).
5. Language: answer in the UI language selected by the user (pt or en), even though the sources are in Portuguese.
6. Conversation memory: load the last N messages of the conversation, rewrite the follow-up into a standalone query before retrieval, then answer.

**Done when:** a CLI or test script answers 10 sample questions with correct citations.

### Phase 5: FastAPI
Endpoints:
- `POST /api/chat` (body: conversation_id, message, language), streamed with SSE
- `GET /api/conversations/{id}` for history
- `GET /api/data/series` for numeric series (Selic, IPCA, USD/BRL, etc.) from the BCB APIs, with short caching
- `GET /api/documents` for the latest ingested documents
- `GET /api/health`

Add request validation (Pydantic), CORS for the frontend, basic rate limiting per IP (no auth, so protect your API key budget), and structured logging.

**Done when:** all endpoints work via the auto-generated `/docs` page.

### Phase 6: Daily job (cron in container)
1. `worker` container runs `supercronic` (or `cron`) with a crontab, e.g. daily at 06:00 America/Sao_Paulo. Set `TZ` explicitly.
2. Job steps: scrape new documents, chunk, insert, run the in-database embedding step, write an `ingest_runs` row.
3. Make it idempotent: running twice causes no duplicates.
4. Log to stdout so `docker logs` works; fail loudly on errors.
5. Provide manual triggers: `docker compose run worker python -m app.worker.ingest --days 7`.

**Done when:** the job runs on schedule and a second run on the same day inserts nothing new.

### Phase 7: Frontend (React + Vite + TypeScript)
1. Chat view: message list, input, streaming display, collapsible source cards with links.
2. Data view: charts (e.g. Recharts) for the main series, last updated timestamp, and a list of the latest documents.
3. Language switcher (pt / en) using `react-i18next`; send the language with each chat request.
4. Persist `conversation_id` in localStorage so history survives a reload; "new chat" button.
5. Serve the build via nginx in the `web` container, proxying `/api` to the backend.

**Done when:** you can ask a question in the browser, see a streamed answer with sources, and view the data charts.

### Phase 8: Quality and evaluation (important for the portfolio)
1. Unit tests for parsers (using saved fixtures), chunking, and dedupe logic.
2. Integration test with a test Postgres container.
3. Small retrieval evaluation set: 20 to 30 question / expected-document pairs; report hit rate@k. Re-run when you change chunking or embeddings.
4. Optionally check answer faithfulness (answer supported by cited chunks).
5. GitHub Actions: lint, type check, tests, Docker build.

### Phase 9: Hardening and docs
1. Secrets only via env; never commit keys; non-root users in containers.
2. Cost guardrails: max tokens, max message length, request limits.
3. README with architecture diagram, setup in 3 commands, screenshots or a short GIF, design decisions and trade-offs, evaluation results.
4. Optional: deployment on a small VM with HTTPS (Caddy or Traefik).

## 5. Suggested order and rough effort

| Phase | Effort (focused days) |
|---|---|
| 0 Setup | 0.5 |
| 1 Schema | 0.5 |
| 2 Scraper | 2 |
| 3 Chunking + embeddings | 1 |
| 4 RAG core | 2 |
| 5 FastAPI | 1 |
| 6 Cron job | 0.5 |
| 7 Frontend | 2 to 3 |
| 8 Evaluation + CI | 1.5 |
| 9 Docs / hardening | 1 |

Total: roughly 12 to 14 focused days. These are estimates, not promises.

## 6. Risks and things to verify

- **Scraping stability:** BCB page structure may change or load content dynamically. Prefer JSON endpoints where they exist; keep parsers small and tested.
- **Legal/ethical:** Check terms of use and robots.txt; keep request rates low.
- **PostgresML maintenance risk:** the latest release I could see on its GitHub page is v2.10.0 from January 2025, and I found no newer one. It still works as a Docker image, but it may lag behind current Postgres and model versions. The Phase 0 spike decides whether to keep it; the fallback is Ollama or an embeddings API with plain pgvector, which only changes Phase 3 and the retrieval SQL.
- **PostgresML and pgvector:** a GitHub issue reports that the `vector` type was missing in an older PostgresML image (2.8.2). The maintainers say it is installed, but verify it in the spike.
- **Model support in `pgml.embed`:** the docs I read confirm Hugging Face models in general but do not list multilingual ones like bge-m3 or multilingual-e5. Test them; do not assume.
- **Resource use:** models run inside the database container on CPU unless you have a GPU. Expect slow first calls (model download) and more RAM than a plain Postgres.
- **Coupling:** embedding inside the DB ties search quality and availability to one container. Keep the model name per chunk so you can re-embed.
- **Regulation text is hierarchical** (articles, paragraphs, references to other norms). Structure-aware chunking will matter more than fancy retrieval.
- **No auth + public API key budget:** rate limit and cap tokens, or keep it local only.
- **Exact BCB API endpoints and series codes:** to be confirmed from the official BCB documentation before coding Phase 2 and the data endpoint.

## 7. Open questions for later

1. Exact URLs / sections of the regulations to scrape (you will provide them in code).
2. Which numeric series to show on the dashboard.
3. Which embedding model and dimension (answered by the Phase 0 spike).
4. Local-only or deployed on a server?

## 8. First concrete next steps

1. Get an Anthropic API key. No embedding key is needed with PostgresML.
2. Run the PostgresML spike (Phase 0, step 5) and pick the embedding model and dimension from the results.
3. Open the BCB regulations page in the browser dev tools and note how the list and detail pages load their data. This decides the scraper design.

## 9. Note on the Python version

Python 3.14 is the current stable line with good wheel support for the libraries in this stack. Python 3.15 was scheduled for release in early October 2026, but I could not confirm that the final release is out, and packages may lag behind a brand-new version. Start on 3.14 and upgrade later by changing one line in the Dockerfile.

## 10. Change log

- Embeddings moved from an external API (Voyage) to PostgresML (`pgml.embed`) running inside Postgres. Affected: decisions table, architecture, Phases 0, 1, 3, 4, 6, risks. Phases 2, 5, 7, 8, 9 are unchanged.
- The embedding model and `vector(N)` dimension are now decided by the Phase 0 spike, not fixed up front. Spike done: `intfloat/multilingual-e5-base`, 768 dimensions. Phase 1 migration (Alembic, raw SQL) is in `backend/migrations`.

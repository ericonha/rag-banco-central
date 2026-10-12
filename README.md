# BCB RAG

RAG chatbot over Banco Central do Brasil regulations. See `bcb-rag-plan.md` for the full plan.

## Quick start (Phase 0)

```bash
cp .env.example .env      # fill DATABASE_URL after the Phase 0 spike
docker compose up --build
curl http://localhost:8000/api/health
```

Expected: `{"status":"ok","pgvector":"enabled"}`

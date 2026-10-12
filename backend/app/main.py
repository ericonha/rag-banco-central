import psycopg
from fastapi import FastAPI

from app.config import get_settings

app = FastAPI(title="BCB RAG")


@app.get("/api/health")
def health() -> dict[str, str]:
    with psycopg.connect(get_settings().database_url) as conn:
        row = conn.execute("SELECT extname FROM pg_extension WHERE extname = 'vector'").fetchone()
    return {"status": "ok", "pgvector": "enabled" if row else "missing"}

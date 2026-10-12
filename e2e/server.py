"""
API server for the end-to-end tests.

It is the real FastAPI application (routes, SSE framing, rate limiter, CORS, persistence in
Postgres, feedback, export, faithfulness check) with exactly two things replaced, because CI has
neither PostgresML nor an Anthropic key:

  * retrieval  -> returns one canned chunk (honours the document-type filter)
  * the LLM    -> streams a canned Markdown answer, slowly when the question contains "lenta"

Requirements: DATABASE_URL pointing to an EMPTY-OR-DISPOSABLE Postgres database (migrations are
applied here, and test rows are inserted). Never point it at your real data.

    DATABASE_URL=postgresql://postgres:postgres@localhost:5432/e2e python3 server.py
"""
from __future__ import annotations

import asyncio
import itertools
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

if not os.environ.get("DATABASE_URL"):
    sys.exit("DATABASE_URL is required (use a disposable database)")

# Must be set before app.main is imported (settings are read at import time).
os.environ.update(
    ANTHROPIC_API_KEY="e2e-not-used",
    ANTHROPIC_MODEL="e2e-model",
    EMBEDDING_MODEL="e2e-embedding",
    EMBEDDING_DIM="768",
    RERANK_MODEL="",
    RATE_LIMIT_PER_MINUTE="0",
    RATE_LIMIT_CHAT_PER_MINUTE="0",
    CORS_ALLOW_ORIGINS="http://localhost:3000,http://127.0.0.1:3000",
)

subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, check=True)

import psycopg  # noqa: E402
import uvicorn  # noqa: E402

DOC_TYPE = "Resolução BCB"
OTHER_DOC_TYPE = "Comunicado"
CHUNK_TEXT = "A Resolução BCB nº 598 dispõe sobre o envio de dados. O prazo é de 30 dias corridos."


def _seed() -> None:
    """Two documents (two types) so the Documentos page and the type filter have something to show."""
    docs = [
        ("e2e-598", "https://example.test/e2e/598", "Resolução BCB N° 598", DOC_TYPE),
        ("e2e-99999", "https://example.test/e2e/99999", "Comunicado N° 99.999", OTHER_DOC_TYPE),
    ]
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as conn:
        for source, url, title, doc_type in docs:
            row = conn.execute(
                "INSERT INTO documents (source, url, title, doc_type, published_at, content_hash, raw_text) "
                "VALUES (%s, %s, %s, %s, now(), %s, %s) ON CONFLICT (url) DO NOTHING RETURNING id",
                (source, url, title, doc_type, source, CHUNK_TEXT),
            ).fetchone()
            if row:
                conn.execute(
                    "INSERT INTO chunks (document_id, chunk_index, text) VALUES (%s, 0, %s)",
                    (row[0], CHUNK_TEXT),
                )


_seed()

import app.main as main  # noqa: E402


async def fake_retrieve(conn, question, embedding_model, embedding_dim, k=5, doc_type_filter=None, **_):
    if doc_type_filter and doc_type_filter != DOC_TYPE:
        return []  # the canned document is a Resolução: any other type filter finds nothing
    return [
        {
            "id": 1,
            "document_id": 1,
            "title": "Resolução BCB N° 598",
            "url": "https://example.test/e2e/598",
            "published_at": datetime(2026, 10, 7, tzinfo=timezone.utc),
            "doc_type": DOC_TYPE,
            "text": CHUNK_TEXT,
            "distance": 0.1,
        }
    ]


_answers = itertools.count(1)


async def fake_stream(question, chunks, language="pt", anthropic_api_key="", anthropic_model="", history=None, **_):
    n = next(_answers)
    if "lenta" in question.lower():
        pieces = [f"Parte {i} da resposta lenta. " for i in range(1, 60)]
        delay = 0.25
    else:
        pieces = [
            "A **Resolução BCB nº 598** dispõe sobre o envio de dados [1]. ",
            f"(versão {n})\n\n",
            "| Item | Valor |\n|---|---|\n| Prazo | 30 dias corridos [1] |\n",
        ]
        delay = 0.05
    for piece in pieces:
        await asyncio.sleep(delay)
        yield {"type": "delta", "text": piece}
    yield {"type": "usage", "tokens_in": 100, "tokens_out": 20}


main.retrieve_chunks = fake_retrieve
main.stream_answer = fake_stream

if __name__ == "__main__":
    uvicorn.run(main.app, host="0.0.0.0", port=8000, log_level="warning")

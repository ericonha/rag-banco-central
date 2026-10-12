"""RAG query logging (psycopg v3, async).

``log_query`` writes one row to ``query_logs`` on its own autocommit connection
and never raises: a logging failure must not break an answer.
"""
from __future__ import annotations

import logging
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from app.config import get_settings

logger = logging.getLogger(__name__)


async def log_query(
    *,
    question: str,
    answer: str | None,
    retrieved: list[dict[str, Any]] | None = None,
    top_k: int = 5,
    embedding_model: str | None = None,
    llm_model: str | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    latency_retrieval_ms: int | None = None,
    latency_llm_ms: int | None = None,
    latency_total_ms: int | None = None,
    status: str = "ok",
    error: str | None = None,
) -> bool:
    """Insert a query log row. Returns True on success, False otherwise."""
    try:
        async with await psycopg.AsyncConnection.connect(
            get_settings().database_url, autocommit=True
        ) as conn:
            await conn.execute(
                """
                INSERT INTO query_logs (
                    question, answer, retrieved, top_k, embedding_model, llm_model,
                    tokens_in, tokens_out, latency_retrieval_ms, latency_llm_ms,
                    latency_total_ms, status, error
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    question,
                    answer,
                    Jsonb(retrieved) if retrieved is not None else None,
                    top_k,
                    embedding_model,
                    llm_model,
                    tokens_in,
                    tokens_out,
                    latency_retrieval_ms,
                    latency_llm_ms,
                    latency_total_ms,
                    status,
                    error,
                ),
            )
        return True
    except Exception as exc:
        logger.error("Failed to log query: %s", exc)
        return False

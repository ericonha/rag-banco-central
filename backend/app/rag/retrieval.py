"""
Retrieve relevant chunks by semantic similarity.

Uses pgvector cosine similarity with the e5 model.
"""
from __future__ import annotations

import logging
import re
from typing import Any

import psycopg

logger = logging.getLogger(__name__)


# Document numbers such as "34.977" or "34977" (embeddings are poor at matching identifiers).
_NUMBER_RE = re.compile(r"\b\d{1,3}(?:\.\d{3})+\b|\b\d{4,}\b")


def _document_numbers(question: str) -> list[str]:
    """Return the document numbers mentioned in the question, as digits only."""
    return list(dict.fromkeys(re.sub(r"\D", "", m) for m in _NUMBER_RE.findall(question)))


async def _chunks_by_title_number(
    conn: psycopg.AsyncConnection,
    numbers: list[str],
    limit: int,
    doc_type_filter: str | None,
) -> list[dict[str, Any]]:
    """Chunks of documents whose title contains one of the given numbers (exact match)."""
    sql = r"""
    SELECT c.id, c.text, c.document_id, d.title, d.url, d.published_at, d.doc_type,
           0.0::float8 AS distance
    FROM documents d
    JOIN chunks c ON c.document_id = d.id
    WHERE regexp_replace(coalesce(d.title, ''), '\D', '', 'g') = ANY(%s)
    """
    params: list[Any] = [numbers]
    if doc_type_filter:
        sql += " AND d.doc_type = %s"
        params.append(doc_type_filter)
    sql += " ORDER BY d.published_at DESC, c.chunk_index LIMIT %s"
    params.append(limit)
    return [dict(row) for row in await (await conn.execute(sql, params)).fetchall()]


async def retrieve_chunks(
    conn: psycopg.AsyncConnection,
    question: str,
    embedding_model: str,
    embedding_dim: int,
    k: int = 5,
    doc_type_filter: str | None = None,
) -> list[dict[str, Any]]:
    """
    Retrieve top-k chunks most similar to the question.
    
    Uses pgml.embed to embed the question on-the-fly and pgvector cosine similarity.
    The e5 model expects "query: " prefix for search queries.
    
    Args:
        conn: Database connection
        question: The search question (Portuguese or English)
        embedding_model: Model name (e.g. "intfloat/multilingual-e5-base")
        embedding_dim: Vector dimension (e.g. 768)
        k: Number of top chunks to return
        doc_type_filter: Optional doc_type to filter by (e.g. "Comunicado")
    
    Returns:
        List of dicts with keys: id, text, document_id, title, url, published_at, doc_type, distance
    """
    
    # Build the SQL query with optional doc_type filter
    where_clause = "WHERE c.embedding IS NOT NULL"
    if doc_type_filter:
        where_clause += " AND d.doc_type = %s"
    
    sql = f"""
    SELECT 
        c.id,
        c.text,
        c.document_id,
        d.title,
        d.url,
        d.published_at,
        d.doc_type,
        c.embedding <=> pgml.embed('{embedding_model}', 'query: ' || %s)::vector({embedding_dim}) as distance
    FROM chunks c
    JOIN documents d ON c.document_id = d.id
    {where_clause}
    ORDER BY distance ASC
    LIMIT %s
    """
    
    if doc_type_filter:
        rows = await (
            await conn.execute(sql, (question, doc_type_filter, k))
        ).fetchall()
    else:
        rows = await (
            await conn.execute(sql, (question, k))
        ).fetchall()
    
    result = [dict(row) for row in rows]

    # Hybrid step: if the question names a document number (e.g. "Comunicado 34.977"),
    # put that document's chunks first, then fill the rest with the semantic hits.
    numbers = _document_numbers(question)
    if numbers:
        exact = await _chunks_by_title_number(conn, numbers, k, doc_type_filter)
        if exact:
            seen = {c["id"] for c in exact}
            result = (exact + [c for c in result if c["id"] not in seen])[:k]
            logger.info("Title-number match %s: %d exact chunks", numbers, len(exact))

    logger.info(
        "Retrieved %d chunks for question (top distance: %.4f)",
        len(result),
        result[0]["distance"] if result else 0.0,
    )

    return result

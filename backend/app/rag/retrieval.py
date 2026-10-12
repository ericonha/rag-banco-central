"""
Retrieve relevant chunks by semantic similarity.

Uses pgvector cosine similarity with the e5 model.
"""
from __future__ import annotations

import logging
from typing import Any

import psycopg

logger = logging.getLogger(__name__)


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
    logger.info(
        "Retrieved %d chunks for question (top distance: %.4f)",
        len(result),
        result[0]["distance"] if result else None,
    )
    
    return result

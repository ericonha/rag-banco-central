"""
Retrieve relevant chunks by semantic similarity.

Uses pgvector cosine similarity with the e5 model.
"""
from __future__ import annotations

import logging
import re
from typing import Any

import psycopg

from app.rag.rerank import rerank_chunks

logger = logging.getLogger(__name__)


# Document numbers such as "34.977" or "34977" (embeddings are poor at matching identifiers).
_NUMBER_RE = re.compile(r"\b\d{1,3}(?:\.\d{3})+\b|\b\d{4,}\b")

# Short numbers ("Resolução BCB nº 598", "circular 3.978", "resolution 598") only count when a
# document keyword or "nº" comes right before them, so plain numbers in a question are ignored.
_KEYWORD_NUMBER_RE = re.compile(
    r"(?:n[º°o]\.?|n\.\s?[º°o]|n[úu]mero|number|no\.|"
    r"resolu[çc][ãa]o(?:\s+(?:bcb|cmn))?|circular(?:\s+bcb)?|comunicado|"
    r"instru[çc][ãa]o\s+normativa(?:\s+bcb)?|resolution|notice)"
    r"\s*(?:n[º°o]\.?\s*)?(\d{1,3}(?:\.\d{3})*|\d+)\b",
    re.IGNORECASE,
)


def _document_numbers(question: str) -> list[str]:
    """Return the document numbers mentioned in the question, as digits only."""
    found = [re.sub(r"\D", "", m) for m in _NUMBER_RE.findall(question)]
    found += [re.sub(r"\D", "", m) for m in _KEYWORD_NUMBER_RE.findall(question)]
    return list(dict.fromkeys(n for n in found if n))


async def _chunks_by_title_number(
    conn: psycopg.AsyncConnection,
    numbers: list[str],
    limit: int,
    doc_type_filter: str | None,
    since_days: int | None = None,
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
    if since_days:
        sql += " AND d.published_at >= now() - make_interval(days => %s)"
        params.append(since_days)
    sql += " ORDER BY d.published_at DESC, c.chunk_index LIMIT %s"
    params.append(limit)
    rows = await (await conn.execute(sql, params)).fetchall()
    return [{**dict(row), "pinned": True} for row in rows]


async def retrieve_chunks(
    conn: psycopg.AsyncConnection,
    question: str,
    embedding_model: str,
    embedding_dim: int,
    k: int = 5,
    doc_type_filter: str | None = None,
    hybrid: bool = True,
    rerank_model: str = "",
    rerank_candidates: int = 20,
    since_days: int | None = None,
    pinned_limit: int = 0,
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
        hybrid: also pin chunks of documents whose title number appears in the question
        rerank_model: pgml.rank cross-encoder; when set, `rerank_candidates` chunks are fetched
            and reordered, then cut to k (pinned exact matches stay first)
        rerank_candidates: how many candidates to fetch when reranking
        since_days: only documents published in the last N days
        pinned_limit: when > k and the question names a document number, return up to this many
            chunks of that document (in reading order) instead of only k, so "summarize
            Resolução 525" sees more than the first articles. 0 keeps the strict top-k.
    
    Returns:
        List of dicts with keys: id, text, document_id, title, url, published_at, doc_type, distance
    """
    
    fetch_k = max(k, rerank_candidates) if rerank_model else k

    where_clause = "WHERE c.embedding IS NOT NULL"
    filter_params: list[Any] = []
    if doc_type_filter:
        where_clause += " AND d.doc_type = %s"
        filter_params.append(doc_type_filter)
    if since_days:
        where_clause += " AND d.published_at >= now() - make_interval(days => %s)"
        filter_params.append(since_days)

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

    rows = await (await conn.execute(sql, (question, *filter_params, fetch_k))).fetchall()

    result = [dict(row) for row in rows]

    # Hybrid step: if the question names a document number (e.g. "Comunicado 34.977"),
    # put that document's chunks first, then fill the rest with the semantic hits.
    numbers = _document_numbers(question) if hybrid else []
    if numbers:
        exact_limit = max(fetch_k, pinned_limit)
        exact = await _chunks_by_title_number(conn, numbers, exact_limit, doc_type_filter, since_days)
        if exact:
            if pinned_limit > k:
                k = max(k, min(len(exact), pinned_limit))
                fetch_k = max(fetch_k, k)
            seen = {c["id"] for c in exact}
            result = (exact + [c for c in result if c["id"] not in seen])[:fetch_k]
            logger.info("Title-number match %s: %d exact chunks", numbers, len(exact))

    if rerank_model:
        result = await rerank_chunks(conn, question, result, rerank_model, k)
    else:
        result = result[:k]

    logger.info(
        "Retrieved %d chunks for question (top distance: %.4f)",
        len(result),
        result[0]["distance"] if result else 0.0,
    )

    return result

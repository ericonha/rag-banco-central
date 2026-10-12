"""Insert and manage chunks in the database."""
from __future__ import annotations

import logging
from typing import Any

import psycopg

logger = logging.getLogger(__name__)


async def insert_chunks(
    conn: psycopg.AsyncConnection,
    document_id: int,
    chunks: list[dict[str, Any]],
) -> None:
    """
    Insert chunks for a document. Deletes existing chunks first (idempotent).
    
    chunks: list of dicts with keys: chunk_index, text, token_count
    """
    # Delete old chunks for this document
    await conn.execute("DELETE FROM chunks WHERE document_id = %s", (document_id,))
    
    # Insert new chunks
    for chunk in chunks:
        await conn.execute(
            """
            INSERT INTO chunks (document_id, chunk_index, text, token_count)
            VALUES (%s, %s, %s, %s)
            """,
            (document_id, chunk["chunk_index"], chunk["text"], chunk["token_count"]),
        )
    
    logger.info("Inserted %d chunks for document_id=%d", len(chunks), document_id)


async def get_unchunked_documents(conn: psycopg.AsyncConnection) -> list[dict[str, Any]]:
    """Get documents that have no chunks yet."""
    rows = await (
        await conn.execute(
            """
            SELECT d.id, d.source, d.url, d.title, d.doc_type, d.published_at, d.raw_text
            FROM documents d
            LEFT JOIN chunks c ON d.id = c.document_id
            WHERE c.id IS NULL
            ORDER BY d.published_at DESC
            """
        )
    ).fetchall()
    return rows


async def get_chunks_needing_embedding(
    conn: psycopg.AsyncConnection, limit: int = 32
) -> list[dict[str, Any]]:
    """Get chunks without embeddings for a batch embedding job."""
    rows = await (
        await conn.execute(
            "SELECT id, document_id, text FROM chunks WHERE embedding IS NULL LIMIT %s",
            (limit,),
        )
    ).fetchall()
    return rows


async def store_embeddings(
    conn: psycopg.AsyncConnection,
    embedding_model: str,
    chunk_embeddings: dict[int, list[float]],
) -> None:
    """Store embeddings for multiple chunks."""
    for chunk_id, embedding in chunk_embeddings.items():
        await conn.execute(
            """
            UPDATE chunks
            SET embedding = %s::vector, embedding_model = %s
            WHERE id = %s
            """,
            (embedding, embedding_model, chunk_id),
        )
    logger.info("Stored %d embeddings", len(chunk_embeddings))

"""
Document upsert logic.

Deduplication strategy:
  - Primary key: ``url`` (UNIQUE constraint)
  - On conflict: update only when content_hash differs (document was edited).
"""
from __future__ import annotations

import logging

import psycopg

from app.scraping.base import Document

logger = logging.getLogger(__name__)

_UPSERT_SQL = """
INSERT INTO documents
    (source, url, title, doc_type, published_at, language, content_hash, raw_text)
VALUES
    (%(source)s, %(url)s, %(title)s, %(doc_type)s,
     %(published_at)s, %(language)s, %(content_hash)s, %(raw_text)s)
ON CONFLICT (url) DO UPDATE
    SET title        = EXCLUDED.title,
        raw_text     = EXCLUDED.raw_text,
        content_hash = EXCLUDED.content_hash,
        fetched_at   = now()
    WHERE documents.content_hash <> EXCLUDED.content_hash
RETURNING id, (xmax = 0) AS inserted
"""


async def upsert_document(
    conn: psycopg.AsyncConnection, doc: Document
) -> tuple[int, bool]:
    """
    Insert or update *doc* in ``documents``.

    Returns ``(id, inserted)`` where *inserted* is True for new rows
    and False for unchanged existing rows.
    Rows where the content hash did not change are left untouched and
    the function returns ``(existing_id, False)`` by fetching it.
    """
    row = await (
        await conn.execute(
            _UPSERT_SQL,
            {
                "source": doc.source,
                "url": doc.url,
                "title": doc.title,
                "doc_type": doc.doc_type,
                "published_at": doc.published_at,
                "language": doc.language,
                "content_hash": doc.content_hash,
                "raw_text": doc.raw_text,
            },
        )
    ).fetchone()

    if row:
        doc_id: int = row["id"]
        inserted: bool = row["inserted"]
        logger.debug("upsert_document: id=%d inserted=%s url=%s", doc_id, inserted, doc.url)
        return doc_id, inserted

    # No row returned means content_hash was identical → already up-to-date.
    existing = await (
        await conn.execute(
            "SELECT id FROM documents WHERE url = %(url)s",
            {"url": doc.url},
        )
    ).fetchone()
    assert existing is not None, f"upsert returned nothing and url not found: {doc.url}"
    return existing["id"], False

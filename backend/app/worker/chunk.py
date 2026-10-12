"""
Chunk all documents and insert into the chunks table.

Usage:
    python -m app.worker.chunk
"""
from __future__ import annotations

import asyncio
import logging
import sys

from app.chunking.chunker import PortugueseRegulationChunker
from app.db.chunks import get_unchunked_documents, insert_chunks
from app.db.session import get_conn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("worker.chunk")


async def run() -> None:
    """Chunk all unchunked documents."""
    chunker = PortugueseRegulationChunker()
    total_chunks = 0
    errors: list[str] = []

    async with get_conn() as conn:
        docs = await get_unchunked_documents(conn)
        logger.info("Found %d unchunked documents", len(docs))

        for doc in docs:
            try:
                chunks_obj = chunker.chunk(doc["raw_text"], doc["id"])
                if not chunks_obj:
                    logger.warning("[%s] No chunks produced for %s", doc["id"], doc["title"])
                    continue

                chunk_dicts = [
                    {
                        "chunk_index": c.chunk_index,
                        "text": c.text,
                        "token_count": c.token_count,
                    }
                    for c in chunks_obj
                ]

                await insert_chunks(conn, doc["id"], chunk_dicts)
                await conn.commit()
                total_chunks += len(chunk_dicts)
                logger.info(
                    "[%d] %s: %d chunks",
                    doc["id"],
                    doc["title"][:60],
                    len(chunk_dicts),
                )
            except Exception as exc:
                msg = f"Document {doc['id']} ({doc['url']}): {exc}"
                logger.error(msg)
                errors.append(msg)
                await conn.rollback()

    logger.info("Chunking done: %d total chunks, %d errors", total_chunks, len(errors))
    if errors:
        for err in errors:
            logger.error(err)
        sys.exit(1)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()

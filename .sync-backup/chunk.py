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
from app.observability.async_tracker import track_run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("worker.chunk")


async def run() -> None:
    """Chunk all unchunked documents with tracking."""
    chunker = PortugueseRegulationChunker()

    async with get_conn() as conn:
        async with track_run(conn, "chunk", {"chunk_size": 512}) as run:
            docs = await get_unchunked_documents(conn)
            logger.info("Found %d unchunked documents", len(docs))

            for doc in docs:
                try:
                    chunks_obj = chunker.chunk(doc["raw_text"], doc["id"])
                    if not chunks_obj:
                        logger.warning("[%s] No chunks produced for %s", doc["id"], doc["title"])
                        await run.event("warning", f"No chunks produced for {doc['id']}", 
                                      document_id=doc["id"], title=doc["title"])
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
                    await run.ok(count=len(chunk_dicts))
                    logger.info(
                        "[%d] %s: %d chunks",
                        doc["id"],
                        doc["title"][:60],
                        len(chunk_dicts),
                    )
                except Exception as exc:
                    msg = f"Document {doc['id']} ({doc['url']}): {exc}"
                    logger.error(msg)
                    await run.fail(doc["id"], exc, {"url": doc["url"], "title": doc["title"]})
                    await conn.rollback()

    logger.info("Chunking done: %d total chunks, %d failed", run.items_ok, run.items_failed)
    if run.items_failed > 0:
        sys.exit(1)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()

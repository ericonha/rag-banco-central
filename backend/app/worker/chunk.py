"""
Chunk all documents and insert into the chunks table.

Usage:
    python -m app.worker.chunk             # only documents without chunks
    python -m app.worker.chunk --rechunk   # delete ALL chunks and rebuild them (then run embed)
"""
from __future__ import annotations

import argparse
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


async def run(rechunk: bool = False) -> None:
    """Chunk all unchunked documents with tracking (rechunk=True discards existing chunks first)."""
    chunker = PortugueseRegulationChunker()

    async with get_conn() as conn:
        async with track_run("chunk", {"chunk_size": 512, "rechunk": rechunk}) as run:
            if rechunk:
                await conn.execute("DELETE FROM chunks")
                await conn.commit()
                logger.warning("--rechunk: all existing chunks deleted; rebuilding")
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
    parser = argparse.ArgumentParser(description="Chunk documents")
    parser.add_argument(
        "--rechunk", action="store_true", help="delete all chunks and rebuild them from raw_text"
    )
    args = parser.parse_args()
    asyncio.run(run(rechunk=args.rechunk))


if __name__ == "__main__":
    main()

"""
Embed chunks using pgml.embed inside PostgreSQL.

Usage:
    python -m app.worker.embed [--batch-size N]

The e5 model expects "passage: " prefix for chunks and "query: " for searches.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from app.config import get_settings
from app.db.chunks import get_chunks_needing_embedding, store_embeddings
from app.db.session import get_conn
from app.observability.async_tracker import track_run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("worker.embed")


async def run(batch_size: int) -> None:
    """Embed all chunks without embeddings with tracking."""
    settings = get_settings()
    model = settings.embedding_model
    
    if not model:
        logger.error("EMBEDDING_MODEL not set in .env")
        sys.exit(1)

    logger.info("Starting embedding: model=%s batch_size=%d", model, batch_size)

    async with get_conn() as conn:
        async with track_run(conn, "embed", {"model": model, "batch_size": batch_size}) as run:
            batch_num = 0
            while True:
                # Fetch a batch
                chunks = await get_chunks_needing_embedding(conn, limit=batch_size)
                if not chunks:
                    logger.info("No more chunks to embed")
                    break

                batch_num += 1
                logger.info("Embedding batch %d of %d chunks", batch_num, len(chunks))

                try:
                    # Use pgml.embed in a single query to embed all chunks at once
                    # Each chunk text gets the "passage: " prefix per e5 model spec
                    chunk_ids = [c["id"] for c in chunks]
                    
                    # Build a SQL query that embeds and updates in one go
                    update_sql = f"""
                    UPDATE chunks
                    SET embedding = pgml.embed('{model}', 'passage: ' || text)::vector({settings.embedding_dim}),
                        embedding_model = '{model}'
                    WHERE id = ANY($1)
                    RETURNING id
                    """
                    
                    result = await (
                        await conn.execute(update_sql, (chunk_ids,))
                    ).fetchall()
                    
                    await conn.commit()
                    await run.ok(count=len(result))
                    logger.info("Batch %d: Embedded %d chunks", batch_num, len(result))

                except Exception as exc:
                    msg = f"Batch {batch_num} embedding failed: {exc}"
                    logger.error(msg)
                    await run.fail(f"batch_{batch_num}", exc, {"batch_size": len(chunks)})
                    await conn.rollback()
                    # Continue with next batch instead of failing entirely
                    break

    logger.info("Embedding done: %d total embedded, %d failed", run.items_ok, run.items_failed)
    if run.items_failed > 0:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Embed chunks using PostgresML")
    parser.add_argument("--batch-size", type=int, default=32, help="Chunks per batch")
    args = parser.parse_args()
    asyncio.run(run(args.batch_size))


if __name__ == "__main__":
    main()

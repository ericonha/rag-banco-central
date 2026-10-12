"""
Run the whole ingestion pipeline once: scrape -> chunk -> embed.

Usage:
    python -m app.worker.pipeline [--days N] [--batch-size N]

Each stage is tracked in pipeline_runs by its own module. A failing stage does
not stop the later ones: chunk/embed also process any backlog from earlier runs.
A Postgres advisory lock prevents two pipelines from running at the same time
(e.g. the scheduler and a manual run).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

import psycopg

from app.config import get_settings

logger = logging.getLogger("worker.pipeline")

LOCK_KEY = 726_001  # arbitrary app-wide advisory lock id


async def _run_stage(name: str, coro_factory) -> bool:
    """Run one stage; return True on success. SystemExit(1) means 'finished with errors'."""
    logger.info("=== stage %s: start ===", name)
    try:
        await coro_factory()
    except SystemExit as exc:
        ok = exc.code in (0, None)
        logger.warning("stage %s finished with exit code %s", name, exc.code)
        return ok
    except Exception:
        logger.exception("stage %s crashed", name)
        return False
    logger.info("=== stage %s: ok ===", name)
    return True


async def run_pipeline(days: int, batch_size: int) -> bool:
    """Returns True if all stages succeeded, False otherwise (or if already running)."""
    # Imported lazily so the scheduler math can be tested without psycopg installed.
    from app.worker import chunk, embed, scrape

    settings = get_settings()
    async with await psycopg.AsyncConnection.connect(settings.database_url, autocommit=True) as lock_conn:
        cur = await lock_conn.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_KEY,))
        row = await cur.fetchone()
        if not row or not row[0]:
            logger.warning("Another pipeline run is in progress; skipping")
            return False
        try:
            results = {
                "scrape": await _run_stage("scrape", lambda: scrape.run(days)),
                "chunk": await _run_stage("chunk", chunk.run),
                "embed": await _run_stage("embed", lambda: embed.run(batch_size)),
            }
        finally:
            await lock_conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))

    failed = [k for k, v in results.items() if not v]
    if failed:
        logger.error("Pipeline finished with problems in: %s", ", ".join(failed))
    else:
        logger.info("Pipeline finished OK")
    return not failed


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )
    parser = argparse.ArgumentParser(description="Run scrape -> chunk -> embed")
    parser.add_argument("--days", type=int, default=7, help="Days back to scrape (default: 7)")
    parser.add_argument("--batch-size", type=int, default=32, help="Embedding batch size")
    args = parser.parse_args()
    ok = asyncio.run(run_pipeline(args.days, args.batch_size))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

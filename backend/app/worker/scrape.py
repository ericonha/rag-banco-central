"""
CLI entrypoint for the scrape-and-ingest pipeline.

Usage (inside the api/worker container):

    python -m app.worker.scrape              # last 7 days (default)
    python -m app.worker.scrape --days 30    # last 30 days
    python -m app.worker.scrape --days 1     # yesterday + today (daily cron)

The script:
  1. For each source, calls list_new(since) to get DocRefs.
  2. Fetches the full Document for each ref.
  3. Upserts into ``documents`` (skips unchanged).
  4. Writes a ``pipeline_runs`` row with the outcome (with fallback to ``ingest_runs``).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timedelta, timezone

from app.db.documents import upsert_document
from app.db.session import get_conn
from app.scraping.sources import ALL_SOURCES
from app.observability.async_tracker import track_run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("worker.scrape")


async def run(days: int) -> None:
    since = datetime.now(tz=timezone.utc) - timedelta(days=days)
    logger.info("Starting scrape run: since=%s, sources=%d", since.date(), len(ALL_SOURCES))

    async with get_conn() as conn:
        # Use the new pipeline_runs tracking (with fallback to ingest_runs)
        async with track_run("scrape", {"days": days}) as run:
            for source in ALL_SOURCES:
                logger.info("[%s] listing new documents since %s…", source.source_name, since.date())
                try:
                    refs = await source.list_new(since)
                except Exception as exc:
                    msg = f"{source.source_name}: list_new failed: {exc}"
                    logger.error(msg)
                    await run.fail(source.source_name, exc, {"stage": "list_new"})
                    continue

                logger.info("[%s] %d refs to process", source.source_name, len(refs))

                for ref in refs:
                    try:
                        doc = await source.fetch(ref)
                        doc_id, inserted = await upsert_document(conn, doc)
                        await conn.commit()
                        if inserted:
                            await run.ok()
                            logger.info("  NEW  [%d] %s", doc_id, doc.title)
                        else:
                            logger.debug("  SKIP %s (unchanged)", ref.url)
                    except Exception as exc:
                        msg = f"{ref.url}: {exc}"
                        logger.error("  ERR  %s", msg)
                        await run.fail(ref.url, exc, {"source": source.source_name})
                        await conn.rollback()

        logger.info(
            "Scrape run finished: ok=%d failed=%d status=%s",
            run.items_ok, run.items_failed, "ok" if run.items_failed == 0 else "done_with_errors",
        )
        
        # Also write to ingest_runs for backward compatibility
        try:
            status = "done" if run.items_failed == 0 else "done_with_errors"
            await conn.execute(
                """
                INSERT INTO ingest_runs (status, new_docs, errors, finished_at)
                VALUES ($1, $2, $3, now())
                """,
                status,
                run.items_ok,
                None if run.items_failed == 0 else f"{run.items_failed} items failed",
            )
            await conn.commit()
        except Exception as e:
            logger.warning(f"Failed to write to ingest_runs (backward compat): {e}")
        
        if run.items_failed > 0:
            sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="BCB scraper")
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="How many days back to look (default: 7)",
    )
    args = parser.parse_args()
    asyncio.run(run(args.days))


if __name__ == "__main__":
    main()

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
  4. Writes an ``ingest_runs`` row with the outcome.
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

    total_new = 0
    errors: list[str] = []

    async with get_conn() as conn:
        # Record the start of this run.
        run_row = await (
            await conn.execute(
                "INSERT INTO ingest_runs (status) VALUES ('running') RETURNING id"
            )
        ).fetchone()
        assert run_row is not None
        run_id: int = run_row["id"]
        await conn.commit()

        for source in ALL_SOURCES:
            logger.info("[%s] listing new documents since %s…", source.source_name, since.date())
            try:
                refs = await source.list_new(since)
            except Exception as exc:
                msg = f"{source.source_name}: list_new failed: {exc}"
                logger.error(msg)
                errors.append(msg)
                continue

            logger.info("[%s] %d refs to process", source.source_name, len(refs))

            for ref in refs:
                try:
                    doc = await source.fetch(ref)
                    doc_id, inserted = await upsert_document(conn, doc)
                    await conn.commit()
                    if inserted:
                        total_new += 1
                        logger.info("  NEW  [%d] %s", doc_id, doc.title)
                    else:
                        logger.debug("  SKIP %s (unchanged)", ref.url)
                except Exception as exc:
                    msg = f"{ref.url}: {exc}"
                    logger.error("  ERR  %s", msg)
                    errors.append(msg)
                    await conn.rollback()

        # Finalise the ingest_runs row.
        status = "done" if not errors else "done_with_errors"
        await conn.execute(
            """
            UPDATE ingest_runs
               SET finished_at = now(),
                   status      = %(status)s,
                   new_docs    = %(new_docs)s,
                   errors      = %(errors)s
             WHERE id = %(id)s
            """,
            {
                "status": status,
                "new_docs": total_new,
                "errors": "\n".join(errors) if errors else None,
                "id": run_id,
            },
        )
        await conn.commit()

    logger.info(
        "Scrape run finished: new=%d errors=%d status=%s",
        total_new, len(errors), status,
    )
    if errors:
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

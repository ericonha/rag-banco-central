"""
Long-running scheduler: runs the pipeline every day at PIPELINE_SCHEDULE_TIME.

Env vars:
    PIPELINE_SCHEDULE_TIME  HH:MM, default 06:00
    PIPELINE_TZ             IANA zone, default $TZ or America/Sao_Paulo
    PIPELINE_SCRAPE_DAYS    days back to scrape each run, default 2 (upserts dedupe)
    PIPELINE_EMBED_BATCH_SIZE  default 32
    PIPELINE_RUN_ON_START   true/false, default false
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger("worker.scheduler")


def parse_hhmm(value: str) -> tuple[int, int]:
    hour_s, minute_s = value.strip().split(":")
    hour, minute = int(hour_s), int(minute_s)
    if not (0 <= hour < 24 and 0 <= minute < 60):
        raise ValueError(f"invalid time {value!r}")
    return hour, minute


def next_run(now: datetime, hour: int, minute: int) -> datetime:
    """Next wall-clock occurrence of hour:minute strictly after `now` (tz-aware)."""
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        # Build from the date so DST changes keep the wall-clock time.
        tomorrow = (now + timedelta(days=1)).date()
        candidate = datetime(tomorrow.year, tomorrow.month, tomorrow.day, hour, minute, tzinfo=now.tzinfo)
    return candidate


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


async def main() -> None:
    from app.worker.pipeline import run_pipeline

    hour, minute = parse_hhmm(os.environ.get("PIPELINE_SCHEDULE_TIME", "06:00"))
    tz = ZoneInfo(os.environ.get("PIPELINE_TZ") or os.environ.get("TZ") or "America/Sao_Paulo")
    days = int(os.environ.get("PIPELINE_SCRAPE_DAYS", "2"))
    batch = int(os.environ.get("PIPELINE_EMBED_BATCH_SIZE", "32"))

    logger.info("Scheduler up: daily at %02d:%02d (%s), scrape_days=%d", hour, minute, tz.key, days)

    if _flag("PIPELINE_RUN_ON_START"):
        logger.info("PIPELINE_RUN_ON_START set: running now")
        await _safe_run(run_pipeline, days, batch)

    while True:
        now = datetime.now(tz)
        target = next_run(now, hour, minute)
        wait = (target - now).total_seconds()
        logger.info("Next run at %s (in %.1f h)", target.isoformat(timespec="minutes"), wait / 3600)
        await asyncio.sleep(max(wait, 1))
        await _safe_run(run_pipeline, days, batch)


async def _safe_run(run_pipeline, days: int, batch: int) -> None:
    try:
        await run_pipeline(days, batch)
    except Exception:
        logger.exception("Pipeline run crashed; will retry at next schedule")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )
    asyncio.run(main())

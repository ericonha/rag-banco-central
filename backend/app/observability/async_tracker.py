"""Pipeline run tracking (psycopg v3, async).

Each tracked run opens its OWN autocommit connection, so log rows are never
rolled back together with the worker's own transaction (workers call
``conn.rollback()`` after a failed item). Logging problems never break the
pipeline: if the tracking connection cannot be opened, the run still works and
only keeps in-memory counters.

Usage:
    async with track_run("scrape", {"days": 30}) as run:
        for item in items:
            try:
                await process(item)
                await run.ok()
            except Exception as exc:
                await run.fail(item, exc)
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.config import get_settings

logger = logging.getLogger(__name__)

_LEVELS = {"info", "warning", "error"}


class AsyncPipelineRun:
    """Handle for one pipeline run (one stage execution)."""

    def __init__(self, run_id: int | None, stage: str, conn: psycopg.AsyncConnection | None):
        self.run_id = run_id
        self.stage = stage
        self._conn = conn
        self.items_ok = 0
        self.items_failed = 0
        self.items_total = 0

    @property
    def has_errors(self) -> bool:
        return self.items_failed > 0

    async def ok(self, count: int = 1) -> None:
        self.items_ok += count
        self.items_total += count

    async def fail(self, item_id: Any, exc: BaseException, details: dict | None = None) -> None:
        self.items_failed += 1
        self.items_total += 1
        payload = {"item_id": str(item_id), "error": str(exc), "error_type": type(exc).__name__}
        if details:
            payload.update(details)
        await self._insert_event("error", f"Failed to process {item_id}", payload)

    async def event(self, level: str, message: str, **details: Any) -> None:
        if level not in _LEVELS:
            level = "info"
        await self._insert_event(level, message, details or None)

    async def _insert_event(self, level: str, message: str, details: dict | None) -> None:
        if self._conn is None or self.run_id is None:
            return
        try:
            await self._conn.execute(
                "INSERT INTO pipeline_events (run_id, level, message, details) "
                "VALUES (%s, %s, %s, %s)",
                (self.run_id, level, message, Jsonb(details) if details is not None else None),
            )
        except Exception as exc:  # logging must never break the pipeline
            logger.error("Failed to write pipeline event: %s", exc)

    async def _finish(self, started_at: datetime, error: str | None) -> None:
        conn = self._conn
        if conn is None:
            return
        finished_at = datetime.now(tz=timezone.utc)
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)
        if error:
            status = "failed"
        elif self.items_failed:
            status = "done_with_errors"
        else:
            status = "ok"
        try:
            await conn.execute(
                "UPDATE pipeline_runs SET status = %s, finished_at = %s, duration_ms = %s, "
                "items_total = %s, items_ok = %s, items_failed = %s, error = %s WHERE id = %s",
                (
                    status,
                    finished_at,
                    duration_ms,
                    self.items_total,
                    self.items_ok,
                    self.items_failed,
                    error,
                    self.run_id,
                ),
            )
            logger.info(
                "Pipeline run %s (%s): %s (%d ok, %d failed, %dms)",
                self.run_id, self.stage, status, self.items_ok, self.items_failed, duration_ms,
            )
        except Exception as exc:
            logger.error("Failed to finalize pipeline run %s: %s", self.run_id, exc)
        finally:
            try:
                await conn.close()
            except Exception:
                pass


@asynccontextmanager
async def track_run(stage: str, params: dict[str, Any] | None = None) -> AsyncIterator[AsyncPipelineRun]:
    """Record a pipeline stage execution in ``pipeline_runs`` / ``pipeline_events``."""
    started_at = datetime.now(tz=timezone.utc)
    conn: psycopg.AsyncConnection | None = None
    run_id: int | None = None
    try:
        conn = await psycopg.AsyncConnection.connect(
            get_settings().database_url, row_factory=dict_row, autocommit=True
        )
        cur = await conn.execute(
            "INSERT INTO pipeline_runs (stage, status, params, started_at) "
            "VALUES (%s, 'running', %s, %s) RETURNING id",
            (stage, Jsonb(params) if params is not None else None, started_at),
        )
        row = await cur.fetchone()
        run_id = row["id"] if row else None
    except Exception as exc:
        logger.error("Could not start pipeline run tracking for %s: %s", stage, exc)
        if conn is not None:
            try:
                await conn.close()
            except Exception:
                pass
        conn = None

    run = AsyncPipelineRun(run_id, stage, conn)
    error: str | None = None
    try:
        yield run
    except BaseException as exc:
        error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        await run._finish(started_at, error)

"""Async context manager for tracking pipeline stage execution with asyncpg."""

import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, Optional

logger = logging.getLogger(__name__)


class AsyncPipelineRun:
    """Represents a single async pipeline run."""
    
    def __init__(self, run_id: int, stage: str, conn):
        self.run_id = run_id
        self.stage = stage
        self.conn = conn
        self.items_ok = 0
        self.items_failed = 0
        self.items_total = 0
        self.has_errors = False
    
    async def ok(self, count: int = 1) -> None:
        """Mark items as successfully processed."""
        self.items_ok += count
        self.items_total += count
    
    async def fail(self, item_id: Any, exc: Exception, details: Optional[Dict] = None) -> None:
        """Record a failure for an item."""
        self.items_failed += 1
        self.items_total += 1
        self.has_errors = True
        
        # Log the event to pipeline_events
        try:
            event_details = {"item_id": str(item_id), "error": str(exc)}
            if details:
                event_details.update(details)
            
            await self.conn.execute(
                """
                INSERT INTO pipeline_events (run_id, level, message, details)
                VALUES ($1, $2, $3, $4)
                """,
                self.run_id,
                "error",
                f"Failed to process {item_id}",
                json.dumps(event_details),
            )
        except Exception as e:
            logger.error(f"Failed to log event: {e}")
    
    async def event(self, level: str, message: str, **details) -> None:
        """Log a generic event to pipeline_events."""
        try:
            await self.conn.execute(
                """
                INSERT INTO pipeline_events (run_id, level, message, details)
                VALUES ($1, $2, $3, $4)
                """,
                self.run_id,
                level,
                message,
                json.dumps(details) if details else None,
            )
        except Exception as e:
            logger.error(f"Failed to log event: {e}")


@asynccontextmanager
async def track_run(
    conn,
    stage: str,
    params: Optional[Dict[str, Any]] = None,
) -> AsyncGenerator[AsyncPipelineRun, None]:
    """
    Async context manager for tracking a pipeline stage execution.
    
    Usage:
        async with track_run(conn, "scrape", {"days": 30}) as run:
            for item in items:
                try:
                    await process(item)
                    await run.ok()
                except Exception as e:
                    await run.fail(item, e)
    """
    
    started_at = datetime.utcnow()
    run_id = None
    
    try:
        # Create run record with status 'running'
        row = await (
            await conn.execute(
                """
                INSERT INTO pipeline_runs (stage, status, params, started_at)
                VALUES ($1, $2, $3, $4)
                RETURNING id
                """,
                stage,
                "running",
                json.dumps(params) if params else None,
                started_at,
            )
        ).fetchone()
        
        if row is None:
            raise RuntimeError("Failed to create pipeline run")
        
        run_id = row["id"]
        run = AsyncPipelineRun(run_id, stage, conn)
        
        yield run
        
    except Exception as e:
        logger.error(f"Error creating pipeline run: {e}")
        raise
    
    finally:
        # Finalize the run record
        if run_id is not None:
            finished_at = datetime.utcnow()
            duration_ms = int((finished_at - started_at).total_seconds() * 1000)
            
            # Determine final status
            status = "done_with_errors" if run.items_failed > 0 else "ok"
            
            try:
                await conn.execute(
                    """
                    UPDATE pipeline_runs
                    SET status = $1,
                        finished_at = $2,
                        duration_ms = $3,
                        items_total = $4,
                        items_ok = $5,
                        items_failed = $6
                    WHERE id = $7
                    """,
                    status,
                    finished_at,
                    duration_ms,
                    run.items_total,
                    run.items_ok,
                    run.items_failed,
                    run_id,
                )
                
                logger.info(
                    f"Pipeline run {run_id} ({stage}): {status} "
                    f"({run.items_ok} ok, {run.items_failed} failed, {duration_ms}ms)"
                )
            except Exception as e:
                logger.error(f"Failed to finalize pipeline run: {e}")
                # Don't raise - let the pipeline continue even if logging fails

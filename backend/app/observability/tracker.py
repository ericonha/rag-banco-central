"""Context manager for tracking pipeline stage execution."""

import json
import logging
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Optional, Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
import os

logger = logging.getLogger(__name__)


class PipelineRun:
    """Represents a single pipeline run (scrape, chunk, or embed stage)."""
    
    def __init__(self, run_id: int, stage: str, session: Session):
        self.run_id = run_id
        self.stage = stage
        self.session = session
        self.items_ok = 0
        self.items_failed = 0
        self.items_total = 0
        self.has_errors = False
    
    def ok(self, count: int = 1) -> None:
        """Mark items as successfully processed."""
        self.items_ok += count
        self.items_total += count
    
    def fail(self, item_id: Any, exc: Exception, details: Optional[Dict] = None) -> None:
        """Record a failure for an item."""
        self.items_failed += 1
        self.items_total += 1
        self.has_errors = True
        
        # Log the event to pipeline_events
        try:
            event_details = {"item_id": str(item_id), "error": str(exc)}
            if details:
                event_details.update(details)
            
            sql = text("""
                INSERT INTO pipeline_events (run_id, level, message, details)
                VALUES (:run_id, :level, :message, :details)
            """)
            
            self.session.execute(sql, {
                "run_id": self.run_id,
                "level": "error",
                "message": f"Failed to process {item_id}",
                "details": json.dumps(event_details),
            })
            self.session.commit()
        except SQLAlchemyError as e:
            logger.error(f"Failed to log event: {e}")
    
    def event(self, level: str, message: str, **details) -> None:
        """Log a generic event to pipeline_events."""
        try:
            sql = text("""
                INSERT INTO pipeline_events (run_id, level, message, details)
                VALUES (:run_id, :level, :message, :details)
            """)
            
            self.session.execute(sql, {
                "run_id": self.run_id,
                "level": level,
                "message": message,
                "details": json.dumps(details) if details else None,
            })
            self.session.commit()
        except SQLAlchemyError as e:
            logger.error(f"Failed to log event: {e}")


@contextmanager
def track_run(
    session: Session,
    stage: str,
    params: Optional[Dict[str, Any]] = None,
) -> Generator[PipelineRun, None, None]:
    """
    Context manager for tracking a pipeline stage execution.
    
    Usage:
        with track_run(session, "scrape", {"days": 30}) as run:
            for item in items:
                try:
                    process(item)
                    run.ok()
                except Exception as e:
                    run.fail(item, e)
    """
    
    started_at = datetime.utcnow()
    run_id = None
    
    try:
        # Create run record with status 'running'
        sql = text("""
            INSERT INTO pipeline_runs (stage, status, params, started_at)
            VALUES (:stage, :status, :params, :started_at)
            RETURNING id
        """)
        
        result = session.execute(sql, {
            "stage": stage,
            "status": "running",
            "params": json.dumps(params) if params else None,
            "started_at": started_at,
        })
        session.commit()
        
        run_id = result.scalar()
        run = PipelineRun(run_id, stage, session)
        
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
            if run.items_failed > 0:
                status = "done_with_errors"
            else:
                status = "ok"
            
            try:
                sql = text("""
                    UPDATE pipeline_runs
                    SET status = :status,
                        finished_at = :finished_at,
                        duration_ms = :duration_ms,
                        items_total = :items_total,
                        items_ok = :items_ok,
                        items_failed = :items_failed
                    WHERE id = :run_id
                """)
                
                session.execute(sql, {
                    "run_id": run_id,
                    "status": status,
                    "finished_at": finished_at,
                    "duration_ms": duration_ms,
                    "items_total": run.items_total,
                    "items_ok": run.items_ok,
                    "items_failed": run.items_failed,
                })
                session.commit()
                
                logger.info(
                    f"Pipeline run {run_id} ({stage}): {status} "
                    f"({run.items_ok} ok, {run.items_failed} failed, {duration_ms}ms)"
                )
            except SQLAlchemyError as e:
                logger.error(f"Failed to finalize pipeline run: {e}")
                # Don't raise - let the pipeline continue even if logging fails

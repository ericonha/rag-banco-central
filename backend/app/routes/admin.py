"""
Admin endpoints for pipeline monitoring and query logs.

Endpoints:
- GET /api/admin/runs — list pipeline runs with filtering
- GET /api/admin/runs/{run_id} — get single run details
- GET /api/admin/runs/{run_id}/events — get events for a run
- GET /api/admin/queries — list query logs
- GET /api/admin/stats/pipeline — pipeline statistics by stage
- GET /api/admin/stats/queries — query performance statistics
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.session import get_conn

logger = logging.getLogger("admin")

router = APIRouter(prefix="/api/admin", tags=["admin"])


async def _scalar(conn, sql: str, params=None):
    """Return the first column of the first row (psycopg has no fetchval)."""
    cur = await conn.execute(sql, params)
    row = await cur.fetchone()
    return next(iter(row.values())) if row else None


# ============================================================================
# Response Models
# ============================================================================


class PipelineEventResponse(BaseModel):
    """Response for a pipeline event"""
    id: int
    run_id: int
    level: str  # info, warning, error
    document_id: Optional[int] = None
    chunk_id: Optional[int] = None
    message: str
    details: Optional[dict] = None
    created_at: datetime


class PipelineRunResponse(BaseModel):
    """Response for a pipeline run"""
    id: int
    stage: str  # scrape, chunk, embed
    status: str  # running, ok, done_with_errors, failed
    started_at: datetime
    finished_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    params: Optional[dict] = None
    items_total: int = 0
    items_ok: int = 0
    items_failed: int = 0
    error: Optional[str] = None


class QueryLogResponse(BaseModel):
    """Response for a query log"""
    id: int
    created_at: datetime
    question: str
    answer: Optional[str] = None
    retrieved: Optional[list[dict]] = None
    top_k: int = 5
    embedding_model: Optional[str] = None
    llm_model: Optional[str] = None
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    latency_retrieval_ms: Optional[int] = None
    latency_llm_ms: Optional[int] = None
    latency_total_ms: Optional[int] = None
    status: str = "ok"  # ok, error
    error: Optional[str] = None


class PipelineStatsResponse(BaseModel):
    """Pipeline statistics by stage"""
    stage: str
    total_runs: int
    successful_runs: int
    failed_runs: int
    avg_duration_ms: float
    total_items_processed: int
    total_items_failed: int
    last_run_at: Optional[datetime] = None
    last_run_status: Optional[str] = None


class QueryStatsResponse(BaseModel):
    """Query performance statistics"""
    total_queries: int
    successful_queries: int
    failed_queries: int
    avg_latency_retrieval_ms: float
    avg_latency_llm_ms: float
    avg_latency_total_ms: float
    avg_tokens_in: float
    avg_tokens_out: float
    queries_last_24h: int


class PaginatedResponse(BaseModel):
    """Paginated response wrapper"""
    items: list
    total: int
    page: int
    page_size: int
    total_pages: int


# ============================================================================
# Pipeline Runs Endpoints
# ============================================================================


@router.get("/runs", response_model=PaginatedResponse)
async def list_pipeline_runs(
    stage: Optional[str] = Query(None, description="Filter by stage: scrape, chunk, embed"),
    status: Optional[str] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
):
    """
    List pipeline runs with optional filtering.

    Filters:
    - stage: scrape, chunk, or embed
    - status: running, ok, done_with_errors, failed
    """
    try:
        async with get_conn() as conn:
            # Build WHERE clause
            where_parts = []
            params = []

            if stage:
                where_parts.append("stage = %s")
                params.append(stage)
            if status:
                where_parts.append("status = %s")
                params.append(status)

            where_clause = " AND ".join(where_parts) if where_parts else "1=1"

            # Get total count
            count_query = f"SELECT COUNT(*) FROM pipeline_runs WHERE {where_clause}"
            total = await _scalar(conn, count_query, params)

            # Get paginated results
            offset = (page - 1) * page_size
            query = f"""
                SELECT id, stage, status, started_at, finished_at, duration_ms,
                       params, items_total, items_ok, items_failed, error
                FROM pipeline_runs
                WHERE {where_clause}
                ORDER BY started_at DESC
                LIMIT %s OFFSET %s
            """
            params.extend([page_size, offset])

            rows = await (await conn.execute(query, params)).fetchall()

            items = [PipelineRunResponse(**dict(row)) for row in rows]
            total_pages = (total + page_size - 1) // page_size

            return PaginatedResponse(
                items=items,
                total=total,
                page=page,
                page_size=page_size,
                total_pages=total_pages,
            )

    except Exception as exc:
        logger.error("Error listing pipeline runs: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/runs/{run_id}", response_model=PipelineRunResponse)
async def get_pipeline_run(run_id: int):
    """Get details for a specific pipeline run."""
    try:
        async with get_conn() as conn:
            row = await (
                await conn.execute(
                    """
                    SELECT id, stage, status, started_at, finished_at, duration_ms,
                           params, items_total, items_ok, items_failed, error
                    FROM pipeline_runs
                    WHERE id = %s
                    """,
                    (run_id,),
                )
            ).fetchone()

            if not row:
                raise HTTPException(status_code=404, detail="Run not found")

            return PipelineRunResponse(**dict(row))

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error getting pipeline run %d: %s", run_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/runs/{run_id}/events", response_model=list[PipelineEventResponse])
async def get_pipeline_run_events(run_id: int):
    """Get all events for a specific pipeline run."""
    try:
        async with get_conn() as conn:
            rows = await (
                await conn.execute(
                    """
                    SELECT id, run_id, level, document_id, chunk_id, message, details, created_at
                    FROM pipeline_events
                    WHERE run_id = %s
                    ORDER BY created_at DESC
                    """,
                    (run_id,),
                )
            ).fetchall()

            return [PipelineEventResponse(**dict(row)) for row in rows]

    except Exception as exc:
        logger.error("Error getting events for run %d: %s", run_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ============================================================================
# Query Logs Endpoints
# ============================================================================


@router.get("/queries", response_model=PaginatedResponse)
async def list_queries(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    hours: int = Query(24, ge=1, description="Filter queries from last N hours"),
):
    """
    List query logs with time range filtering.

    - hours: show queries from last N hours (default 24)
    """
    try:
        async with get_conn() as conn:
            time_cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=hours)

            # Get total count
            total = await _scalar(
                conn,
                "SELECT COUNT(*) FROM query_logs WHERE created_at >= %s",
                (time_cutoff,),
            )

            # Get paginated results
            offset = (page - 1) * page_size
            rows = await (
                await conn.execute(
                    """
                    SELECT id, created_at, question, answer, retrieved, top_k,
                           embedding_model, llm_model, tokens_in, tokens_out,
                           latency_retrieval_ms, latency_llm_ms, latency_total_ms,
                           status, error
                    FROM query_logs
                    WHERE created_at >= %s
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (time_cutoff, page_size, offset),
                )
            ).fetchall()

            items = [QueryLogResponse(**dict(row)) for row in rows]
            total_pages = (total + page_size - 1) // page_size

            return PaginatedResponse(
                items=items,
                total=total,
                page=page,
                page_size=page_size,
                total_pages=total_pages,
            )

    except Exception as exc:
        logger.error("Error listing queries: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ============================================================================
# Statistics Endpoints
# ============================================================================


@router.get("/stats/pipeline", response_model=list[PipelineStatsResponse])
async def get_pipeline_stats():
    """Get pipeline statistics grouped by stage."""
    try:
        async with get_conn() as conn:
            rows = await (
                await conn.execute(
                    """
                    SELECT
                        stage,
                        COUNT(*) as total_runs,
                        COALESCE(SUM(CASE WHEN status IN ('ok', 'done_with_errors') THEN 1 ELSE 0 END), 0) as successful_runs,
                        COALESCE(SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END), 0) as failed_runs,
                        COALESCE(AVG(CASE WHEN duration_ms IS NOT NULL THEN duration_ms ELSE NULL END), 0) as avg_duration_ms,
                        COALESCE(SUM(items_total), 0) as total_items_processed,
                        COALESCE(SUM(items_failed), 0) as total_items_failed,
                        MAX(started_at) as last_run_at
                    FROM pipeline_runs
                    GROUP BY stage
                    ORDER BY stage
                    """
                )
            ).fetchall()

            stats = []
            for row in rows:
                row_dict = dict(row)
                # Get last run status
                last_status_row = await (
                    await conn.execute(
                        "SELECT status FROM pipeline_runs WHERE stage = %s ORDER BY started_at DESC LIMIT 1",
                        (row_dict['stage'],),
                    )
                ).fetchone()

                row_dict['last_run_status'] = last_status_row['status'] if last_status_row else None
                stats.append(PipelineStatsResponse(**row_dict))

            return stats

    except Exception as exc:
        logger.error("Error getting pipeline stats: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/stats/queries", response_model=QueryStatsResponse)
async def get_query_stats():
    """Get query performance statistics."""
    try:
        async with get_conn() as conn:
            row = await (
                await conn.execute(
                    """
                    SELECT
                        COUNT(*) as total_queries,
                        COALESCE(SUM(CASE WHEN status = 'ok' THEN 1 ELSE 0 END), 0) as successful_queries,
                        COALESCE(SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END), 0) as failed_queries,
                        COALESCE(AVG(CASE WHEN latency_retrieval_ms IS NOT NULL THEN latency_retrieval_ms ELSE NULL END), 0) as avg_latency_retrieval_ms,
                        COALESCE(AVG(CASE WHEN latency_llm_ms IS NOT NULL THEN latency_llm_ms ELSE NULL END), 0) as avg_latency_llm_ms,
                        COALESCE(AVG(CASE WHEN latency_total_ms IS NOT NULL THEN latency_total_ms ELSE NULL END), 0) as avg_latency_total_ms,
                        COALESCE(AVG(CASE WHEN tokens_in IS NOT NULL THEN tokens_in ELSE NULL END), 0) as avg_tokens_in,
                        COALESCE(AVG(CASE WHEN tokens_out IS NOT NULL THEN tokens_out ELSE NULL END), 0) as avg_tokens_out,
                        COUNT(CASE WHEN created_at >= NOW() - INTERVAL '24 hours' THEN 1 END) as queries_last_24h
                    FROM query_logs
                    """
                )
            ).fetchone()

            if not row:
                raise HTTPException(status_code=500, detail="Unable to fetch query statistics")

            return QueryStatsResponse(**dict(row))

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error getting query stats: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ============================================================================
# Documents dashboard
# ============================================================================


@router.get("/documents")
async def list_documents_dashboard(
    q: Optional[str] = None,
    doc_type: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Summary + paginated documents with chunk/embedding counts (for the live dashboard)."""
    where, params = ["TRUE"], []
    if q:
        where.append("(d.title ILIKE %s OR d.url ILIKE %s)")
        params += [f"%{q}%", f"%{q}%"]
    if doc_type:
        where.append("d.doc_type = %s")
        params.append(doc_type)
    where_sql = " AND ".join(where)

    try:
        async with get_conn() as conn:
            summary = await (
                await conn.execute(
                    """
                    SELECT
                      (SELECT COUNT(*) FROM documents) AS documents,
                      (SELECT COUNT(*) FROM chunks) AS chunks,
                      (SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL) AS embedded,
                      (SELECT COUNT(*) FROM documents d WHERE NOT EXISTS
                         (SELECT 1 FROM chunks c WHERE c.document_id = d.id)) AS without_chunks,
                      (SELECT MAX(fetched_at) FROM documents) AS last_fetched_at
                    """
                )
            ).fetchone()
            types = await (
                await conn.execute(
                    "SELECT COALESCE(doc_type, 'outros') AS doc_type, COUNT(*) AS count "
                    "FROM documents GROUP BY 1 ORDER BY 2 DESC"
                )
            ).fetchall()
            total = await _scalar(conn, f"SELECT COUNT(*) FROM documents d WHERE {where_sql}", params)
            rows = await (
                await conn.execute(
                    f"""
                    SELECT d.id, d.title, d.url, d.doc_type, d.published_at, d.fetched_at,
                           COUNT(c.id) AS chunks,
                           COUNT(c.embedding) AS embedded
                    FROM documents d
                    LEFT JOIN chunks c ON c.document_id = d.id
                    WHERE {where_sql}
                    GROUP BY d.id
                    ORDER BY COALESCE(d.published_at, d.fetched_at) DESC, d.id DESC
                    LIMIT %s OFFSET %s
                    """,
                    params + [limit, offset],
                )
            ).fetchall()
        return {
            "summary": dict(summary),
            "types": [dict(t) for t in types],
            "total": total or 0,
            "items": [dict(r) for r in rows],
        }
    except Exception as exc:
        logger.error("Error building documents dashboard: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


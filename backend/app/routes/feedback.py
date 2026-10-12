"""
Answer feedback (thumbs up/down).

- POST /api/messages/{id}/feedback   — value 1 / -1 / 0 (0 clears), optional comment
- GET  /api/admin/feedback           — counts + recent rated answers
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.session import get_conn

logger = logging.getLogger("feedback")

router = APIRouter(prefix="/api/messages", tags=["feedback"])
admin_router = APIRouter(prefix="/api/admin", tags=["admin"])


class FeedbackRequest(BaseModel):
    value: int = Field(..., ge=-1, le=1, description="1 = útil, -1 = não útil, 0 = remover")
    comment: str | None = Field(default=None, max_length=1000)


@router.post("/{message_id}/feedback")
async def set_feedback(message_id: int, body: FeedbackRequest) -> dict[str, Any]:
    value = body.value or None
    comment = (body.comment or "").strip() or None if value else None
    try:
        async with get_conn() as conn:
            cur = await conn.execute(
                """
                UPDATE messages
                SET feedback = %s,
                    feedback_comment = %s,
                    feedback_at = CASE WHEN %s::smallint IS NULL THEN NULL ELSE now() END
                WHERE id = %s AND role = 'assistant'
                RETURNING id
                """,
                (value, comment, value, message_id),
            )
            row = await cur.fetchone()
            await conn.commit()
    except Exception as exc:
        logger.error("Error saving feedback for %s: %s", message_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))
    if not row:
        raise HTTPException(status_code=404, detail="Assistant message not found")
    return {"id": message_id, "feedback": value or 0}


@admin_router.get("/feedback")
async def list_feedback(
    value: int | None = Query(None, ge=-1, le=1),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """Counts of 👍/👎 and the most recent rated answers (with the question that triggered them)."""
    where = "m.feedback IS NOT NULL" + (" AND m.feedback = %s" if value else "")
    params: list[Any] = [value] if value else []
    try:
        async with get_conn() as conn:
            counts = await (
                await conn.execute(
                    "SELECT COALESCE(SUM((feedback = 1)::int), 0) AS up, "
                    "COALESCE(SUM((feedback = -1)::int), 0) AS down FROM messages"
                )
            ).fetchone()
            rows = await (
                await conn.execute(
                    f"""
                    SELECT m.id, m.conversation_id::text AS conversation_id, m.feedback,
                           m.feedback_comment, m.feedback_at, m.content AS answer, m.grounding,
                           (SELECT u.content FROM messages u
                            WHERE u.conversation_id = m.conversation_id AND u.role = 'user' AND u.id < m.id
                            ORDER BY u.id DESC LIMIT 1) AS question
                    FROM messages m
                    WHERE {where}
                    ORDER BY m.feedback_at DESC NULLS LAST
                    LIMIT %s OFFSET %s
                    """,
                    (*params, limit, offset),
                )
            ).fetchall()
    except Exception as exc:
        logger.error("Error listing feedback: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
    up, down = int(counts["up"]), int(counts["down"])
    return {
        "up": up,
        "down": down,
        "total": up + down,
        "satisfaction": round(up / (up + down), 3) if up + down else None,
        "items": [dict(r) for r in rows],
    }

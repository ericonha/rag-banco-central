"""
Conversation history endpoints (persistent chat).

- GET    /api/conversations          — recent conversations (sidebar)
- GET    /api/conversations/{id}     — messages of one conversation
- GET    /api/conversations/{id}/export?format=md|json — download
- DELETE /api/conversations/{id}     — remove a conversation and its messages
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.db.session import get_conn
from app.export import render_json, render_markdown

logger = logging.getLogger("conversations")

router = APIRouter(prefix="/api/conversations", tags=["conversations"])

_TITLE_MAX = 80


@router.get("")
async def list_conversations(
    limit: int = 50,
    q: str | None = Query(None, max_length=200, description="Text contained in any message"),
    days: int | None = Query(None, ge=1, le=3650, description="Only conversations active in the last N days"),
) -> list[dict[str, Any]]:
    """Most recently active conversations that have at least one message."""
    limit = max(1, min(limit, 200))
    extra = ""
    params: list[Any] = []
    if q and q.strip():
        like = "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        extra += " AND EXISTS (SELECT 1 FROM messages m WHERE m.conversation_id = c.id AND m.content ILIKE %s)"
        params.append(like)
    if days:
        extra += (" AND (SELECT MAX(m.created_at) FROM messages m WHERE m.conversation_id = c.id)"
                  " >= now() - make_interval(days => %s)")
        params.append(days)
    try:
        async with get_conn() as conn:
            rows = await (
                await conn.execute(
                    """
                    SELECT c.id::text AS id,
                           c.language,
                           c.created_at,
                           COALESCE((SELECT m.content FROM messages m
                                     WHERE m.conversation_id = c.id AND m.role = 'user'
                                     ORDER BY m.id LIMIT 1), '') AS title,
                           (SELECT MAX(m.created_at) FROM messages m
                            WHERE m.conversation_id = c.id) AS updated_at,
                           (SELECT COUNT(*) FROM messages m
                            WHERE m.conversation_id = c.id) AS message_count
                    FROM conversations c
                    WHERE EXISTS (SELECT 1 FROM messages m WHERE m.conversation_id = c.id)
                    """ + extra + """
                    ORDER BY updated_at DESC
                    LIMIT %s
                    """,
                    (*params, limit),
                )
            ).fetchall()
    except Exception as exc:
        logger.error("Error listing conversations: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    result = []
    for row in rows:
        item = dict(row)
        title = " ".join(str(item["title"]).split())
        item["title"] = title if len(title) <= _TITLE_MAX else title[: _TITLE_MAX - 1] + "…"
        result.append(item)
    return result


@router.get("/{conversation_id}")
async def get_conversation(conversation_id: uuid.UUID) -> dict[str, Any]:
    """Messages of a conversation. Unknown ids return an empty list (new conversation)."""
    try:
        async with get_conn() as conn:
            rows = await (
                await conn.execute(
                    """
                    SELECT id, role, content, sources, created_at, feedback, grounding
                    FROM messages
                    WHERE conversation_id = %s
                    ORDER BY id
                    """,
                    (conversation_id,),
                )
            ).fetchall()
    except Exception as exc:
        logger.error("Error loading conversation %s: %s", conversation_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))

    return {"conversation_id": str(conversation_id), "messages": [dict(r) for r in rows]}


@router.get("/{conversation_id}/export")
async def export_conversation(
    conversation_id: uuid.UUID, format: str = Query("md", pattern="^(md|json)$")
) -> Response:
    """Download a conversation as Markdown or JSON."""
    data = await get_conversation(conversation_id)
    messages = data["messages"]
    if not messages:
        raise HTTPException(status_code=404, detail="Conversation not found")
    try:
        async with get_conn() as conn:
            row = await (
                await conn.execute("SELECT language FROM conversations WHERE id = %s", (conversation_id,))
            ).fetchone()
    except Exception:
        row = None
    language = (row or {}).get("language") or "pt"
    first_user = next((m["content"] for m in messages if m["role"] == "user"), "")
    title = " ".join(first_user.split())[:_TITLE_MAX] or "BCB RAG"
    now = datetime.now(tz=timezone.utc)
    short = str(conversation_id)[:8]
    if format == "json":
        body = json.dumps(
            render_json(str(conversation_id), title, messages, now),
            ensure_ascii=False, indent=2, default=str,
        )
        media, ext = "application/json", "json"
    else:
        body = render_markdown(title, messages, now, language)
        media, ext = "text/markdown", "md"
    return Response(
        content=body,
        media_type=f"{media}; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="conversa-{short}.{ext}"'},
    )


@router.delete("/{conversation_id}")
async def delete_conversation(conversation_id: uuid.UUID) -> dict[str, bool]:
    try:
        async with get_conn() as conn:
            await conn.execute("DELETE FROM conversations WHERE id = %s", (conversation_id,))
    except Exception as exc:
        logger.error("Error deleting conversation %s: %s", conversation_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))
    return {"deleted": True}

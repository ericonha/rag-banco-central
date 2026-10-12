"""
Conversation history endpoints (persistent chat).

- GET    /api/conversations          — recent conversations (sidebar)
- GET    /api/conversations/{id}     — messages of one conversation
- DELETE /api/conversations/{id}     — remove a conversation and its messages
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from app.db.session import get_conn

logger = logging.getLogger("conversations")

router = APIRouter(prefix="/api/conversations", tags=["conversations"])

_TITLE_MAX = 80


@router.get("")
async def list_conversations(limit: int = 50) -> list[dict[str, Any]]:
    """Most recently active conversations that have at least one message."""
    limit = max(1, min(limit, 200))
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
                    ORDER BY updated_at DESC
                    LIMIT %s
                    """,
                    (limit,),
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
                    SELECT id, role, content, sources, created_at
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


@router.delete("/{conversation_id}")
async def delete_conversation(conversation_id: uuid.UUID) -> dict[str, bool]:
    try:
        async with get_conn() as conn:
            await conn.execute("DELETE FROM conversations WHERE id = %s", (conversation_id,))
    except Exception as exc:
        logger.error("Error deleting conversation %s: %s", conversation_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))
    return {"deleted": True}

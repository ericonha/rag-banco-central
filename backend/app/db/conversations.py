"""Persistence for chat conversations (tables `conversations` and `messages`)."""
from __future__ import annotations

import uuid
from typing import Any

from psycopg.types.json import Jsonb

from app.db.session import get_conn


async def save_exchange(
    conversation_id: uuid.UUID,
    language: str,
    question: str,
    answer: str,
    sources: list[dict[str, Any]] | None,
    grounding: dict[str, Any] | None = None,
    replace_message_id: int | None = None,
) -> int:
    """Store one question/answer pair, creating the conversation on first use.

    Returns the id of the assistant message (used for feedback). With `replace_message_id`
    (regenerate) the old assistant message and the question before it are removed in the same
    transaction, so the conversation keeps a single copy of the exchange.
    """
    async with get_conn() as conn:
        if replace_message_id is not None:
            await conn.execute(
                """
                DELETE FROM messages
                WHERE conversation_id = %s AND (
                    id = %s AND role = 'assistant'
                    OR id = (SELECT MAX(id) FROM messages
                             WHERE conversation_id = %s AND role = 'user' AND id < %s)
                )
                """,
                (conversation_id, replace_message_id, conversation_id, replace_message_id),
            )
        await conn.execute(
            "INSERT INTO conversations (id, language) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING",
            (conversation_id, language),
        )
        await conn.execute(
            "INSERT INTO messages (conversation_id, role, content) VALUES (%s, 'user', %s)",
            (conversation_id, question),
        )
        row = await (
            await conn.execute(
                "INSERT INTO messages (conversation_id, role, content, sources, grounding) "
                "VALUES (%s, 'assistant', %s, %s, %s) RETURNING id",
                (
                    conversation_id,
                    answer,
                    Jsonb(sources) if sources is not None else None,
                    Jsonb(grounding) if grounding is not None else None,
                ),
            )
        ).fetchone()
        await conn.commit()
    return int(row["id"])


async def get_recent_history(
    conversation_id: uuid.UUID, limit: int, regenerate_of: int | None = None
) -> list[dict[str, str]]:
    """Last `limit` messages of a conversation, oldest first, as {role, content}.

    With `regenerate_of` (an assistant message id) the exchange being regenerated and everything
    after it is left out, so the old answer does not leak into the new one.
    """
    if limit <= 0:
        return []
    async with get_conn() as conn:
        before: int | None = None
        if regenerate_of is not None:
            row = await (
                await conn.execute(
                    "SELECT MAX(id) AS id FROM messages "
                    "WHERE conversation_id = %s AND role = 'user' AND id < %s",
                    (conversation_id, regenerate_of),
                )
            ).fetchone()
            before = row["id"] if row and row["id"] is not None else regenerate_of
        rows = await (
            await conn.execute(
                """
                SELECT role, content FROM (
                    SELECT id, role, content FROM messages
                    WHERE conversation_id = %s AND (%s::bigint IS NULL OR id < %s::bigint)
                    ORDER BY id DESC LIMIT %s
                ) recent ORDER BY id
                """,
                (conversation_id, before, before, limit),
            )
        ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in rows]


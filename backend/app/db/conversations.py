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
) -> None:
    """Store one question/answer pair, creating the conversation on first use."""
    async with get_conn() as conn:
        await conn.execute(
            "INSERT INTO conversations (id, language) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING",
            (conversation_id, language),
        )
        await conn.execute(
            "INSERT INTO messages (conversation_id, role, content) VALUES (%s, 'user', %s)",
            (conversation_id, question),
        )
        await conn.execute(
            "INSERT INTO messages (conversation_id, role, content, sources) "
            "VALUES (%s, 'assistant', %s, %s)",
            (conversation_id, answer, Jsonb(sources) if sources is not None else None),
        )

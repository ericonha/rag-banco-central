"""Conversation context helpers (stdlib only, easy to unit test)."""
from __future__ import annotations

from typing import Any

# A follow-up like "e o prazo disso?" is too short to retrieve on its own.
SHORT_QUESTION_WORDS = 8


def build_messages(history: list[dict[str, Any]] | None, user_message: str) -> list[dict[str, str]]:
    """
    Messages for the Anthropic API: prior turns (plain text) followed by the new user message.

    The API needs the list to start with a user message and alternate roles, so leading
    assistant messages are dropped and consecutive same-role messages are merged.
    """
    cleaned: list[dict[str, str]] = []
    for m in history or []:
        role, content = m.get("role"), (m.get("content") or "").strip()
        if role not in ("user", "assistant") or not content:
            continue
        if not cleaned and role == "assistant":
            continue
        if cleaned and cleaned[-1]["role"] == role:
            cleaned[-1]["content"] += "\n\n" + content
        else:
            cleaned.append({"role": role, "content": content})
    if cleaned and cleaned[-1]["role"] == "user":
        # History ended on a user turn (its answer was never saved): merge into the new one.
        user_message = cleaned.pop()["content"] + "\n\n" + user_message
    return cleaned + [{"role": "user", "content": user_message}]


def retrieval_query(question: str, history: list[dict[str, Any]] | None) -> str:
    """Prepend the previous user question when the new one is a short follow-up."""
    if not history or len(question.split()) > SHORT_QUESTION_WORDS:
        return question
    for m in reversed(history):
        if m.get("role") == "user" and (m.get("content") or "").strip():
            return f"{m['content'].strip()} {question}"
    return question

"""Render a stored conversation as Markdown or JSON (stdlib only)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

_LABELS = {
    "pt": {"exported": "Exportado em", "question": "Pergunta", "answer": "Resposta", "sources": "Fontes"},
    "en": {"exported": "Exported on", "question": "Question", "answer": "Answer", "sources": "Sources"},
}


def _stamp(value: Any) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if isinstance(value, datetime) else str(value or "")


def render_markdown(
    title: str, messages: list[dict[str, Any]], exported_at: datetime, language: str = "pt"
) -> str:
    lab = _LABELS.get(language, _LABELS["pt"])
    out = [f"# {title or 'BCB RAG'}", "", f"_{lab['exported']} {_stamp(exported_at)}_", ""]
    for m in messages:
        heading = lab["question"] if m["role"] == "user" else lab["answer"]
        out += ["---", "", f"## {heading} ({_stamp(m.get('created_at'))})", "", (m.get("content") or "").strip(), ""]
        sources = m.get("sources") or []
        if m["role"] == "assistant" and sources:
            out += [f"**{lab['sources']}**", ""]
            for i, s in enumerate(sources, 1):
                label = s.get("title") or s.get("url") or "?"
                link = f"[{label}]({s['url']})" if s.get("url") else label
                meta = " — ".join(x for x in (s.get("doc_type"), str(s.get("published_at") or "")[:10]) if x)
                out.append(f"{i}. {link}" + (f" — {meta}" if meta else ""))
            out.append("")
    return "\n".join(out).rstrip() + "\n"


def render_json(
    conversation_id: str, title: str, messages: list[dict[str, Any]], exported_at: datetime
) -> dict[str, Any]:
    return {
        "conversation_id": conversation_id,
        "title": title,
        "exported_at": exported_at.isoformat(),
        "messages": [
            {
                "id": m.get("id"),
                "role": m["role"],
                "content": m.get("content"),
                "sources": m.get("sources") or [],
                "created_at": m["created_at"].isoformat() if isinstance(m.get("created_at"), datetime) else m.get("created_at"),
                "feedback": m.get("feedback"),
                "grounding": m.get("grounding"),
            }
            for m in messages
        ],
    }

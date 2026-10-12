"""Conversation export renderers (pure)."""
from datetime import datetime

from app.export import render_json, render_markdown

NOW = datetime(2026, 10, 12, 9, 30)
MSGS = [
    {"id": 1, "role": "user", "content": "O que diz a Resolução 598?", "created_at": datetime(2026, 10, 12, 9, 0)},
    {
        "id": 2, "role": "assistant", "content": "Ela trata de X [1].", "created_at": datetime(2026, 10, 12, 9, 1),
        "sources": [{"title": "Resolução BCB N° 598", "url": "https://x.test/598", "doc_type": "Resolução BCB",
                     "published_at": "2026-10-07T00:00:00"}],
        "feedback": 1, "grounding": {"ok": True},
    },
]


def test_markdown_has_title_turns_and_sources() -> None:
    md = render_markdown("Resolução 598", MSGS, NOW, "pt")
    assert md.startswith("# Resolução 598")
    assert "## Pergunta" in md and "## Resposta" in md
    assert "[Resolução BCB N° 598](https://x.test/598)" in md
    assert "2026-10-07" in md
    assert md.endswith("\n")


def test_markdown_english_labels() -> None:
    md = render_markdown("T", MSGS, NOW, "en")
    assert "## Question" in md and "**Sources**" in md


def test_markdown_survives_missing_sources() -> None:
    md = render_markdown("T", [{"role": "assistant", "content": "ok", "created_at": None}], NOW)
    assert "ok" in md


def test_json_shape() -> None:
    data = render_json("abc", "T", MSGS, NOW)
    assert data["conversation_id"] == "abc"
    assert data["exported_at"] == NOW.isoformat()
    assert data["messages"][1]["feedback"] == 1
    assert data["messages"][0]["sources"] == []
    assert data["messages"][0]["created_at"] == "2026-10-12T09:00:00"

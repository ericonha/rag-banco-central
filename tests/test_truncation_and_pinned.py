"""Cut-off answers are flagged, and a named document contributes more than k chunks."""
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.rag import answering
from app.rag.retrieval import retrieve_chunks

CHUNKS = [{
    "title": "Resolução BCB N° 525", "url": "https://example.test/525",
    "published_at": datetime(2025, 11, 28), "doc_type": "Resolução BCB", "text": "Texto.",
}]


def _client(captured: dict, stop_reason: str | None):
    class FakeClient:
        def __init__(self, api_key: str = "") -> None:
            self.messages = SimpleNamespace(create=self._create)

        def _create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                content=[SimpleNamespace(text="resposta incompleta")],
                usage=SimpleNamespace(input_tokens=1, output_tokens=2),
                stop_reason=stop_reason,
            )

    return FakeClient


def test_truncated_answer_gets_a_visible_notice(monkeypatch) -> None:
    captured: dict = {}
    monkeypatch.setattr(answering, "Anthropic", _client(captured, "max_tokens"))
    text, _, _ = answering.answer_question_with_usage("q", CHUNKS, "pt", "k", "m", max_tokens=300)
    assert text.startswith("resposta incompleta")
    assert "cortada" in text
    assert captured["max_tokens"] == 300


def test_complete_answer_is_untouched(monkeypatch) -> None:
    monkeypatch.setattr(answering, "Anthropic", _client({}, "end_turn"))
    text, _, _ = answering.answer_question_with_usage("q", CHUNKS, "en", "k", "m")
    assert text == "resposta incompleta"


def test_default_limit_is_larger_than_the_old_one() -> None:
    assert answering.DEFAULT_MAX_TOKENS > 1024


def test_prompt_forbids_claiming_the_regulation_ends_with_the_excerpt() -> None:
    assert "nunca afirme que a norma termina ali" in answering.SYSTEM_PROMPT_PT
    assert "never state that the regulation ends there" in answering.SYSTEM_PROMPT_EN


# ---- retrieval: pinned document expands beyond k -------------------------------------------

def _row(i: int, kind: str) -> dict:
    return {"id": i, "text": f"t{i}", "document_id": 525 if kind == "exact" else 1, "title": kind,
            "url": "u", "published_at": datetime(2025, 11, 28), "doc_type": "Resolução BCB",
            "distance": 0.0 if kind == "exact" else 0.3}


class FakeConn:
    """Answers the two queries retrieve_chunks issues, told apart by their SQL."""

    def __init__(self, n_exact: int) -> None:
        self.n_exact = n_exact

    async def execute(self, sql, params=None):
        if "regexp_replace" in sql:
            rows = [{**_row(100 + i, "exact"), "pinned": True} for i in range(self.n_exact)]
            rows = [{k: v for k, v in r.items() if k != "pinned"} for r in rows]
        else:
            rows = [_row(i, "semantic") for i in range(5)]
        return SimpleNamespace(fetchall=self._all(rows))

    @staticmethod
    def _all(rows):
        async def fetchall():
            return rows
        return fetchall


async def _retrieve(n_exact: int, **kw):
    return await retrieve_chunks(
        FakeConn(n_exact), "resumo da Resolução BCB nº 525", "m", 768, k=5, **kw
    )


@pytest.mark.asyncio
async def test_without_pinned_limit_the_strict_top_k_holds() -> None:
    out = await _retrieve(20)
    assert len(out) == 5


@pytest.mark.asyncio
async def test_named_document_expands_up_to_the_pinned_limit_in_order() -> None:
    out = await _retrieve(20, pinned_limit=12)
    assert len(out) == 12
    assert all(c["title"] == "exact" for c in out)
    assert [c["id"] for c in out] == list(range(100, 112))  # reading order kept


@pytest.mark.asyncio
async def test_short_document_does_not_pad_with_unrelated_chunks_beyond_k() -> None:
    out = await _retrieve(3, pinned_limit=12)
    assert len(out) == 5
    assert [c["title"] for c in out[:3]] == ["exact"] * 3

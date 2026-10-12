"""answer_question_with_usage: history reaches the API call and usage is returned."""
from datetime import datetime
from types import SimpleNamespace

from app.rag import answering

CHUNKS = [
    {
        "title": "Resolução BCB N° 598",
        "url": "https://example.test/598",
        "published_at": datetime(2026, 10, 7),
        "doc_type": "Resolução BCB",
        "text": "Texto da resolução.",
    }
]


def _fake_anthropic(captured: dict, usage):
    class FakeClient:
        def __init__(self, api_key: str = "") -> None:
            self.messages = SimpleNamespace(create=self._create)

        def _create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(content=[SimpleNamespace(text="resposta [1]")], usage=usage)

    return FakeClient


def test_history_is_sent_and_usage_returned(monkeypatch) -> None:
    captured: dict = {}
    usage = SimpleNamespace(input_tokens=120, output_tokens=30)
    monkeypatch.setattr(answering, "Anthropic", _fake_anthropic(captured, usage))
    history = [
        {"role": "user", "content": "O que diz a Resolução 598?"},
        {"role": "assistant", "content": "Ela trata de X."},
    ]

    text, sources, used = answering.answer_question_with_usage(
        "e o prazo?", CHUNKS, "pt", "key", "model-x", history=history
    )

    assert text == "resposta [1]"
    assert len(sources) == 1
    assert used == {"tokens_in": 120, "tokens_out": 30}
    roles = [m["role"] for m in captured["messages"]]
    assert roles == ["user", "assistant", "user"]
    assert "Pergunta: e o prazo?" in captured["messages"][-1]["content"]
    assert "Resolução BCB N° 598" in captured["messages"][-1]["content"]


def test_missing_usage_gives_none(monkeypatch) -> None:
    monkeypatch.setattr(answering, "Anthropic", _fake_anthropic({}, None))
    _, _, used = answering.answer_question_with_usage("q", CHUNKS, "pt", "key", "m")
    assert used == {"tokens_in": None, "tokens_out": None}


def test_no_chunks_skips_the_api(monkeypatch) -> None:
    def boom(*a, **k):
        raise AssertionError("API must not be called")

    monkeypatch.setattr(answering, "Anthropic", boom)
    text, sources, used = answering.answer_question_with_usage("q", [], "en", "key", "m")
    assert sources == [] and "No relevant" in text
    assert used["tokens_in"] is None


def test_legacy_wrapper_still_returns_two_values(monkeypatch) -> None:
    monkeypatch.setattr(answering, "Anthropic", _fake_anthropic({}, None))
    result = answering.answer_question("q", CHUNKS, "pt", "key", "m")
    assert len(result) == 2

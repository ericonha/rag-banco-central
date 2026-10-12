"""stream_answer with a fake async Anthropic client (no network)."""
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.rag import answering

CHUNKS = [{
    "title": "Resolução BCB N° 598", "url": "https://example.test/598",
    "published_at": datetime(2026, 10, 7), "doc_type": "Resolução BCB", "text": "Texto.",
}]


def _fake(captured: dict, pieces: list[str], usage):
    class Stream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        @property
        def text_stream(self):
            async def gen():
                for p in pieces:
                    yield p
            return gen()

        async def get_final_message(self):
            return SimpleNamespace(usage=usage)

    class FakeClient:
        def __init__(self, api_key: str = "") -> None:
            self.messages = SimpleNamespace(stream=self._stream)

        def _stream(self, **kwargs):
            captured.update(kwargs)
            return Stream()

    return FakeClient


@pytest.mark.asyncio
async def test_yields_deltas_then_usage(monkeypatch) -> None:
    captured: dict = {}
    usage = SimpleNamespace(input_tokens=100, output_tokens=7)
    monkeypatch.setattr(answering, "AsyncAnthropic", _fake(captured, ["Ela ", "trata ", "de X [1]."], usage))

    events = [e async for e in answering.stream_answer("e a 598?", CHUNKS, "pt", "key", "model-x", history=[])]

    assert [e["text"] for e in events if e["type"] == "delta"] == ["Ela ", "trata ", "de X [1]."]
    assert events[-1] == {"type": "usage", "tokens_in": 100, "tokens_out": 7}
    assert captured["model"] == "model-x"
    assert captured["temperature"] == 0
    assert captured["messages"][-1]["role"] == "user"


@pytest.mark.asyncio
async def test_missing_usage_gives_none(monkeypatch) -> None:
    monkeypatch.setattr(answering, "AsyncAnthropic", _fake({}, ["ok"], None))
    events = [e async for e in answering.stream_answer("q", CHUNKS, "en", "key", "m")]
    assert events[-1] == {"type": "usage", "tokens_in": None, "tokens_out": None}

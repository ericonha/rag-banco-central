"""
Unit tests for the BCB normativos scraper parser.

These tests run fully offline against saved JSON fixtures.
No network or database connection is needed.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.scraping.bcb_normativos import BCBNormativosSource, _html_to_text, _make_hash
from app.scraping.base import DocRef

FIXTURE_DIR = Path(__file__).parent / "fixtures"

SOURCE = BCBNormativosSource(
    source_name="bcb_comunicados_ccs",
    querytext="CCS",
    tipo_documento="Comunicado",
)


# ---------------------------------------------------------------------------
# Pure-function tests (no I/O)
# ---------------------------------------------------------------------------


def test_html_to_text_strips_tags() -> None:
    html = "<div><p>Hello <b>world</b></p></div>"
    assert _html_to_text(html) == "Hello world"


def test_html_to_text_collapses_whitespace() -> None:
    html = "<p>Line one\n\n  Line two</p>"
    result = _html_to_text(html)
    assert "\n" not in result
    assert "Line one" in result
    assert "Line two" in result


def test_make_hash_is_deterministic() -> None:
    assert _make_hash("abc") == _make_hash("abc")


def test_make_hash_differs() -> None:
    assert _make_hash("abc") != _make_hash("def")


# ---------------------------------------------------------------------------
# fetch() — mocked HTTP, real parsing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_parses_fixture() -> None:
    fixture = json.loads((FIXTURE_DIR / "bcb_comunicado_37667.json").read_text())

    ref = DocRef(
        source="bcb_comunicados_ccs",
        url=(
            "https://www.bcb.gov.br/estabilidadefinanceira/exibenormativo"
            "?tipo=Comunicado&numero=37667"
        ),
        doc_type="Comunicado",
        numero=37667,
        published_at=datetime(2021, 9, 14, 21, 36, 55, tzinfo=timezone.utc),
        title="Comunicado N° 37.667",
    )

    with patch("app.scraping.bcb_normativos.get_json", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = fixture
        doc = await SOURCE.fetch(ref)

    assert doc.title == "Comunicado N° 37.667"
    assert doc.doc_type == "Comunicado"
    assert doc.language == "pt"
    assert "Banco Central do Brasil" in doc.raw_text
    assert "<" not in doc.raw_text, "HTML tags must be stripped"
    assert len(doc.content_hash) == 64  # sha256 hex
    assert doc.published_at == datetime(2021, 9, 14, 21, 36, 55, tzinfo=timezone.utc)

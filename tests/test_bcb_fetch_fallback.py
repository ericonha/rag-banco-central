"""fetch() falls back to other BCB endpoints when the first returns an empty conteudo."""
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.scraping.base import DocRef
from app.scraping.bcb_normativos import BCBNormativosSource

FIXTURE = Path(__file__).parent / "fixtures" / "bcb_comunicado_37667.json"
SOURCE = BCBNormativosSource(
    source_name="bcb_resolucoes", querytext="*", tipo_documento="Resolução BCB"
)
REF = DocRef(
    source="bcb_resolucoes",
    url="https://www.bcb.gov.br/estabilidadefinanceira/exibenormativo?tipo=Resolução BCB&numero=598",
    doc_type="Resolução BCB",
    numero=598,
    published_at=datetime(2026, 10, 7, tzinfo=timezone.utc),
    title="Resolução BCB N° 598",
)


@pytest.mark.asyncio
async def test_falls_back_to_second_endpoint() -> None:
    fixture = json.loads(FIXTURE.read_text())
    with patch("app.scraping.bcb_normativos.get_json", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = [{"conteudo": []}, fixture]
        doc = await SOURCE.fetch(REF)
    assert mock_get.await_count == 2
    assert "Banco Central do Brasil" in doc.raw_text


@pytest.mark.asyncio
async def test_error_lists_what_was_tried() -> None:
    with patch("app.scraping.bcb_normativos.get_json", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {"conteudo": []}
        with pytest.raises(ValueError) as exc:
            await SOURCE.fetch(REF)
    assert "tried" in str(exc.value)
    assert mock_get.await_count == 4

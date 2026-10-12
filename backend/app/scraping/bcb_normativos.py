"""
BCB normativos scraper.

Uses two pure-JSON endpoints (no HTML parsing needed for the listing):

  LIST  GET /api/search/app/normativos/buscanormativos
           ?querytext=<keyword>
           &rowlimit=50
           &startrow=<N>
           &sortlist=Data1OWSDATE:descending
           &refinementfilters=Data:range(datetime(<from>),datetime(<to>))
           (compound 'AND' refinements return HTTP 500, so the doc type is
            filtered client-side on TipodoNormativoOWSCHCS)

  DETAIL GET /api/conteudo/app/normativos/exibeoutrasnormas
            ?p1=<TIPO_UPPERCASE>
            &p2=<numero>

The ``Source`` class is parameterised so that a single class covers every
combination of (querytext, tipo_documento) that the BCB search page accepts.
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Any

from bs4 import BeautifulSoup

from app.scraping.base import DocRef, Document
from app.scraping.http import bcb_client, get_json

logger = logging.getLogger(__name__)

_BCB_BASE = "https://www.bcb.gov.br"
_SEARCH_URL = f"{_BCB_BASE}/api/search/app/normativos/buscanormativos"
_DETAIL_URL = f"{_BCB_BASE}/api/conteudo/app/normativos/exibeoutrasnormas"
_DETAIL_URL_NORMATIVO = f"{_BCB_BASE}/api/conteudo/app/normativos/exibenormativo"
_PAGE_URL_TPL = (
    "{base}/estabilidadefinanceira/exibenormativo?tipo={tipo}&numero={numero}"
)

_ROW_LIMIT = 50  # max rows per page supported by the BCB API


def _html_to_text(html: str) -> str:
    """Strip HTML tags, collapse whitespace."""
    soup = BeautifulSoup(html, "html.parser")
    return re.sub(r"\s+", " ", soup.get_text(separator=" ")).strip()


def _make_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _parse_iso(dt_str: str) -> datetime:
    """Parse the ISO-8601 timestamps returned by the BCB API."""
    return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))


def _norm(s: str | None) -> str:
    return (s or "").strip().casefold()


class BCBNormativosSource:
    """
    Parameterisable source for BCB regulatory documents.

    Parameters
    ----------
    source_name:
        Logical identifier stored in ``documents.source``
        (e.g. "bcb_comunicados_ccs").
    querytext:
        The ``querytext`` forwarded to the BCB search API
        (e.g. "CCS", or "*" for all documents of a given type).
    tipo_documento:
        Document type exactly as it appears in the BCB API
        (e.g. "Comunicado", "Resolução BCB", "Carta Circular").
        Used for the client-side type filter and in the detail URL.
    """

    def __init__(
        self,
        *,
        source_name: str,
        querytext: str,
        tipo_documento: str,
    ) -> None:
        self.source_name = source_name
        self.querytext = querytext
        self.tipo_documento = tipo_documento

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def list_new(self, since: datetime) -> list[DocRef]:
        """
        Return all documents of this type published on or after *since*.

        Paginates through the BCB API automatically.
        """
        since_utc = since.astimezone(timezone.utc)
        from_str = since_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        refs: list[DocRef] = []

        async with bcb_client() as client:
            start_row = 0
            while True:
                data: Any = await get_json(
                    client,
                    _SEARCH_URL,
                    querytext=self.querytext,
                    rowlimit=_ROW_LIMIT,
                    startrow=start_row,
                    sortlist="Data1OWSDATE:descending",
                    refinementfilters=f"Data:range(datetime({from_str}),datetime(max))",
                )

                rows: list[dict[str, Any]] = data.get("Rows", [])
                if not rows:
                    break

                for row in rows:
                    if _norm(row.get("TipodoNormativoOWSCHCS")) != _norm(self.tipo_documento):
                        continue
                    try:
                        numero = int(float(row["NumeroOWSNMBR"]))
                        refs.append(
                            DocRef(
                                source=self.source_name,
                                url=_PAGE_URL_TPL.format(
                                    base=_BCB_BASE,
                                    tipo=row["TipodoNormativoOWSCHCS"],
                                    numero=numero,
                                ),
                                doc_type=row["TipodoNormativoOWSCHCS"],
                                numero=numero,
                                published_at=_parse_iso(row["data"]),
                                title=row["title"],
                            )
                        )
                    except (KeyError, ValueError) as exc:
                        logger.warning("Skipping malformed row: %s (%s)", row, exc)

                total: int = data.get("TotalRows", 0)
                start_row += len(rows)
                if start_row >= total:
                    break

        logger.info(
            "list_new(%s, since=%s): found %d refs",
            self.source_name,
            since,
            len(refs),
        )
        return refs

    async def fetch(self, ref: DocRef) -> Document:
        """Download and return the full text of one document.

        Comunicados come from ``exibeoutrasnormas``. Resoluções/Circulares return an
        empty ``conteudo`` there, so we fall back to ``exibenormativo`` and to other
        spellings of the type. The first non-empty answer wins.
        """
        candidates = [
            (_DETAIL_URL, ref.doc_type.upper()),
            (_DETAIL_URL_NORMATIVO, ref.doc_type),
            (_DETAIL_URL_NORMATIVO, ref.doc_type.upper()),
            (_DETAIL_URL, ref.doc_type),
        ]
        item: dict[str, Any] | None = None
        tried: list[str] = []
        async with bcb_client() as client:
            for url, p1 in candidates:
                try:
                    data: Any = await get_json(client, url, p1=p1, p2=ref.numero)
                except Exception as exc:  # noqa: BLE001 - try the next candidate
                    tried.append(f"{url.rsplit('/', 1)[-1]}[{p1}]: {type(exc).__name__}")
                    continue
                items = data.get("conteudo", []) if isinstance(data, dict) else []
                if items:
                    item = items[0]
                    break
                keys = sorted(data) if isinstance(data, dict) else type(data).__name__
                tried.append(f"{url.rsplit('/', 1)[-1]}[{p1}]: empty (keys={keys})")

        if item is None:
            logger.warning("Empty conteudo for %s (tried %s)", ref.url, "; ".join(tried))
            raise ValueError(f"Empty conteudo for {ref.url} (tried: {'; '.join(tried)})")

        def field(*names: str) -> str:
            for n in names:
                v = item.get(n)
                if v:
                    return v
            return ""

        # Combine assunto (subject) and texto (body) into a single plain text blob.
        full_html = f"{field('Assunto', 'assunto')}\n{field('Texto', 'texto')}"
        raw_text = _html_to_text(full_html)
        if not raw_text.strip():
            raise ValueError(f"No text in conteudo for {ref.url} (fields: {sorted(item)})")

        data_str = field("Data", "data")
        return Document(
            source=ref.source,
            url=ref.url,
            title=field("Titulo", "titulo") or ref.title,
            doc_type=field("Tipo", "tipo") or ref.doc_type,
            published_at=_parse_iso(data_str) if data_str else ref.published_at,
            language="pt",
            raw_text=raw_text,
            content_hash=_make_hash(raw_text),
        )

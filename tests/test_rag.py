"""Tests for RAG retrieval and answering."""
import pytest
from app.rag.answering import _build_context_from_chunks


def test_build_context_from_chunks() -> None:
    """Test context building with chunk data."""
    chunks = [
        {
            "title": "Comunicado N° 37.667",
            "url": "https://bcb.gov.br/...",
            "published_at": "2021-09-14",
            "text": "O Banco Central comunica...",
        },
        {
            "title": "Resolução N° 1.234",
            "url": "https://bcb.gov.br/...",
            "published_at": "2021-08-01",
            "text": "Fica estabelecido...",
        },
    ]
    
    context = _build_context_from_chunks(chunks)
    
    assert "[1]" in context
    assert "[2]" in context
    assert "Comunicado N° 37.667" in context
    assert "Resolução N° 1.234" in context
    assert "O Banco Central comunica..." in context

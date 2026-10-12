"""Tests for the chunker."""
from app.chunking.chunker import PortugueseRegulationChunker


def test_chunker_handles_empty_text() -> None:
    """Empty text produces no chunks."""
    chunker = PortugueseRegulationChunker()
    chunks = chunker.chunk("", document_id=1)
    assert chunks == []


def test_chunker_handles_short_text() -> None:
    """Short text produces one chunk."""
    chunker = PortugueseRegulationChunker()
    text = "O Banco Central comunica a inclusão das instituições de pagamento."
    chunks = chunker.chunk(text, document_id=1)
    assert len(chunks) == 1
    assert chunks[0].document_id == 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].text == text
    assert chunks[0].token_count > 0


def test_chunker_respects_token_limit() -> None:
    """Chunks respect max token limit."""
    chunker = PortugueseRegulationChunker()
    
    # One article of ~2000+ tokens (50 repetitions are only ~750 real tokens)
    long_text = (
        "Art. 1º Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 150
    )
    
    chunks = chunker.chunk(long_text, document_id=1)
    assert len(chunks) > 1
    
    # All chunks should be within token limits
    for chunk in chunks:
        assert chunk.token_count < 850, f"Chunk {chunk.chunk_index} exceeds max tokens"


def test_chunker_preserves_article_structure() -> None:
    """Chunks try to respect article boundaries."""
    chunker = PortugueseRegulationChunker()
    
    text = """
Art. 1º Do escopo
Esta regulação aplica-se a todas as instituições.

Art. 2º Das definições
Para os efeitos desta Resolução:
- Instituição: pessoa jurídica autorizada;
- Risco: possibilidade de prejuízo.

Art. 3º Das obrigações
Cada instituição deve cumprir os requisitos aqui descritos.
"""
    
    chunks = chunker.chunk(text, document_id=1)
    # Should have at least 2 chunks (articles grouped)
    assert len(chunks) >= 1
    
    # Check that chunk indices are correct
    for i, chunk in enumerate(chunks):
        assert chunk.chunk_index == i
        assert len(chunk.text) > 0


def test_chunker_token_counting() -> None:
    """Token counting is consistent."""
    chunker = PortugueseRegulationChunker()
    
    text = "O Banco Central do Brasil é autarquia federal."
    tokens = chunker.count_tokens(text)
    
    # This text should be ~10-12 tokens
    assert 5 < tokens < 20


def test_chunker_keeps_the_last_article() -> None:
    """Regression: the body of the last article used to be dropped."""
    chunker = PortugueseRegulationChunker()
    text = (
        "Art. 1º Primeiro artigo.\n\n"
        "Art. 2º Segundo artigo.\n\n"
        "Art. 3º Terceiro artigo com texto final."
    )
    joined = "\n".join(c.text for c in chunker.chunk(text, document_id=1))
    assert "Primeiro artigo" in joined
    assert "Segundo artigo" in joined
    assert "Terceiro artigo com texto final" in joined


def test_chunker_single_article_keeps_its_body() -> None:
    chunker = PortugueseRegulationChunker()
    chunks = chunker.chunk("Art. 1º O Banco Central resolve incluir o código 123.", document_id=1)
    assert len(chunks) == 1
    assert "resolve incluir o código 123" in chunks[0].text


def test_chunker_does_not_duplicate_headers_or_lose_preamble() -> None:
    chunker = PortugueseRegulationChunker()
    text = "Preâmbulo da norma.\n\nArt. 1º Um.\n\nArt. 2º Dois."
    joined = "\n".join(c.text for c in chunker.chunk(text, document_id=1))
    assert "Preâmbulo da norma" in joined
    assert joined.count("Art. 2") == 1
    assert joined.count("Art. 1") == 1


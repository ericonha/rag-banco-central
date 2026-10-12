"""Document-number extraction used by the hybrid retrieval step."""
from app.rag.retrieval import _document_numbers


def test_dotted_number() -> None:
    assert _document_numbers("O que diz o Comunicado nº 34.977?") == ["34977"]


def test_plain_long_number() -> None:
    assert _document_numbers("comunicado 34977") == ["34977"]


def test_short_number_needs_keyword() -> None:
    assert _document_numbers("O que diz a Resolução BCB nº 598?") == ["598"]
    assert _document_numbers("resolução 598") == ["598"]
    assert _document_numbers("Resolução BCB N° 598") == ["598"]
    assert _document_numbers("circular 3.978") == ["3978"]


def test_english_keywords() -> None:
    assert _document_numbers("What does Resolution 598 say?") == ["598"]
    assert _document_numbers("Resolution No. 589 says?") == ["589"]


def test_plain_small_numbers_are_ignored() -> None:
    assert _document_numbers("Quais as regras para 5 bancos?") == []
    assert _document_numbers("o que é o CCS?") == []


def test_deduplicates_and_keeps_order() -> None:
    assert _document_numbers("Resolução 598 e resolução 599, de novo a 598") == ["598", "599"]

"""Heuristic faithfulness check (no LLM, no database)."""
from app.rag.faithfulness import check_answer

CHUNKS = [
    "O prazo para envio das informações ao CCS é de 30 dias corridos contados da publicação.",
    "A multa diária prevista é de R$ 500,00 para instituições que descumprirem a norma.",
]


def _types(result: dict) -> set[str]:
    return {f["type"] for f in result["flags"]}


def test_supported_answer_is_ok() -> None:
    result = check_answer("O prazo para envio das informações ao CCS é de 30 dias corridos [1].", CHUNKS)
    assert result["ok"] is True
    assert result["score"] == 1.0
    assert result["flags"] == []


def test_invalid_citation_is_flagged() -> None:
    result = check_answer("O prazo para envio das informações ao CCS é de 30 dias [5].", CHUNKS)
    assert result["ok"] is False
    assert "invalid_citation" in _types(result)


def test_number_missing_from_cited_chunk_is_flagged() -> None:
    result = check_answer("O prazo para envio das informações ao CCS é de 45 dias corridos [1].", CHUNKS)
    assert "unsupported_number" in _types(result)


def test_number_is_checked_against_the_cited_chunk_only() -> None:
    # R$ 500,00 exists, but in chunk 2 — citing chunk 1 for it is wrong.
    result = check_answer("A multa diária prevista é de R$ 500,00 para instituições [1].", CHUNKS)
    assert result["ok"] is False


def test_answer_without_citations_scores_zero() -> None:
    result = check_answer("O prazo é de trinta dias corridos para todas as instituições.", CHUNKS)
    assert result["score"] == 0.0
    assert _types(result) == {"no_citations"}


def test_refusal_is_not_penalised() -> None:
    result = check_answer("Não tenho informações sobre isso nos documentos disponíveis.", CHUNKS)
    assert result["ok"] is True
    assert result["checked"] == 0


def test_empty_answer_is_ok() -> None:
    assert check_answer("", CHUNKS)["ok"] is True


def test_flags_are_capped() -> None:
    answer = " ".join(f"Afirmação inventada número {i} sobre assunto totalmente diferente [9]." for i in range(20))
    assert len(check_answer(answer, CHUNKS)["flags"]) <= 6

"""Retrieval-evaluation metrics and the dataset file."""
import json
from pathlib import Path

import app.evaluation
from app.evaluation.metrics import first_hit_rank, group_summary, summarize, title_matches

DATASET = Path(app.evaluation.__file__).parent / "dataset.json"


def test_title_matches_whole_numbers_only() -> None:
    assert title_matches("Resolução BCB N° 598", "598")
    assert title_matches("Comunicado nº 34.977", "34.977")
    assert not title_matches("Resolução BCB N° 5980", "598")
    assert not title_matches("Resolução BCB N° 1598", "598")
    assert not title_matches(None, "598")


def test_title_matches_ignores_thousands_separator() -> None:
    assert title_matches("Comunicado nº 34977", "34.977")
    assert title_matches("Comunicado nº 34.977", "34977")
    assert not title_matches("Comunicado nº 134.977", "34.977")


def test_first_hit_rank_counts_distinct_documents() -> None:
    titles = ["Res 1", "Res 1", "Res 1", "Res N° 598"]
    assert first_hit_rank(titles, ["598"]) == 2


def test_first_hit_rank_miss() -> None:
    assert first_hit_rank(["Res 1", "Res 2"], ["598"]) is None
    assert first_hit_rank([], ["598"]) is None


def test_summarize() -> None:
    s = summarize([1, 2, None, None])
    assert s == {"n": 4, "hit_rate": 0.5, "mrr": 0.375}
    assert summarize([]) == {"n": 0, "hit_rate": 0.0, "mrr": 0.0}


def test_group_summary() -> None:
    rows = [
        {"type": "identifier", "rank": 1},
        {"type": "identifier", "rank": None},
        {"type": "semantic", "rank": 2},
    ]
    g = group_summary(rows, "type")
    assert g["identifier"]["hit_rate"] == 0.5
    assert g["semantic"]["mrr"] == 0.5


def test_dataset_is_well_formed() -> None:
    questions = json.loads(DATASET.read_text(encoding="utf-8"))["questions"]
    assert len(questions) >= 10
    ids = [q["id"] for q in questions]
    assert len(ids) == len(set(ids)), "duplicate question ids"
    for q in questions:
        assert q["question"].strip()
        assert q["type"] in ("identifier", "semantic")
        assert q["language"] in ("pt", "en")
        assert q["expected_titles"] and all(q["expected_titles"])

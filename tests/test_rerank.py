"""Pure part of the reranker: ordering by (index, score) pairs."""
from app.rag.rerank import apply_scores

CANDS = [{"id": 1}, {"id": 2}, {"id": 3}]


def test_orders_by_score_descending_and_keeps_scores() -> None:
    out = apply_scores(CANDS, [(0, 0.1), (1, 0.9), (2, 0.5)])
    assert [c["id"] for c in out] == [2, 3, 1]
    assert out[0]["rerank_score"] == 0.9


def test_unscored_candidates_go_last_without_score() -> None:
    out = apply_scores(CANDS, [(2, 0.4)])
    assert out[0]["id"] == 3
    assert "rerank_score" not in out[1]
    assert [c["id"] for c in out[1:]] == [1, 2]  # stable


def test_out_of_range_indexes_are_ignored() -> None:
    out = apply_scores(CANDS, [(7, 1.0), (-1, 1.0), (1, 0.2)])
    assert out[0]["id"] == 2


def test_input_is_not_mutated() -> None:
    apply_scores(CANDS, [(0, 1.0)])
    assert "rerank_score" not in CANDS[0]

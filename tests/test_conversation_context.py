"""Conversation context, retrieval-query expansion and cost maths (no database needed)."""
from app.rag.context import build_messages, retrieval_query
from app.rag.pricing import compute_cost


def test_no_history_is_just_the_user_message() -> None:
    assert build_messages(None, "oi") == [{"role": "user", "content": "oi"}]
    assert build_messages([], "oi") == [{"role": "user", "content": "oi"}]


def test_history_comes_first_and_alternates() -> None:
    history = [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
    ]
    msgs = build_messages(history, "q2")
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert msgs[-1]["content"] == "q2"


def test_leading_assistant_message_is_dropped() -> None:
    history = [
        {"role": "assistant", "content": "orphan"},
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
    ]
    msgs = build_messages(history, "q2")
    assert msgs[0] == {"role": "user", "content": "q1"}


def test_consecutive_same_role_messages_are_merged() -> None:
    history = [
        {"role": "user", "content": "q1"},
        {"role": "user", "content": "q1b"},
        {"role": "assistant", "content": "a1"},
    ]
    msgs = build_messages(history, "q2")
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert "q1" in msgs[0]["content"] and "q1b" in msgs[0]["content"]


def test_history_ending_on_user_turn_is_merged_into_new_message() -> None:
    msgs = build_messages([{"role": "user", "content": "unanswered"}], "q2")
    assert len(msgs) == 1
    assert "unanswered" in msgs[0]["content"] and "q2" in msgs[0]["content"]


def test_blank_and_unknown_messages_are_ignored() -> None:
    history = [
        {"role": "user", "content": "  "},
        {"role": "system", "content": "x"},
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
    ]
    assert [m["content"] for m in build_messages(history, "q2")] == ["q1", "a1", "q2"]


def test_short_followup_is_expanded_with_previous_question() -> None:
    history = [
        {"role": "user", "content": "O que diz a Resolução BCB nº 598?"},
        {"role": "assistant", "content": "..."},
    ]
    assert retrieval_query("e o prazo?", history) == "O que diz a Resolução BCB nº 598? e o prazo?"


def test_long_question_or_empty_history_is_unchanged() -> None:
    history = [{"role": "user", "content": "anterior"}]
    long_q = "quais são todos os requisitos de capital mínimo exigidos das instituições financeiras"
    assert retrieval_query(long_q, history) == long_q
    assert retrieval_query("e o prazo?", []) == "e o prazo?"
    assert retrieval_query("e o prazo?", None) == "e o prazo?"


def test_compute_cost() -> None:
    assert compute_cost(1_000_000, 1_000_000, 1.0, 5.0) == 6.0
    assert compute_cost(2_000, 500, 1.0, 5.0) == 0.0045


def test_cost_is_none_when_unknown() -> None:
    assert compute_cost(None, 10, 1.0, 5.0) is None
    assert compute_cost(10, None, 1.0, 5.0) is None
    assert compute_cost(10, 10, 0.0, 0.0) is None

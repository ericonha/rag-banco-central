"""
Cross-encoder reranking with PostgresML (``pgml.rank``).

Retrieval fetches more candidates than needed (hybrid: exact-number matches + semantic top-N),
then a cross-encoder reads (question, passage) pairs together and reorders them. Chunks pinned
by an exact document-number match stay first. Any failure falls back to the original order,
so a missing model or a timeout never breaks an answer.
"""
from __future__ import annotations

import logging
from typing import Any

import psycopg

logger = logging.getLogger(__name__)

MAX_PASSAGE_CHARS = 1500


def apply_scores(
    candidates: list[dict[str, Any]], scored: list[tuple[int, float]]
) -> list[dict[str, Any]]:
    """Order `candidates` by the (index, score) pairs from the reranker; unscored ones go last."""
    by_index: dict[int, float] = {}
    for idx, score in scored:
        if 0 <= idx < len(candidates):
            by_index[idx] = float(score)
    order = sorted(range(len(candidates)), key=lambda i: by_index.get(i, float("-inf")), reverse=True)
    result = []
    for i in order:
        chunk = dict(candidates[i])
        if i in by_index:
            chunk["rerank_score"] = round(by_index[i], 4)
        result.append(chunk)
    return result


async def rerank_chunks(
    conn: psycopg.AsyncConnection,
    question: str,
    chunks: list[dict[str, Any]],
    model: str,
    top_n: int,
) -> list[dict[str, Any]]:
    """Return the best `top_n` chunks after reranking (pinned chunks first)."""
    pinned = [c for c in chunks if c.get("pinned")]
    rest = [c for c in chunks if not c.get("pinned")]
    if len(rest) <= 1 or not model:
        return (pinned + rest)[:top_n]

    passages = [c["text"][:MAX_PASSAGE_CHARS] for c in rest]
    try:
        rows = await (
            await conn.execute(
                "SELECT corpus_id, score FROM pgml.rank(%s, %s, %s::text[])",
                (model, question, passages),
            )
        ).fetchall()
        scored = [(int(r["corpus_id"]), float(r["score"])) for r in rows]
    except Exception as exc:  # noqa: BLE001 - reranking is best effort
        logger.warning("Reranking with %s failed, keeping retrieval order: %s", model, exc)
        try:
            await conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        return (pinned + rest)[:top_n]

    if not scored:
        return (pinned + rest)[:top_n]
    return (pinned + apply_scores(rest, scored))[:top_n]

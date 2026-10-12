"""Retrieval metrics (stdlib only)."""
from __future__ import annotations

import re
from typing import Any


def _strip_thousands(text: str) -> str:
    """"34.977" -> "34977" (BCB titles are inconsistent about the thousands separator)."""
    return re.sub(r"(?<=\d)\.(?=\d{3}\b)", "", text)


def title_matches(title: str | None, expected: str) -> bool:
    """True if `expected` (e.g. "598", "34.977") appears in the title as a whole number."""
    title_n, expected_n = _strip_thousands(title or ""), _strip_thousands(expected)
    return bool(re.search(rf"(?<!\d){re.escape(expected_n)}(?!\d)", title_n, re.IGNORECASE))


def first_hit_rank(titles: list[str], expected: list[str]) -> int | None:
    """1-based rank of the first distinct document matching any expected string, else None.

    `titles` holds one title per retrieved chunk; repeated titles count once so that
    several chunks of one document do not push other documents down.
    """
    seen: list[str] = []
    for t in titles:
        if t not in seen:
            seen.append(t)
    for rank, t in enumerate(seen, 1):
        if any(title_matches(t, e) for e in expected):
            return rank
    return None


def summarize(ranks: list[int | None]) -> dict[str, float]:
    """Hit rate and mean reciprocal rank over a list of per-question ranks."""
    n = len(ranks)
    if n == 0:
        return {"n": 0, "hit_rate": 0.0, "mrr": 0.0}
    hits = [r for r in ranks if r is not None]
    return {
        "n": n,
        "hit_rate": round(len(hits) / n, 4),
        "mrr": round(sum(1 / r for r in hits) / n, 4),
    }


def group_summary(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, float]]:
    """Summaries per distinct value of `key` (each row has a `rank`)."""
    groups: dict[str, list[int | None]] = {}
    for row in rows:
        groups.setdefault(str(row.get(key)), []).append(row["rank"])
    return {k: summarize(v) for k, v in sorted(groups.items())}

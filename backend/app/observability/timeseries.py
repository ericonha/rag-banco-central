"""Fill gaps in per-day series (stdlib only) so charts always get one point per day."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

QUERY_FIELDS = ("queries", "errors", "avg_latency_ms", "tokens", "cost_usd", "ungrounded")
FEEDBACK_FIELDS = ("up", "down")


def build_timeseries(
    query_rows: list[dict[str, Any]],
    feedback_rows: list[dict[str, Any]],
    days: int,
    today: date | None = None,
) -> list[dict[str, Any]]:
    """One dict per day (oldest first, `days` entries ending today), zeros where nothing happened."""
    end = today or date.today()
    q = {r["day"]: r for r in query_rows}
    f = {r["day"]: r for r in feedback_rows}
    points = []
    for i in range(days - 1, -1, -1):
        day = end - timedelta(days=i)
        point: dict[str, Any] = {"day": day.isoformat()}
        for name in QUERY_FIELDS:
            point[name] = float((q.get(day) or {}).get(name) or 0)
        for name in FEEDBACK_FIELDS:
            point[name] = int((f.get(day) or {}).get(name) or 0)
        for name in ("queries", "errors", "tokens", "ungrounded"):
            point[name] = int(point[name])
        points.append(point)
    return points

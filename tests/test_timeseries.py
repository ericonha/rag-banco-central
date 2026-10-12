"""Gap filling of the Logs charts series (pure)."""
from datetime import date

from app.observability.timeseries import build_timeseries

TODAY = date(2026, 10, 12)


def test_one_point_per_day_oldest_first_with_zero_fill() -> None:
    pts = build_timeseries([], [], 3, today=TODAY)
    assert [p["day"] for p in pts] == ["2026-10-10", "2026-10-11", "2026-10-12"]
    assert all(p["queries"] == 0 and p["up"] == 0 and p["cost_usd"] == 0.0 for p in pts)


def test_rows_land_on_their_day_with_types() -> None:
    q = [{"day": date(2026, 10, 11), "queries": 4, "errors": 1, "avg_latency_ms": 812.5,
          "tokens": 1200, "cost_usd": 0.0123, "ungrounded": 2}]
    f = [{"day": date(2026, 10, 12), "up": 3, "down": 1}]
    pts = build_timeseries(q, f, 3, today=TODAY)
    assert pts[1]["queries"] == 4 and isinstance(pts[1]["queries"], int)
    assert pts[1]["avg_latency_ms"] == 812.5
    assert pts[1]["ungrounded"] == 2
    assert (pts[2]["up"], pts[2]["down"]) == (3, 1)
    assert pts[0]["queries"] == 0


def test_rows_outside_the_window_are_ignored() -> None:
    q = [{"day": date(2026, 9, 1), "queries": 9}]
    assert sum(p["queries"] for p in build_timeseries(q, [], 3, today=TODAY)) == 0

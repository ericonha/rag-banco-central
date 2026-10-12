"""Pipeline health evaluation (pure)."""
from datetime import datetime, timedelta, timezone

from app.observability.health import evaluate_health

NOW = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)


def _run(stage: str, status: str = "ok", ago_h: float = 1, **extra) -> dict:
    return {"stage": stage, "status": status, "started_at": NOW - timedelta(hours=ago_h),
            "items_failed": 0, "items_total": 0, **extra}


def test_all_ok() -> None:
    h = evaluate_health([_run("scrape"), _run("chunk"), _run("embed")], NOW)
    assert h["status"] == "ok" and h["issues"] == []
    assert h["last_run_at"]


def test_no_runs_yet_is_ok() -> None:
    assert evaluate_health([], NOW) == {"status": "ok", "issues": [], "last_run_at": None}


def test_failed_stage_is_error() -> None:
    h = evaluate_health([_run("scrape"), _run("embed", "failed")], NOW)
    assert h["status"] == "error"
    assert [(i["stage"], i["kind"]) for i in h["issues"]] == [("embed", "failed")]


def test_done_with_errors_is_warning() -> None:
    h = evaluate_health([_run("chunk", "done_with_errors", items_failed=2, items_total=10)], NOW)
    assert h["status"] == "warning"
    assert "2 de 10" in h["issues"][0]["message"]


def test_stuck_running_stage() -> None:
    assert evaluate_health([_run("embed", "running", ago_h=5)], NOW)["issues"][0]["kind"] == "stuck"
    assert evaluate_health([_run("embed", "running", ago_h=1)], NOW)["status"] == "ok"


def test_stale_scrape() -> None:
    h = evaluate_health([_run("scrape", ago_h=40)], NOW, stale_hours=36)
    assert h["status"] == "warning" and h["issues"][0]["kind"] == "stale"
    assert evaluate_health([_run("scrape", ago_h=40)], NOW, stale_hours=48)["status"] == "ok"


def test_error_outranks_warning() -> None:
    h = evaluate_health([_run("scrape", ago_h=40), _run("embed", "failed")], NOW)
    assert h["status"] == "error" and len(h["issues"]) == 2

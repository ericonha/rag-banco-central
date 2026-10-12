"""Pipeline health evaluation (stdlib only): turns the latest run of each stage into alerts."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

STAGES = ("scrape", "chunk", "embed")
RUNNING_TOO_LONG = timedelta(hours=3)
_SEVERITY = {"ok": 0, "warning": 1, "error": 2}


def evaluate_health(
    latest_runs: list[dict[str, Any]], now: datetime, stale_hours: int = 36
) -> dict[str, Any]:
    """
    `latest_runs`: the most recent pipeline_runs row per stage (stage, status, started_at,
    items_failed, items_total). Returns {"status": ok|warning|error, "issues": [...],
    "last_run_at": iso|None}.
    """
    issues: list[dict[str, Any]] = []
    by_stage = {r["stage"]: r for r in latest_runs}

    for stage in STAGES:
        run = by_stage.get(stage)
        if not run:
            continue
        status, started = run["status"], run["started_at"]
        if status == "failed":
            issues.append(_issue(stage, "error", "failed", "a última execução falhou", started))
        elif status == "done_with_errors":
            n = run.get("items_failed") or 0
            total = run.get("items_total") or 0
            issues.append(
                _issue(stage, "warning", "errors", f"{n} de {total} itens com erro na última execução", started)
            )
        elif status == "running" and now - started > RUNNING_TOO_LONG:
            issues.append(_issue(stage, "warning", "stuck", "execução parada há mais de 3 h", started))

    scrape = by_stage.get("scrape")
    if scrape and now - scrape["started_at"] > timedelta(hours=stale_hours):
        hours = int((now - scrape["started_at"]).total_seconds() // 3600)
        issues.append(_issue("scrape", "warning", "stale", f"nenhuma coleta há {hours} h", scrape["started_at"]))

    status = max((i["severity"] for i in issues), key=_SEVERITY.__getitem__, default="ok")
    last = max((r["started_at"] for r in latest_runs), default=None)
    return {"status": status, "issues": issues, "last_run_at": last.isoformat() if last else None}


def _issue(stage: str, severity: str, kind: str, message: str, at: datetime) -> dict[str, Any]:
    return {"stage": stage, "severity": severity, "kind": kind, "message": message, "at": at.isoformat()}

"""Stage runner of the pipeline (no database needed)."""
import pytest

from app.worker.pipeline import _run_stage


async def _ok() -> None:
    return None


async def _exit(code: int) -> None:
    raise SystemExit(code)


async def _crash() -> None:
    raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_stage_success() -> None:
    assert await _run_stage("x", _ok) is True


@pytest.mark.asyncio
async def test_stage_exit_zero_is_success() -> None:
    assert await _run_stage("x", lambda: _exit(0)) is True


@pytest.mark.asyncio
async def test_stage_exit_one_means_finished_with_errors() -> None:
    assert await _run_stage("x", lambda: _exit(1)) is False


@pytest.mark.asyncio
async def test_stage_exception_does_not_propagate() -> None:
    assert await _run_stage("x", _crash) is False

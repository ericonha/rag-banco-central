"""Schedule math of the pipeline scheduler (no database needed)."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.worker.scheduler import next_run, parse_hhmm

SP = ZoneInfo("America/Sao_Paulo")


def test_parse_hhmm() -> None:
    assert parse_hhmm("06:00") == (6, 0)
    assert parse_hhmm(" 23:59 ") == (23, 59)


def test_parse_hhmm_rejects_bad_values() -> None:
    for bad in ("24:00", "12:60", "6", "abc", ""):
        with pytest.raises(ValueError):
            parse_hhmm(bad)


def test_next_run_later_today() -> None:
    now = datetime(2026, 10, 12, 5, 0, tzinfo=SP)
    assert next_run(now, 6, 0) == datetime(2026, 10, 12, 6, 0, tzinfo=SP)


def test_next_run_is_strictly_in_the_future() -> None:
    now = datetime(2026, 10, 12, 6, 0, tzinfo=SP)
    assert next_run(now, 6, 0) == datetime(2026, 10, 13, 6, 0, tzinfo=SP)


def test_next_run_rolls_over_midnight_and_month() -> None:
    now = datetime(2026, 10, 31, 23, 59, tzinfo=SP)
    assert next_run(now, 0, 5) == datetime(2026, 11, 1, 0, 5, tzinfo=SP)


def test_next_run_keeps_wall_clock_across_dst() -> None:
    berlin = ZoneInfo("Europe/Berlin")
    now = datetime(2026, 3, 28, 10, 0, tzinfo=berlin)  # CET, DST starts next day
    nxt = next_run(now, 6, 0)
    assert (nxt.year, nxt.month, nxt.day, nxt.hour, nxt.minute) == (2026, 3, 29, 6, 0)
    assert nxt.utcoffset().total_seconds() == 2 * 3600  # CEST

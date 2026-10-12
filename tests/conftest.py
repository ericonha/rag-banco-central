"""Shared fixtures. DB tests run only when RUN_DB_TESTS=1 and DATABASE_URL points to a
migrated Postgres (CI sets both). They only touch rows they create and delete them afterwards."""
import os
import uuid

import pytest


@pytest.fixture
def db():
    """Autocommit sync connection plus a list of cleanup callbacks."""
    if os.environ.get("RUN_DB_TESTS") != "1" or not os.environ.get("DATABASE_URL"):
        pytest.skip("set RUN_DB_TESTS=1 and DATABASE_URL to run database tests")
    import psycopg

    try:
        conn = psycopg.connect(os.environ["DATABASE_URL"], autocommit=True, connect_timeout=5)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"database not reachable: {exc}")
    cleanups: list[tuple[str, tuple]] = []
    conn.cleanups = cleanups  # type: ignore[attr-defined]
    try:
        yield conn
    finally:
        for sql, params in reversed(cleanups):
            conn.execute(sql, params)
        conn.close()


@pytest.fixture
def token() -> str:
    return uuid.uuid4().hex[:12]

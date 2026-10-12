"""Database connection helpers (psycopg v3, async)."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import psycopg
from psycopg.rows import dict_row

from app.config import get_settings


@asynccontextmanager
async def get_conn() -> AsyncIterator[psycopg.AsyncConnection]:
    """Yield a single async connection, auto-committed per call."""
    settings = get_settings()
    async with await psycopg.AsyncConnection.connect(
        settings.database_url,
        row_factory=dict_row,
        autocommit=False,
    ) as conn:
        yield conn

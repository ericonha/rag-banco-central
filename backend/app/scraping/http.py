"""Shared httpx client with retry, rate-limiting, and a polite User-Agent."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx

logger = logging.getLogger(__name__)

USER_AGENT = (
    "bcb-rag-scraper/0.1 "
    "(portfolio project; contact: github.com/ericrhein; respectful scraper)"
)

# Seconds to wait between consecutive requests to the same host.
REQUEST_DELAY = 0.5

# httpx transport with automatic retries on transient errors.
_TRANSPORT = httpx.AsyncHTTPTransport(retries=3)


@asynccontextmanager
async def bcb_client() -> AsyncIterator[httpx.AsyncClient]:
    """Yield a shared httpx client configured for BCB API calls."""
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=httpx.Timeout(30.0),
        transport=_TRANSPORT,
        follow_redirects=True,
    ) as client:
        yield client


async def get_json(client: httpx.AsyncClient, url: str, **params: object) -> object:
    """GET a BCB JSON endpoint, apply polite delay, raise on HTTP errors."""
    await asyncio.sleep(REQUEST_DELAY)
    r = await client.get(url, params=params)  # type: ignore[arg-type]
    r.raise_for_status()
    logger.debug("GET %s -> %d", r.url, r.status_code)
    return r.json()

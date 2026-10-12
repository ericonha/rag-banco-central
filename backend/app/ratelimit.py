"""Per-client sliding-window rate limiting (stdlib only, in-memory, resets on restart)."""
from __future__ import annotations

import time
from collections.abc import Mapping

CHAT_PATHS = ("/api/chat", "/api/chat/stream")


def bucket_for(method: str, path: str) -> str:
    """Endpoints that call the LLM share a (much lower) budget than everything else."""
    return "chat" if method == "POST" and path.rstrip("/") in CHAT_PATHS else "default"


def client_ip(headers: Mapping[str, str], peer: str | None, trust_proxy: bool) -> str:
    """Peer address; behind a reverse proxy (trust_proxy) the first X-Forwarded-For hop."""
    if trust_proxy:
        forwarded = headers.get("x-forwarded-for", "")
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return peer or "unknown"


class RateLimiter:
    def __init__(self, limits: dict[str, int], window_seconds: float = 60.0) -> None:
        self.limits = limits
        self.window = window_seconds
        self.requests: dict[tuple[str, str], list[float]] = {}
        self._last_prune = 0.0

    def check(self, ip: str, bucket: str, now: float | None = None) -> tuple[bool, int]:
        """Returns (allowed, retry_after_seconds). A limit <= 0 disables the bucket."""
        now = time.monotonic() if now is None else now
        limit = self.limits.get(bucket, 0)
        if limit <= 0:
            return True, 0
        self._prune(now)
        key = (ip, bucket)
        hits = [t for t in self.requests.get(key, []) if t > now - self.window]
        if len(hits) >= limit:
            self.requests[key] = hits
            return False, max(1, int(hits[0] + self.window - now) + 1)
        hits.append(now)
        self.requests[key] = hits
        return True, 0

    def _prune(self, now: float) -> None:
        """Drop idle clients so the table cannot grow without bound."""
        if now - self._last_prune < self.window:
            return
        self._last_prune = now
        cutoff = now - self.window
        for key in [k for k, v in self.requests.items() if not v or v[-1] <= cutoff]:
            del self.requests[key]

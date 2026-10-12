"""Sliding-window rate limiter and client IP resolution (pure)."""
from app.ratelimit import RateLimiter, bucket_for, client_ip


def test_allows_up_to_the_limit_then_blocks_with_retry_after() -> None:
    rl = RateLimiter({"default": 3})
    assert [rl.check("1.1.1.1", "default", now=t)[0] for t in (0, 1, 2)] == [True, True, True]
    allowed, retry = rl.check("1.1.1.1", "default", now=3)
    assert allowed is False
    assert 1 <= retry <= 60


def test_window_slides() -> None:
    rl = RateLimiter({"default": 2})
    rl.check("a", "default", now=0)
    rl.check("a", "default", now=1)
    assert rl.check("a", "default", now=10)[0] is False
    assert rl.check("a", "default", now=61)[0] is True  # first hit left the window


def test_clients_and_buckets_are_independent() -> None:
    rl = RateLimiter({"default": 1, "chat": 1})
    assert rl.check("a", "default", now=0)[0]
    assert not rl.check("a", "default", now=1)[0]
    assert rl.check("b", "default", now=1)[0]
    assert rl.check("a", "chat", now=1)[0]


def test_zero_limit_disables_the_bucket() -> None:
    rl = RateLimiter({"default": 0})
    assert all(rl.check("a", "default", now=i)[0] for i in range(100))


def test_idle_clients_are_pruned() -> None:
    rl = RateLimiter({"default": 5})
    rl.check("old", "default", now=0)
    rl.check("new", "default", now=200)
    assert ("old", "default") not in rl.requests


def test_bucket_for() -> None:
    assert bucket_for("POST", "/api/chat") == "chat"
    assert bucket_for("POST", "/api/chat/stream") == "chat"
    assert bucket_for("GET", "/api/chat") == "default"
    assert bucket_for("GET", "/api/admin/runs") == "default"


def test_client_ip_proxy_header_only_when_trusted() -> None:
    headers = {"x-forwarded-for": "9.9.9.9, 10.0.0.1"}
    assert client_ip(headers, "172.18.0.1", trust_proxy=False) == "172.18.0.1"
    assert client_ip(headers, "172.18.0.1", trust_proxy=True) == "9.9.9.9"
    assert client_ip({}, "172.18.0.1", trust_proxy=True) == "172.18.0.1"
    assert client_ip({}, None, trust_proxy=False) == "unknown"

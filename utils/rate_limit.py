"""Small cache-backed rate limiter for sensitive unauthenticated endpoints."""
import hashlib
from dataclasses import dataclass

from django.core.cache import cache
from django.http import HttpRequest


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    retry_after: int


def _hash_part(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def client_ip(req: HttpRequest) -> str:
    return req.META.get("REMOTE_ADDR", "") or "unknown"


def check_rate_limit(scope: str, subject: str, max_attempts: int, window_seconds: int) -> RateLimitResult:
    """Consume one attempt in a fixed window and report whether it is allowed."""
    if max_attempts <= 0 or window_seconds <= 0:
        return RateLimitResult(True, 0)

    key = f"rate-limit:{scope}:{_hash_part(subject)}"
    added = cache.add(key, 1, timeout=window_seconds)
    if added:
        return RateLimitResult(True, 0)

    try:
        attempts = cache.incr(key)
    except ValueError:
        cache.add(key, 1, timeout=window_seconds)
        return RateLimitResult(True, 0)

    if attempts > max_attempts:
        return RateLimitResult(False, window_seconds)
    return RateLimitResult(True, 0)


def check_any_rate_limit(limits: list[tuple[str, str, int, int]]) -> RateLimitResult:
    """Apply multiple limits and reject when any one of them has been exceeded."""
    retry_after = 0
    for scope, subject, max_attempts, window_seconds in limits:
        result = check_rate_limit(scope, subject, max_attempts, window_seconds)
        if not result.allowed:
            retry_after = max(retry_after, result.retry_after)
    if retry_after > 0:
        return RateLimitResult(False, retry_after)
    return RateLimitResult(True, 0)

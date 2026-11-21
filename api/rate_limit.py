"""Simple in-memory token-bucket rate limiter for sensitive endpoints."""

from __future__ import annotations

import time
from dataclasses import dataclass

from fastapi import Request


@dataclass
class Bucket:
    tokens: float
    updated: float


class RateLimiter:
    def __init__(self, rate_per_minute: float = 30.0, burst: int = 10) -> None:
        self.rate_per_minute = rate_per_minute
        self.burst = burst
        self.buckets: dict[str, Bucket] = {}

    def check(self, key: str) -> bool:
        now = time.monotonic()
        bucket = self.buckets.get(key)
        if bucket is None:
            bucket = Bucket(tokens=float(self.burst), updated=now)
            self.buckets[key] = bucket
        elapsed = now - bucket.updated
        bucket.tokens = min(float(self.burst), bucket.tokens + elapsed * (self.rate_per_minute / 60.0))
        bucket.updated = now
        if bucket.tokens < 1.0:
            return False
        bucket.tokens -= 1.0
        return True


_limiter = RateLimiter()


def client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def rate_limit(request: Request, per_minute: float = 30.0) -> None:
    from fastapi import HTTPException

    if not _limiter.check(client_key(request)):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

"""Thread-safe token buckets for bounded social interaction rates."""

import time
from threading import Lock

from utils import metrics as metrics_registry


class TokenBucket:
    def __init__(self, rate_per_second, burst, clock=None):
        if rate_per_second <= 0 or burst <= 0:
            raise ValueError("rate and burst must be positive")
        self.rate_per_second = float(rate_per_second)
        self.burst = float(burst)
        self._clock = clock
        self._lock = Lock()
        self._tokens = float(burst)
        self._updated_at = self._now()

    def _now(self):
        return self._clock() if self._clock is not None else time.monotonic()

    def consume(self, amount=1):
        if amount <= 0:
            raise ValueError("amount must be positive")
        with self._lock:
            now = self._now()
            elapsed = max(0.0, now - self._updated_at)
            self._tokens = min(self.burst, self._tokens + elapsed * self.rate_per_second)
            self._updated_at = now
            if self._tokens < amount:
                return False
            self._tokens -= amount
            return True


class SessionRateLimiter:
    def __init__(self, limits, clock=None):
        self._buckets = {
            name: TokenBucket(rate, burst, clock=clock)
            for name, (rate, burst) in limits.items()
        }

    def allow(self, name):
        bucket = self._buckets[name]
        allowed = bucket.consume()
        if not allowed:
            metrics_registry.metrics.inc(f"ofps.rate_limit.{name}_rejections_total")
        return allowed

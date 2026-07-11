"""In-memory sliding window rate limiter (100 req/min per IP)."""

import time
import threading
from collections import defaultdict

DEFAULT_RATE_LIMIT = 100  # requests
DEFAULT_WINDOW_SECONDS = 60


class RateLimiter:
    """Sliding window rate limiter using a per-IP request log."""

    def __init__(self, rate_limit=DEFAULT_RATE_LIMIT, window_seconds=DEFAULT_WINDOW_SECONDS):
        self.rate_limit = rate_limit
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def is_allowed(self, ip: str) -> bool:
        """Return True if the request is allowed, False if rate-limited."""
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            timestamps = self._requests[ip]
            # Prune expired entries
            self._requests[ip] = timestamps = [t for t in timestamps if t > cutoff]

            if len(timestamps) >= self.rate_limit:
                return False

            timestamps.append(now)
            return True

    def reset(self, ip: str | None = None):
        """Reset counters. If ip is None, reset all."""
        with self._lock:
            if ip:
                self._requests.pop(ip, None)
            else:
                self._requests.clear()


def get_rate_limiter() -> RateLimiter:
    """Singleton rate limiter instance."""
    if not hasattr(get_rate_limiter, "_instance"):
        get_rate_limiter._instance = RateLimiter()
    return get_rate_limiter._instance

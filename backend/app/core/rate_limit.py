import threading
import time
from collections import OrderedDict, deque

from fastapi import HTTPException, status


class RateLimiter:
    """In-process sliding-window rate limiter, keyed by an arbitrary string (e.g. an IP address,
    or an "ip:email" pair — see auth.py for how each endpoint keys it). Deliberately no external
    store: resets on restart and isn't shared across instances, which matches this app's existing
    single-process deployment shape (see excel_io.workbook_write_lock's own docstring, which
    already depends on that same assumption).

    max_tracked_keys bounds memory the same way excel_io.py's workbook caches do — oldest-
    touched keys are evicted once the cap is hit, so an attacker cycling through many distinct
    keys (e.g. many IPs) can't grow this dict without bound."""

    def __init__(self, max_attempts: int, window_seconds: float, max_tracked_keys: int = 10_000):
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._max_tracked_keys = max_tracked_keys
        self._attempts: "OrderedDict[str, deque[float]]" = OrderedDict()
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        """Raises HTTP 429 if `key` has already made max_attempts within the trailing window;
        otherwise records this attempt and returns normally. Every call to the endpoint counts,
        not just failures — simpler, and still effective against brute-forcing since a genuine
        user logging in/retrying a handful of times in a few minutes stays well under the
        (deliberately generous) limits chosen for each endpoint in auth.py."""
        now = time.monotonic()
        with self._lock:
            attempts = self._attempts.setdefault(key, deque())
            self._attempts.move_to_end(key)
            while attempts and now - attempts[0] > self._window_seconds:
                attempts.popleft()
            if len(attempts) >= self._max_attempts:
                retry_after = max(1, int(self._window_seconds - (now - attempts[0])))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many attempts. Please try again later.",
                    headers={"Retry-After": str(retry_after)},
                )
            attempts.append(now)
            while len(self._attempts) > self._max_tracked_keys:
                self._attempts.popitem(last=False)

    def reset(self) -> None:
        """Test-only: clears all tracked state so test runs don't inherit rate-limit state from
        unrelated earlier tests sharing the same TestClient (and therefore the same client IP)."""
        with self._lock:
            self._attempts.clear()

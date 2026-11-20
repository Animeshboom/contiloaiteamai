import threading
import time
from collections import defaultdict, deque

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings
from app.core.errors import AppError

limiter = Limiter(key_func=get_remote_address, enabled=get_settings().environment != "test")


class TooManyAttempts(AppError):
    status_code = 429
    code = "rate_limited"


class FailedLoginThrottle:
    """Per-account brute-force guard.

    The per-IP limit above relies on the client IP, which on hosted proxies comes from
    X-Forwarded-For and can be forged by the client. This limit is keyed by the account
    email instead, so password guessing against one account is capped regardless of IP.
    In-memory: it resets on restart and is per process (fine for the single free instance).
    """

    def __init__(self, max_failures: int, window_seconds: float, enabled: bool = True):
        self.max_failures = max_failures
        self.window = window_seconds
        self.enabled = enabled
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> deque[float]:
        q = self._failures[key]
        while q and now - q[0] > self.window:
            q.popleft()
        return q

    def check(self, email: str) -> None:
        if not self.enabled:
            return
        key = email.strip().lower()
        with self._lock:
            q = self._recent(key, time.monotonic())
            blocked = len(q) >= self.max_failures
            if not q:
                self._failures.pop(key, None)
        if blocked:
            raise TooManyAttempts("Too many failed sign-in attempts for this account. Try again in a few minutes.")

    def record_failure(self, email: str) -> None:
        if not self.enabled:
            return
        key = email.strip().lower()
        with self._lock:
            now = time.monotonic()
            if len(self._failures) > 10_000:  # bound memory under email-spraying: drop expired entries
                for k in [k for k, q in self._failures.items() if not q or now - q[-1] > self.window]:
                    del self._failures[k]
            self._recent(key, now).append(now)

    def reset(self, email: str) -> None:
        with self._lock:
            self._failures.pop(email.strip().lower(), None)


_s = get_settings()
login_throttle = FailedLoginThrottle(
    max_failures=_s.login_max_failures,
    window_seconds=_s.login_failure_window_minutes * 60,
    enabled=_s.environment != "test",
)

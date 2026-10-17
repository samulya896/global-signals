"""Small per-process request limiter for local development.

Production deployments should also enforce limits at the reverse proxy or API gateway,
because in-process counters are not shared between worker processes or hosts.
"""

from collections import defaultdict, deque
from threading import Lock
import time

from fastapi import HTTPException, Request


_hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
_lock = Lock()


def enforce_rate_limit(request: Request, action: str, limit: int, window_seconds: int) -> None:
    # Do not trust X-Forwarded-For directly; configure trusted proxy handling at the edge.
    client_ip = request.client.host if request.client else "unknown"
    key = (action, client_ip)
    now = time.monotonic()
    with _lock:
        events = _hits[key]
        while events and now - events[0] >= window_seconds:
            events.popleft()
        if len(events) >= limit:
            raise HTTPException(status_code=429, detail="Too many attempts. Please wait and try again.")
        events.append(now)

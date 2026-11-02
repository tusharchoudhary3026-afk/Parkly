"""Small process-local throttle for local/demo deployments."""
import asyncio
import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._windows: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def allow(self, key: str, limit: int, period_seconds: int = 60) -> bool:
        now=time.monotonic()
        async with self._lock:
            window=self._windows[key]
            while window and window[0]<=now-period_seconds:
                window.popleft()
            if len(window)>=limit:
                return False
            window.append(now)
            if len(self._windows)>10_000:
                stale=[name for name,values in self._windows.items() if not values or values[-1]<=now-period_seconds]
                for name in stale:
                    self._windows.pop(name,None)
            return True

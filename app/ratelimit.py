"""简易内存限流：按 IP 做滑动窗口。

单进程部署够用；将来多 worker 要换成 Redis。
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, max_events: int = 20000) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._max_events = max_events

    def check(self, key: str, seconds: int, limit: int) -> float:
        """在 seconds 秒内最多允许 limit 次。

        返回 0 表示放行；大于 0 表示还需要等待多少秒。
        """
        now = time.time()
        window_start = now - seconds
        with self._lock:
            bucket = self._hits[key]
            while bucket and bucket[0] < window_start:
                bucket.popleft()
            if len(bucket) >= limit:
                return max(0.0, bucket[0] + seconds - now)
            bucket.append(now)
            # 粗暴防止 key 无限增长
            if len(self._hits) > self._max_events:
                stale = [k for k, v in self._hits.items() if not v]
                for k in stale[:1000]:
                    self._hits.pop(k, None)
        return 0.0

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def clear(self) -> None:
        """清空所有计数（测试用）。"""
        with self._lock:
            self._hits.clear()


rate_limiter = RateLimiter()

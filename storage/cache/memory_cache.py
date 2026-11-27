"""进程内 TTL 缓存，替代 Redis 的轻量实现。

只用于单进程便携部署；不保证跨进程/重启持久化。
"""
from __future__ import annotations

import copy
import threading
import time
from typing import Any, Optional


class MemoryTTLCache:
    def __init__(self, default_ttl: int = 3600, max_entries: int = 4096):
        self.default_ttl = default_ttl
        self.max_entries = max_entries
        self._data: dict[str, tuple[float, Any]] = {}
        self._lock = threading.RLock()

    def _expired(self, expires_at: float) -> bool:
        return expires_at != 0 and expires_at <= time.monotonic()

    def set_data(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        ttl = self.default_ttl if ttl is None else ttl
        expires_at = 0 if ttl <= 0 else time.monotonic() + ttl
        with self._lock:
            # 简单的 FIFO 淘汰：便携场景条目很少
            if key not in self._data and len(self._data) >= self.max_entries:
                oldest_key = next(iter(self._data), None)
                if oldest_key is not None:
                    self._data.pop(oldest_key, None)
            self._data[key] = (expires_at, copy.deepcopy(value))

    def get_data(self, key: str) -> Optional[Any]:
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            expires_at, value = item
            if self._expired(expires_at):
                self._data.pop(key, None)
                return None
            return copy.deepcopy(value)

    def get_answer(self, query: str) -> Optional[Any]:
        return self.get_data(f"answer:{query}")

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)

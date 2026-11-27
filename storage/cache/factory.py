"""缓存客户端工厂：embedded → MemoryTTLCache；external → RedisClient。"""
from __future__ import annotations

import threading

from base.config import config

_cache_client = None
_lock = threading.Lock()


def get_cache_client() -> object:
    global _cache_client
    if _cache_client is not None:
        return _cache_client
    with _lock:
        if _cache_client is not None:
            return _cache_client
        if config.STORAGE_BACKEND == "external":
            from mysql_qa.cache.redis_client import RedisClient

            _cache_client = RedisClient()
        else:
            from storage.cache.memory_cache import MemoryTTLCache

            _cache_client = MemoryTTLCache()
        return _cache_client


def reset_cache_client() -> None:
    global _cache_client
    with _lock:
        _cache_client = None

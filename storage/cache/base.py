"""缓存客户端协议。"""
from __future__ import annotations

from typing import Any, Optional, Protocol


class CacheClient(Protocol):
    def set_data(self, key: str, value: Any, ttl: Optional[int] = None) -> None: ...

    def get_data(self, key: str) -> Optional[Any]: ...

    def get_answer(self, query: str) -> Optional[Any]: ...

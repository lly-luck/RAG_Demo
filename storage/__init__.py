"""存储适配层：默认内嵌（SQLite + 内存缓存），可切换 external（MySQL/Redis）。"""

from storage.cache.factory import get_cache_client
from storage.db.factory import get_db_client

__all__ = ["get_db_client", "get_cache_client"]

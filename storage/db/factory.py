"""数据库客户端工厂。

默认 embedded → SQLiteClient；external → 现有 MySQLClient。
外部依赖 pymysql 只在 external 模式下导入，便携包运行期可不安装。
"""
from __future__ import annotations

import threading
from typing import Optional

from base import paths
from base.config import config

_db_client = None
_lock = threading.Lock()


def get_db_client() -> object:
    global _db_client
    if _db_client is not None:
        return _db_client
    with _lock:
        if _db_client is not None:
            return _db_client
        if config.STORAGE_BACKEND == "external":
            from mysql_qa.db.mysql_client import MySQLClient

            _db_client = MySQLClient()
        else:
            paths.ensure_user_data()
            from storage.db.sqlite_client import SQLiteClient

            _db_client = SQLiteClient()
        return _db_client


def reset_db_client() -> None:
    """测试/切换后端时释放单例。"""
    global _db_client
    with _lock:
        if _db_client is not None:
            try:
                _db_client.close()
            except Exception:
                pass
        _db_client = None

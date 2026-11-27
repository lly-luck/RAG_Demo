"""向量库工厂：embedded → Chroma；external → Milvus（懒导入 pymilvus）。"""
from __future__ import annotations

import threading

from base import paths
from base.config import config

_vector_store = None
_lock = threading.Lock()


def get_vector_store() -> object:
    global _vector_store
    if _vector_store is not None:
        return _vector_store
    with _lock:
        if _vector_store is not None:
            return _vector_store
        if config.STORAGE_BACKEND == "external":
            from rag_qa.core.vector_store import MilvusVectorStore

            _vector_store = MilvusVectorStore()
        else:
            paths.ensure_user_data()
            from rag_qa.core.chroma_store import ChromaVectorStore

            _vector_store = ChromaVectorStore()
        return _vector_store


def reset_vector_store() -> None:
    global _vector_store
    with _lock:
        _vector_store = None

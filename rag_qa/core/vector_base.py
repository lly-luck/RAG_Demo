"""向量库接口协议。"""
from __future__ import annotations

from typing import List, Optional, Protocol


class VectorStoreProtocol(Protocol):
    def add_documents(self, documents: list) -> None: ...

    def hybrid_search_with_reranker(
        self,
        query: str,
        k: Optional[int] = None,
        source_filter: Optional[str] = None,
    ) -> List: ...

    def warmup(self) -> None: ...

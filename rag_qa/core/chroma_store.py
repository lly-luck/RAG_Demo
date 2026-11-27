"""Chroma 本地持久化向量库（便携包默认后端）。

检索链路与原 Milvus 版本保持一致：
1. BGE-M3 dense 语义召回（Chroma 余弦距离）；
2. jieba + BM25 关键词召回；
3. 两路分数 min-max 归一化后 0.7/1.0 加权融合；
4. 父块去重；
5. CrossEncoder 重排，取 candidate_m。

Chroma 1.3.5 的本地 search() 混合检索是 hosted-only 实验 API，因此稀疏通道
用 BM25 实现，而不是 Chroma 的 sparse vector。
"""
from __future__ import annotations

import hashlib
import os
from typing import Dict, List, Optional

import numpy as np
from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

from base.config import config
from base.logger import logger
from mysql_qa.util.doc_preprocess import preprocess_text
from rag_qa.core.model_registry import get_embedding_model, get_reranker_model


class ChromaVectorStore:
    def __init__(
        self,
        persist_dir: Optional[str] = None,
        collection_name: Optional[str] = None,
        embedding=None,
        reranker=None,
        load_models: bool = True,
    ):
        import chromadb
        from chromadb.config import Settings

        self.persist_dir = str(persist_dir or config.VECTOR_DB_DIR)
        self.collection_name = collection_name or config.MILVUS_COLLECTION_NAME
        os.makedirs(self.persist_dir, exist_ok=True)

        self.client = chromadb.PersistentClient(
            path=self.persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
            embedding_function=None,
        )

        self._embedding = embedding
        self._reranker = reranker
        if load_models and self._embedding is None:
            self._embedding = get_embedding_model()

        self._bm25: Optional[BM25Okapi] = None
        self._ids: List[str] = []
        self._documents: List[str] = []
        self._metadatas: List[dict] = []
        self._load_index()
        logger.info(
            "Chroma 向量库就绪：%s，集合 %s，子块 %d",
            self.persist_dir,
            self.collection_name,
            len(self._documents),
        )

    # ============================ 索引 ============================
    def _load_index(self) -> None:
        result = self.collection.get(include=["documents", "metadatas"])
        self._ids = list(result.get("ids") or [])
        self._documents = [doc or "" for doc in (result.get("documents") or [])]
        self._metadatas = list(result.get("metadatas") or [])
        if len(self._documents) != len(self._ids):
            logger.warning("Chroma 文档与 ID 数量不一致，BM25 索引可能不完整")

        if self._documents:
            tokenized = [preprocess_text(doc) for doc in self._documents]
            self._bm25 = BM25Okapi(tokenized)
        else:
            self._bm25 = None

    def count(self) -> int:
        return int(self.collection.count())

    def warmup(self) -> None:
        if self._embedding is None:
            self._embedding = get_embedding_model()
        if self._reranker is None:
            self._reranker = get_reranker_model()

    # ============================ 写入 ============================
    def add_documents(self, documents, batch_size: int = 16) -> None:
        if not documents:
            return
        if self._embedding is None:
            self._embedding = get_embedding_model()

        for start in range(0, len(documents), batch_size):
            batch = documents[start:start + batch_size]
            texts = [doc.page_content for doc in batch]
            embeddings = self._embedding(texts)
            dense = embeddings["dense"]
            if hasattr(dense, "tolist"):
                dense = dense.tolist()
            else:
                # BGEM3EmbeddingFunction 返回 list[np.ndarray]
                dense = [row.tolist() if hasattr(row, "tolist") else row for row in dense]

            ids = [hashlib.md5(text.encode("utf-8")).hexdigest() for text in texts]
            metadatas = []
            for doc in batch:
                meta = doc.metadata or {}
                metadatas.append({
                    "parent_id": str(meta.get("parent_id") or ""),
                    "parent_content": str(meta.get("parent_content") or doc.page_content),
                    "source": str(meta.get("source") or "unknown"),
                    "timestamp": str(meta.get("timestamp") or "unknown"),
                })

            self.collection.upsert(
                ids=ids,
                documents=texts,
                metadatas=metadatas,
                embeddings=dense,
            )
            logger.info("Chroma 已写入 %d/%d 个子块", min(start + batch_size, len(documents)), len(documents))

        self._load_index()

    # ============================ 检索 ============================
    @staticmethod
    def _normalize(values: List[float]) -> np.ndarray:
        array = np.asarray(values, dtype=np.float64)
        if array.size == 0:
            return array
        finite = array[np.isfinite(array)]
        if finite.size == 0:
            return np.zeros_like(array)
        low, high = float(finite.min()), float(finite.max())
        if high - low < 1e-12:
            return np.zeros_like(array)
        normalized = (array - low) / (high - low)
        return np.nan_to_num(normalized, nan=0.0, posinf=0.0, neginf=0.0)

    def hybrid_search_with_reranker(
        self,
        query: str,
        k: Optional[int] = None,
        source_filter: Optional[str] = None,
    ) -> List[Document]:
        k = int(k or config.RETRIEVAL_K)
        count = self.count()
        if count == 0:
            logger.warning("Chroma 集合为空，跳过检索")
            return []

        if source_filter and source_filter not in config.VALID_SOURCES:
            logger.warning("非法 source_filter=%s，已忽略", source_filter)
            source_filter = None

        if self._embedding is None:
            self._embedding = get_embedding_model()
        embedding_result = self._embedding([query])
        dense_query = embedding_result["dense"][0]
        if hasattr(dense_query, "tolist"):
            dense_query = dense_query.tolist()

        n_results = min(max(k * 4, 10), count)
        where = {"source": source_filter} if source_filter else None

        dense_result = self.collection.query(
            query_embeddings=[dense_query],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        candidates: Dict[str, dict] = {}
        dense_ids = (dense_result.get("ids") or [[]])[0]
        dense_docs = (dense_result.get("documents") or [[]])[0]
        dense_metas = (dense_result.get("metadatas") or [[]])[0]
        dense_distances = (dense_result.get("distances") or [[]])[0]
        for doc_id, text, meta, distance in zip(dense_ids, dense_docs, dense_metas, dense_distances):
            candidates[doc_id] = {
                "text": text or "",
                "metadata": meta or {},
                # Chroma cosine distance → 相似度
                "dense": 1.0 - float(distance),
                "bm25": None,
            }

        # BM25 关键词召回
        if self._bm25 is not None and self._documents:
            row_scores = np.asarray(self._bm25.get_scores(preprocess_text(query)), dtype=np.float64)
            if source_filter:
                mask = np.array([
                    (meta or {}).get("source") == source_filter
                    for meta in self._metadatas
                ])
                row_scores = np.where(mask, row_scores, -np.inf)
            top_indices = np.argsort(row_scores)[::-1][:n_results]
            for index in top_indices:
                score = float(row_scores[index])
                if not np.isfinite(score):
                    continue
                doc_id = self._ids[index]
                item = candidates.setdefault(
                    doc_id,
                    {
                        "text": self._documents[index],
                        "metadata": self._metadatas[index] or {},
                        "dense": None,
                        "bm25": None,
                    },
                )
                item["bm25"] = score

        if not candidates:
            return []

        dense_values = [item["dense"] if item["dense"] is not None else 0.0 for item in candidates.values()]
        bm25_values = [item["bm25"] if item["bm25"] is not None else 0.0 for item in candidates.values()]
        dense_norm = self._normalize(dense_values)
        bm25_norm = self._normalize(bm25_values)

        # 与原 WeightedRanker(0.7, 1.0) 对齐
        fused_scores = 0.7 * dense_norm + 1.0 * bm25_norm

        ordered = sorted(
            zip(candidates.keys(), candidates.values(), fused_scores),
            key=lambda pair: pair[2],
            reverse=True,
        )

        # 父块去重
        seen = set()
        parent_docs: List[Document] = []
        for doc_id, item, _score in ordered:
            metadata = dict(item["metadata"])
            parent_content = metadata.get("parent_content") or item["text"]
            if not parent_content or parent_content in seen:
                continue
            seen.add(parent_content)
            parent_docs.append(
                Document(
                    page_content=parent_content,
                    metadata={
                        "parent_id": metadata.get("parent_id", ""),
                        "parent_content": parent_content,
                        "source": metadata.get("source", "unknown"),
                        "timestamp": metadata.get("timestamp", "unknown"),
                        "child_id": doc_id,
                    },
                )
            )
            if len(parent_docs) >= max(k, config.CANDIDATE_M):
                break

        if len(parent_docs) < 2:
            return parent_docs[:config.CANDIDATE_M]

        if self._reranker is None:
            self._reranker = get_reranker_model()
        pairs = [[query, doc.page_content] for doc in parent_docs]
        scores = self._reranker.predict(pairs)
        ranked = [doc for _score, doc in sorted(zip(scores, parent_docs), key=lambda pair: pair[0], reverse=True)]
        logger.info("Chroma 混合检索完成：召回 %d 个子块，父块 %d 个", len(candidates), len(ranked))
        return ranked[:config.CANDIDATE_M]

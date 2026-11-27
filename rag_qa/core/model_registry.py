"""本地模型单例。

BGE-M3、BGE-Reranker、BERT 分类器都只加载一次。原实现里
RAGSystem 与 StrategySelector 各建一个 VectorStore，导致模型重复加载；
这里统一由注册表提供，向量库与问答链路共享。
"""
from __future__ import annotations

import threading

from base import paths
from base.logger import logger

_embedding_model = None
_reranker_model = None
_query_classifier = None
_lock = threading.Lock()


def get_embedding_model():
    global _embedding_model
    if _embedding_model is not None:
        return _embedding_model
    with _lock:
        if _embedding_model is None:
            from milvus_model.hybrid import BGEM3EmbeddingFunction

            model_path = str(paths.MODELS_DIR / "bge-m3")
            logger.info("加载 BGE-M3 混合嵌入模型：%s", model_path)
            _embedding_model = BGEM3EmbeddingFunction(
                model_name_or_path=model_path,
                device="cpu",
                use_fp16=False,
            )
            logger.info("BGE-M3 混合嵌入模型初始化完成")
    return _embedding_model


def _reranker_path():
    base = paths.MODELS_DIR / "bge-reranker-base"
    large = paths.MODELS_DIR / "bge-reranker-large"
    if base.is_dir():
        return base
    if large.is_dir():
        logger.warning("未找到 bge-reranker-base，回退到 bge-reranker-large")
        return large
    return base


def get_reranker_model():
    global _reranker_model
    if _reranker_model is not None:
        return _reranker_model
    with _lock:
        if _reranker_model is None:
            from sentence_transformers import CrossEncoder

            model_path = str(_reranker_path())
            logger.info("加载 BGE-Reranker：%s", model_path)
            _reranker_model = CrossEncoder(model_path, device="cpu")
            logger.info("BGE-Reranker 初始化完成")
    return _reranker_model


def get_query_classifier():
    global _query_classifier
    if _query_classifier is not None:
        return _query_classifier
    with _lock:
        if _query_classifier is None:
            from rag_qa.core.query_classifier import QueryClassifier

            _query_classifier = QueryClassifier()
            logger.info("问题分类模型加载完成")
    return _query_classifier


def warmup_models() -> None:
    """启动时预加载，避免第一次提问等待过久。"""
    get_embedding_model()
    get_reranker_model()
    get_query_classifier()


def reset_model_registry() -> None:
    global _embedding_model, _reranker_model, _query_classifier
    with _lock:
        _embedding_model = None
        _reranker_model = None
        _query_classifier = None

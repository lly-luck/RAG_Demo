from rank_bm25 import BM25Okapi
import numpy as np

from base.logger import logger
from mysql_qa.util.doc_preprocess import preprocess_text
from storage.cache.factory import get_cache_client
from storage.db.factory import get_db_client


class BM25Search:
    def __init__(self, db_client=None, cache_client=None):
        # 允许注入，便于测试与共享单例；默认从工厂取
        self.db_client = db_client or get_db_client()
        self.cache_client = cache_client or get_cache_client()

        self.bm25 = None
        self.original_questions = None
        self.tokenized_questions = None
        self._load()

    def _load(self):
        """初始化 BM25 检索模型（问题列表优先从缓存读取）。"""
        original_key = "qa_original_questions"
        tokenized_key = "qa_tokenized_questions"

        self.original_questions = self.cache_client.get_data(original_key)
        self.tokenized_questions = self.cache_client.get_data(tokenized_key)

        if not self.original_questions or not self.tokenized_questions:
            self.original_questions = self.db_client.fetch_questions()
            self.tokenized_questions = [preprocess_text(q) for q in self.original_questions]
            self.cache_client.set_data(original_key, self.original_questions)
            self.cache_client.set_data(tokenized_key, self.tokenized_questions)

        if self.original_questions and self.tokenized_questions:
            self.bm25 = BM25Okapi(self.tokenized_questions)
            logger.info("BM25 检索模型初始化成功，问题数：%d", len(self.original_questions))
        else:
            self.bm25 = None
            logger.warning("FAQ 问题列表为空，FAQ 通道将回退到 RAG")

    def search(self, query, threshold=0.85):
        """
        BM25 检索查询。
        :return: (answer:str|None, need_llm:bool)
        """
        # 1. 精确答案缓存
        answer = self.cache_client.get_answer(query)
        if answer:
            return answer, False

        if self.bm25 is None:
            return None, True

        # 2. 分词 + BM25 打分
        query_token = preprocess_text(query)
        row_scores = self.bm25.get_scores(query_token)
        softmax_scores = self._softmax(row_scores)

        best_score = float(np.nanmax(softmax_scores))
        best_idx = int(np.argmax(softmax_scores))

        # 3. 阈值判断
        if best_score < threshold:
            logger.info("FAQ匹配失败，置信阈值%.3f", best_score)
            return None, True

        original_question = self.original_questions[best_idx]
        cache_answer = self.cache_client.get_answer(original_question)
        if cache_answer:
            logger.info("缓存命中问题：%s", original_question)
            answer = cache_answer
        else:
            answer = self.db_client.fetch_answer(original_question)
            logger.info("数据库命中问题：%s", original_question)
            if answer is not None:
                self.cache_client.set_data(f"answer:{original_question}", answer)

        logger.info("FAQ匹配成功，置信阈值%.3f", best_score)
        return answer, False

    @staticmethod
    def _softmax(scores):
        """把 BM25 无界分值归一化到 0~1。"""
        scores = np.asarray(scores, dtype=np.float64)
        if scores.size == 0:
            return scores
        shifted = scores - np.max(scores)
        exp_scores = np.exp(shifted)
        total = exp_scores.sum()
        if total == 0:
            return np.zeros_like(scores)
        return exp_scores / total


if __name__ == "__main__":
    bm25 = BM25Search()
    answer, need_llm = bm25.search("熵的含义")
    if answer:
        print(f"FAQ答案：{answer}")
    if need_llm:
        print("FAQ没有结果，需要执行LLM的RAG")

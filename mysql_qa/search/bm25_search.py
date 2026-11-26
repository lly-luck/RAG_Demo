from rank_bm25 import BM25Okapi

from base.logger import logger
from mysql_qa.cache.redis_client import RedisClient
from mysql_qa.db.mysql_client import MySQLClient
from mysql_qa.util.doc_preprocess import preprocess_text
import numpy as np


class BM25Search:
    def __init__(self):
        # 创建 MySQL、Redis客户端连接对象
        self.redis_client = RedisClient()
        self.mysql_client = MySQLClient()
        # 声明BM25全局变量
        self.bm25=None
        # 声明原始问题列表（用于查询问题答案）
        self.original_questions = None
        # 声明分词后问题列表（提供给BM25计算相似度）
        self.tokenized_questions=None
        # 初始化BM25检索模型
        self._load()

    def _load(self):
        """私有的初始化BM25检索模型"""
        # 1.读取redis中原始问题、分词问题
        original_key = "qa_original_questions"
        tokenized_key = "qa_tokenized_questions"
        self.original_questions = self.redis_client.get_data(original_key)
        self.tokenized_questions = self.redis_client.get_data(tokenized_key)
        # 2.如果缓存中没有，从mysql中查询，并分词处理
        if not self.original_questions or not self.tokenized_questions:
            # 查询mysql原始问题
            self.original_questions = self.mysql_client.fetch_questions()
            # 对原始问题进行分词处理
            self.tokenized_questions = [preprocess_text(q) for q in self.original_questions]
            # 3.将原始问题和分词问题存入redis中
            self.redis_client.set_data(original_key, self.original_questions)
            self.redis_client.set_data(tokenized_key, self.tokenized_questions)
        # 4.初始化 BM25 检索模型
        self.bm25 = BM25Okapi(self.tokenized_questions)
        logger.info("BM25 检索模型初始化成功")

    def search(self, query, threshold=0.85):
        """
        BM25检索查询的方法
        :param query:  用户问题
        :param threshold:  归一化后的阈值
        :return: (answer:str,need_llm:bool)
        """
        # 1.redis问题的精准匹配查询
        answer = self.redis_client.get_answer(query)
        if answer:
            return answer, False
        # 2.用户问题进行分词，BM25进行检索
        query_token = preprocess_text(query)
        row_scores = self.bm25.get_scores(query_token)
        # 归一化处理的分数
        softmax_scores = self._softmax(row_scores)
        # 3.查询最高分，索引
        best_score = np.nanmax(softmax_scores)
        best_idx = np.argmax(softmax_scores)

        # 4.最高分对比阈值
        # 分数<阈值，匹配失败，使用LLM
        if best_score < threshold:
            logger.info(f"FAQ匹配失败，置信阈值{best_score:.3f}")
            return None, True

        # 分数>阈值，拿到原始问题
        original_question = self.original_questions[best_idx]
        # 查询缓存
        cache_answer = self.redis_client.get_answer(original_question)
        if cache_answer:
            logger.info(f"Redis缓存命中问题：{original_question}")
            answer = cache_answer
        else:
            # 查询mysql数据库
            answer = self.mysql_client.fetch_answer(original_question)
            logger.info(f"MySQL命中问题：{original_question}")
            # 同步到缓存
            self.redis_client.set_data(f"answer:{original_question}", answer);
        logger.info(f"FAQ匹配成功，置信阈值{best_score:.3f}")
        return answer, False

    def _softmax(self, scores):
        """
        私有归一化函数：将BM25无界原始分值转为0~1概率
        :param scores: BM25输出原始相关性分数列表
        :return: 归一化概率数组，数值越大匹配度越高
        """
        temperature = 1
        scores = np.array(scores) / temperature
        exp_scores = np.exp(scores - np.max(scores))
        return exp_scores / exp_scores.sum()


if __name__ == '__main__':
    bm25 = BM25Search()
    answer,need_llm =bm25.search("熵的含义")
    if answer:
        print(f"FAQ答案：{answer}")
    if need_llm:
        print("FAQ没有结果，需要执行LLM的RAG")
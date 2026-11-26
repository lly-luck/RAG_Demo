"""
RAG 检索策略选择核心模块
功能：
1. 动态选择检索策略：直接检索 / 子查询拆分 / 假设问题检索（HyDE）
2. 根据问题复杂度自动路由最优检索方式
3. 去重、排序、输出最终上下文
"""
from langchain_core.output_parsers import StrOutputParser

from base.logger import logger
from langchain.chat_models import init_chat_model

from base.config import config as conf
from rag_qa.core.prompts import RAGPrompts
from rag_qa.core.vector_store import VectorStore

class StrategySelector:
    """智能检索策略选择器"""

    def __init__(self):
        # 1. 初始化大模型
        self.llm = init_chat_model(
            model=conf.LLM_MODEL,
            temperature=0.3,
            api_key=conf.LLM_API_KEY,
            base_url=conf.LLM_BASE_URL
        )

        # 2. 初始化向量存储
        self.vector_store = VectorStore()
        logger.info("检索策略引擎初始化完成")

    def strategy_select(self, query, source_filter=None):
        """
        核心入口：根据用户问题自动选择最优检索策略
        :param query: 用户原始问题
        :param source_filter: 技术方向过滤
        :return: 最优排序后的文档列表
        """
        # 调用llm选择策略
        strategy_prompt = RAGPrompts.strategy_select_prompt().format(query=query)
        # chain = strategy_prompt | self.llm | StrOutputParser()
        strategy_content = self._call_llm(strategy_prompt)
        logger.info(f"选择策略-》{strategy_content}, 问题-》{query}")

        # 执行策略
        if strategy_content == "子查询检索":
            ranked_docs = self._retrieve_with_subqueries(query, source_filter)
        elif strategy_content == "假设问题检索":
            ranked_docs = self._retrieve_with_hyde(query, source_filter)
        else: # 直接检索
            logger.info(f"执行直接检索，问题：{query}")
            ranked_docs = self.vector_store.hybrid_search_with_reranker(query, source_filter = source_filter)
        # 最终返回的结果
        final_docs = ranked_docs[:conf.CANDIDATE_M]
        logger.info(f"策略执行完成，最终返回了{len(final_docs)}条结果")
        return final_docs



    def _retrieve_with_hyde(self, query, source_filter):
        """
        HyDE 假设答案检索策略
        先生成假设答案 → 用答案向量检索 → 语义更匹配
        """
        logger.info(f"执行 HyDE 假设答案检索：{query}")
        try:
            # 生成假设答案
            hyde_prompt = RAGPrompts.hyde_prompt().format(query=query)
            hypo_answer = self._call_llm(hyde_prompt).strip()
            logger.info(f"HyDE 生成答案：{hypo_answer[:100]}...")

            # 使用假设答案检索
            return self.vector_store.hybrid_search_with_reranker(
                query=hypo_answer,
                source_filter=source_filter
            )
        except Exception as e:
            logger.error(f"HyDE 策略执行失败：{str(e)}")
            return []

    def _retrieve_with_subqueries(self, query, source_filter=None):
        """
        子查询拆分策略
        复杂问题 → 拆成 N 个小问题 → 分别检索 → 去重合并
        """
        logger.info(f"执行 子查询拆分检索：{query}")
        try:
            # 生成子问题
            subquery_prompt = RAGPrompts.subquery_prompt().format(query=query)
            subqueries_text = self._call_llm(subquery_prompt).strip()
            subqueries = [q.strip() for q in subqueries_text.split("\n") if q.strip()]

            if not subqueries:
                logger.warning("子查询生成为空，返回空列表")
                return []

            logger.info(f"拆分后子问题：{subqueries}")

            # 批量检索
            all_docs = []
            for sub_q in subqueries:
                docs = self.vector_store.hybrid_search_with_reranker(
                    query=sub_q,
                    source_filter=source_filter
                )
                all_docs.extend(docs)
                logger.info(f"子问题 [{sub_q}] 召回 {len(docs)} 条")

            # 文本去重
            unique_dict = {doc.page_content: doc for doc in all_docs}
            unique_docs = list(unique_dict.values())

            logger.info(f"合并去重后：{len(unique_docs)} 条")
            return unique_docs
        except Exception as e:
            logger.error(f"子查询策略失败：{str(e)}")
            return []

    def _call_llm(self, prompt):
        """
        统一 LLM 调用接口
        简化格式、稳定返回、异常兜底
        """
        try:
            response = self.llm.invoke(prompt)
            return response.content.strip()
        except Exception as e:
            logger.error(f"LLM 调用异常：{str(e)}")
            return "直接检索"

if __name__ == '__main__':
    ss = StrategySelector()
    query1 = "Spring Boot 自动配置的原理是什么"
    query2 = "Redis 和 MySQL 的区别是什么"
    query3 = "大模型在智能客服中有哪些应用"
    docs = ss.strategy_select(query1)
    print(docs)














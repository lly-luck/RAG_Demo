"""
RAG 检索策略选择核心模块
功能：
1. 动态选择检索策略：直接检索 / 子查询拆分 / 假设问题检索（HyDE）
2. 根据问题复杂度自动路由最优检索方式
3. 去重、排序、输出最终上下文
"""

from base.config import config
from base.llm_factory import LLMNotConfigured, get_llm_factory
from base.logger import logger
from rag_qa.core.prompts import RAGPrompts
from rag_qa.core.vector_factory import get_vector_store


class StrategySelector:
    """智能检索策略选择器"""

    def __init__(self, vector_store=None, llm_factory=None):
        # LLM 按需获取；未配置时自动降级为直接检索
        self.llm_factory = llm_factory or get_llm_factory()
        self.vector_store = vector_store or get_vector_store()
        logger.info("检索策略引擎初始化完成")

    def strategy_select(self, query, source_filter=None):
        """
        核心入口：根据用户问题自动选择最优检索策略
        :param query: 用户原始问题
        :param source_filter: 技术方向过滤
        :return: 最优排序后的文档列表
        """
        strategy_prompt = RAGPrompts.strategy_select_prompt().format(query=query)
        strategy_content = self._call_llm(strategy_prompt)
        logger.info("选择策略-》%s, 问题-》%s", strategy_content, query)

        if strategy_content == "子查询检索":
            ranked_docs = self._retrieve_with_subqueries(query, source_filter)
        elif strategy_content == "假设问题检索":
            ranked_docs = self._retrieve_with_hyde(query, source_filter)
        else:  # 直接检索
            logger.info("执行直接检索，问题：%s", query)
            ranked_docs = self.vector_store.hybrid_search_with_reranker(
                query, source_filter=source_filter
            )

        final_docs = ranked_docs[:config.CANDIDATE_M]
        logger.info("策略执行完成，最终返回了%d条结果", len(final_docs))
        return final_docs

    def _retrieve_with_hyde(self, query, source_filter):
        """
        HyDE 假设答案检索策略：先生成假设答案，再用答案向量检索。
        """
        logger.info("执行 HyDE 假设答案检索：%s", query)
        try:
            hyde_prompt = RAGPrompts.hyde_prompt().format(query=query)
            hypo_answer = self._call_llm(hyde_prompt).strip()
            logger.info("HyDE 生成答案：%s...", hypo_answer[:100])
            return self.vector_store.hybrid_search_with_reranker(
                query=hypo_answer,
                source_filter=source_filter,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("HyDE 策略执行失败：%s", exc)
            return []

    def _retrieve_with_subqueries(self, query, source_filter=None):
        """
        子查询拆分策略：拆成 N 个小问题分别检索，再去重合并。
        """
        logger.info("执行 子查询拆分检索：%s", query)
        try:
            subquery_prompt = RAGPrompts.subquery_prompt().format(query=query)
            subqueries_text = self._call_llm(subquery_prompt).strip()
            subqueries = [q.strip() for q in subqueries_text.split("\n") if q.strip()]

            if not subqueries:
                logger.warning("子查询生成为空，返回空列表")
                return []

            logger.info("拆分后子问题：%s", subqueries)

            all_docs = []
            for sub_q in subqueries:
                docs = self.vector_store.hybrid_search_with_reranker(
                    query=sub_q,
                    source_filter=source_filter,
                )
                all_docs.extend(docs)
                logger.info("子问题 [%s] 召回 %d 条", sub_q, len(docs))

            unique_dict = {doc.page_content: doc for doc in all_docs}
            unique_docs = list(unique_dict.values())
            logger.info("合并去重后：%d 条", len(unique_docs))
            return unique_docs
        except Exception as exc:  # noqa: BLE001
            logger.error("子查询策略失败：%s", exc)
            return []

    def _call_llm(self, prompt):
        """统一 LLM 调用；未配置 Key 时降级为直接检索。"""
        try:
            response = self.llm_factory.get(temperature=0.3).invoke(prompt)
            return response.content.strip()
        except LLMNotConfigured:
            logger.info("LLM 未配置，策略选择降级为直接检索")
            return "直接检索"
        except Exception as exc:  # noqa: BLE001
            logger.error("LLM 调用异常：%s", exc)
            return "直接检索"


if __name__ == "__main__":
    ss = StrategySelector()
    docs = ss.strategy_select("Spring Boot 自动配置的原理是什么")
    print(docs)

"""
RAG 智能问答主系统
功能：
1. 问题分类（通用知识 / 专业咨询）
2. 专业问题 → 向量库检索 + 重排序
3. 通用问题 → 直接回答
"""

from base.config import config
from base.llm_factory import LLMNotConfigured, get_llm_factory
from base.logger import logger
from rag_qa.core.model_registry import get_query_classifier
from rag_qa.core.prompts import RAGPrompts
from rag_qa.core.strategy_selector import StrategySelector
from rag_qa.core.vector_factory import get_vector_store


class RAGSystem:
    """RAG 问答系统核心类"""

    def __init__(self, vector_store=None, llm_factory=None):
        logger.info("初始化 RAG 智能问答系统...")

        # 1. 问题分类器（共享单例）
        self.classifier = get_query_classifier()
        logger.info("问题分类器加载完成")

        # 2. 向量存储（embedded=Chroma / external=Milvus，共享单例）
        self.vector_store = vector_store or get_vector_store()
        logger.info("向量检索引擎加载完成")

        # 3. LLM 按需创建（允许启动时尚未配置 Key）
        self.llm_factory = llm_factory or get_llm_factory()

        # 4. 检索策略（注入同一个 vector_store，避免模型重复加载）
        self.ss = StrategySelector(
            vector_store=self.vector_store,
            llm_factory=self.llm_factory,
        )

    async def generate_answer(self, query, source_filter=None, history=None):
        """
        根据用户问题生成最终答案（核心入口）
        :param query: 用户问题
        :param source_filter: 技术方向过滤（可选）
        :param history: 对话历史
        :return: 最终回答（异步生成器）
        """
        if not query or not query.strip():
            yield "请输入有效的问题"
            return

        # 问题分类
        query_category = self.classifier.predict_category(query.strip())
        logger.info("问题：%s，分类：%s", query, query_category)

        history = history or []
        history_content = "\n".join(
            f"Q:{item.get('question', '')}\nA:{item.get('answer', '')}\n"
            for item in history
        )

        # 构建提示词
        if query_category == "通用知识":
            prompt = RAGPrompts.rag_prompt().format(
                context="通用知识",
                history=history_content,
                question=query,
                phone=config.CUSTOMER_SERVICE_PHONE,
            )
        else:
            logger.info("开始进行混合检索(RAG...)")
            try:
                documents = self.ss.strategy_select(query, source_filter)
            except Exception as exc:  # noqa: BLE001
                logger.exception("检索失败，降级为空上下文：%s", exc)
                documents = []
            if documents:
                context = "\n".join(doc.page_content for doc in documents)
            else:
                context = "未找到相关专业知识"
            prompt = RAGPrompts.rag_prompt().format(
                context=context,
                history=history_content,
                question=query,
                phone=config.CUSTOMER_SERVICE_PHONE,
            )
            logger.info("最终发给大模型的提示词：%s......", prompt[:100])

        # 调用大模型（流式）
        try:
            llm = self.llm_factory.get(temperature=0.1)
        except LLMNotConfigured:
            logger.warning("LLM 未配置，返回设置引导")
            yield "尚未配置大模型，请点击页面右上角的“设置”按钮，填写 Base URL、模型名和 API Key 后重试。"
            return

        try:
            async for chunk in llm.astream(prompt):
                if chunk.content:
                    yield chunk.content
        except Exception as exc:  # noqa: BLE001
            logger.error("大模型调用失败：%s", exc)
            yield f"抱歉，服务暂时出现问题，请联系人工客服：{config.CUSTOMER_SERVICE_PHONE}"


if __name__ == "__main__":
    import asyncio

    rag_system = RAGSystem()

    async def main():
        while True:
            print()
            query = input("请输入问题：")
            if query == "exit":
                break
            async for item in rag_system.generate_answer(query=query, source_filter="ai"):
                print(item, end="", flush=True)

    asyncio.run(main())

"""
RAG 智能问答主系统
功能：
1. 问题分类（通用知识 / 专业咨询）
2. 专业问题 → 向量库检索 + 重排序
3. 通用问题 → 直接回答
"""

from langchain.chat_models import init_chat_model
from base.config import config
from base.logger import logger
from rag_qa.core.prompts import RAGPrompts
from rag_qa.core.query_classifier import QueryClassifier
from rag_qa.core.vector_store import VectorStore
from rag_qa.core.strategy_selector import StrategySelector


class RAGSystem:
    """RAG 问答系统核心类"""

    def __init__(self):
        logger.info("初始化 RAG 智能问答系统...")

        # 1. 初始化问题分类器（BERT 微调模型）
        self.classifier = QueryClassifier()
        logger.info("问题分类器加载完成")

        # 2. 初始化向量存储（Milvus + BGE-M3 + Reranker）
        self.vector_store = VectorStore()
        logger.info("向量检索引擎加载完成")

        # 3. 初始化大模型
        self.llm = init_chat_model(
            model=config.LLM_MODEL,
            temperature=0.1,  # 低温度，保证答案专业、稳定
            api_key=config.LLM_API_KEY,
            base_url=config.LLM_BASE_URL
        )
        logger.info("大模型初始化完成")

        # 初始化对象
        self.ss = StrategySelector()

    async def generate_answer(self, query, source_filter=None, history = None):
        """
        根据用户问题生成最终答案（核心入口）
        :param query: 用户问题
        :param source_filter: 技术方向过滤（可选）
        :param history: 对话历史
        :return: 最终回答
        """
        # 校验用户的query
        if not query or len(query) == 0 :
            # return "请输入有效的问题"
            yield "请输入有效的问题"
        #  问题分类
        query_category = self.classifier.predict_category(query.strip())
        logger.info(f"问题：{query}，分类：{query_category}")

        # 处理对话历史history
        if not (
                history):
            history=[]
        history_content = "\n".join(f"Q:{dict['question']} \nA {dict['answer']}\n" for dict in history)

        # 构建提示词
        if query_category == "通用知识":
            prompt = RAGPrompts.rag_prompt().format(context="通用知识",
                                                    history=history_content,
                                                    question=query,
                                                    phone=config.CUSTOMER_SERVICE_PHONE
                                                    )
        else:
            logger.info("开始进行混合检索(RAG...)")
            # 混合检索
            documents = self.ss.strategy_select(query, source_filter)
            if documents:
                # 存在， 拼接context
                context = "\n".join(doc.page_content for doc in documents)
            else:
                # 不存在，指定context
                context = "未找到相关专业知识"
            # 拼接rag的prompt
            prompt = RAGPrompts.rag_prompt().format(context=context,
                                                    history=history_content,
                                                    question=query,
                                                    phone=config.CUSTOMER_SERVICE_PHONE
                                                    )
            logger.info(f"最终发给大模型的提示词：{prompt[:100]}......")

        # 调用大模型
        try:
            # 非流式输出
            # answer = self.llm.invoke(prompt).content.strip()
            # logger.info("llm成功生成答案")
            # return answer
            # 流式输出
            model_stream = self.llm.astream(prompt)
            async for chunk in model_stream:
                if chunk.content:
                    yield chunk.content
        except Exception as e:
            logger.error(f"大模型调用失败：{e}")
            yield f"抱歉，服务暂时出现问题，请联系人工客服：{config.CUSTOMER_SERVICE_PHONE}"


if __name__ == "__main__":
    import asyncio

    rag_system = RAGSystem()

    # # 测试专业问题
    # test_query = "Spring Boot 自动配置的原理是什么"
    # # test_query = "你好"
    # query1 = "Spring Boot 自动配置的原理是什么"
    # query2 = "Redis 和 MySQL 的区别是什么"
    # query3 = "大模型在智能客服中有哪些应用"
    # final_answer = rag_system.generate_answer(query=query3, source_filter="java")
    #
    # print(f"用户问题：{test_query}")
    # print("=" * 80)
    # print(f"系统回答：\n{final_answer}")
    async def main():
        while True:
            print()
            query = input("请输入问题：")
            if query == "exit":
                break
            async for item in rag_system.generate_answer(query=query, source_filter="java"):
                print(item, end="", flush=True)

    asyncio.run(main())













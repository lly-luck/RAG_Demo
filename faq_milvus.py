"""FAQ + RAG 双层集成问答系统"""
from base.logger import logger
from mysql_qa.db.mysql_client import MySQLClient
from mysql_qa.search.bm25_search import BM25Search
from rag_qa.core.rag_system import RAGSystem
from base.config import config
import time

class IntegratedQASystem:
    def __init__(self):
        self.bm25_search = BM25Search()
        self.rag_system = RAGSystem()
        self.mysql_client = MySQLClient()
        logger.info("集成问答系统初始化完成")

    async def search(self, query, scores_filter=None, session_id=None):
        """
        FAQ+RAG
        :param query: 用户提问
        :param scores_filter: 技术方向过滤
        :param session_id: 会话id
        :return:
        """
        # 查询
        faq_ans, need_llm = self.bm25_search.search(query)
        if faq_ans:
            # 将本轮的对话存入MySQL中
            if session_id:
                self.mysql_client.update_session_history(session_id, query, faq_ans)
            logger.info("FAQ命中...")
            # 模拟流式输出
            for char in faq_ans:
                time.sleep(0.01)
                yield char, False
            yield "", True # 生成结束
            return
        if need_llm:
            logger.info("执行RAG")
            # 查询对话历史
            history = self.mysql_client.fetch_recent_history(session_id)

            stream = self.rag_system.generate_answer(query, scores_filter, history)
            rag_answer = ""
            async for chunk in stream:
                rag_answer += chunk
                yield chunk, False
            # 将本轮的对话存入MySQL中
            if session_id:
                self.mysql_client.update_session_history(session_id, query, rag_answer)

            yield "", True # 生成结束
            return
        yield f"未找到相关答案，请联系人工客服：{config.CUSTOMER_SERVICE_PHONE}"


if __name__ == "__main__":
    import asyncio
    qa = IntegratedQASystem()
    print("-------------系统启动 | exit退出--------------")

    async def main():
        while True:
            query = input("请输入问题：")
            if query == "exit":
                break
            subj = input("请输入技术方向（可选）：") or None
            gen = qa.search(query, subj, "123")
            async for chunk, is_end in gen:
                print(chunk, end="", flush=True)
                if is_end:  # 模拟前端
                    continue
            print("\n" + "-" * 50)

    asyncio.run(main())

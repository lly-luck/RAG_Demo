"""FAQ + RAG 双层集成问答系统"""
import asyncio

from base.config import config
from base.logger import logger
from mysql_qa.search.bm25_search import BM25Search
from rag_qa.core.rag_system import RAGSystem
from storage.cache.factory import get_cache_client
from storage.db.factory import get_db_client


class IntegratedQASystem:
    def __init__(self, db_client=None, cache_client=None, vector_store=None):
        self.db_client = db_client or get_db_client()
        self.cache_client = cache_client or get_cache_client()
        self.bm25_search = BM25Search(
            db_client=self.db_client,
            cache_client=self.cache_client,
        )
        self.rag_system = RAGSystem(vector_store=vector_store)
        logger.info("集成问答系统初始化完成")

    async def search(self, query, scores_filter=None, session_id=None):
        """
        FAQ + RAG。
        :param query: 用户提问
        :param scores_filter: 技术方向过滤
        :param session_id: 会话 id
        """
        faq_ans, need_llm = self.bm25_search.search(query)
        if faq_ans:
            if session_id:
                self.db_client.update_session_history(session_id, query, faq_ans)
            logger.info("FAQ命中...")
            # 模拟流式输出：按小块推送，避免长答案逐字等待过久
            chunk_size = 8
            for start in range(0, len(faq_ans), chunk_size):
                yield faq_ans[start:start + chunk_size], False
                await asyncio.sleep(0.01)
            yield "", True
            return

        if need_llm:
            logger.info("执行RAG")
            history = self.db_client.fetch_recent_history(session_id) if session_id else []

            stream = self.rag_system.generate_answer(query, scores_filter, history)
            rag_answer = ""
            async for chunk in stream:
                rag_answer += chunk
                yield chunk, False

            if session_id and rag_answer:
                self.db_client.update_session_history(session_id, query, rag_answer)

            yield "", True
            return

        # 理论上不会到这里；保持与 app.py 的 (token, is_complete) 协议一致
        yield f"未找到相关答案，请联系人工客服：{config.CUSTOMER_SERVICE_PHONE}", False
        yield "", True


if __name__ == "__main__":
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
                if is_end:
                    continue
            print("\n" + "-" * 50)

    asyncio.run(main())

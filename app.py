# Web 框架核心
import json
import re
import time
import uuid
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.websockets import WebSocketDisconnect, WebSocketState

# 业务层依赖
from base import paths
from base.config import config
from base.llm_factory import get_llm_factory
from base.logger import logger
from base.settings_store import get_settings_store
from faq_milvus import IntegratedQASystem
from storage.db.factory import get_db_client


# 应用实例化
app = FastAPI(title="问答系统API", description="集成FAQ和RAG的智能问答系统")

# 跨域配置：仅本地演示使用，不携带凭证
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 首次启动：准备用户数据目录并复制预构建种子
_seed_result = paths.ensure_user_data()
if _seed_result["missing"]:
    logger.warning("缺少预构建种子：%s", ", ".join(_seed_result["missing"]))

# 实例初始化（会加载 BERT 分类器、BGE-M3，并连接配置的存储后端）
qa_system = IntegratedQASystem()
db_client = get_db_client()
settings_store = get_settings_store()
llm_factory = get_llm_factory()

# 预加载 reranker，避免首次提问等待；external Milvus 实现中为空操作
try:
    qa_system.rag_system.vector_store.warmup()
except Exception as exc:  # noqa: BLE001
    logger.warning("向量模型预热失败（首次查询时重试）：%s", exc)


GREETING_PATTERNS = [
    {
        "pattern": r"^(你好|您好|hi|hello)",
        "response": "你好！我是智能问答助手，专注于解答 AI、Java、Python 等技术问题，很高兴为你服务！"
    },
    {
        "pattern": r"^(你是谁|您是谁|你叫什么|你的名字|who are you)",
        "response": "我是智能问答助手，基于 RAG 检索增强生成，可以为你解答 AI、Java、Python 等技术问题！"
    },
    {
        "pattern": r"^(在吗|在不在|有人吗)",
        "response": "我在！我是智能问答助手，随时为你解答问题！"
    },
    {
        "pattern": r"^(干嘛呢|你在干嘛|做什么)",
        "response": "我正在待命，随时为你解答技术相关的问题！有什么我可以帮你的？"
    },
]


def check_greeting(query: str) -> Optional[str]:
    query_text = query.strip()
    for pattern_info in GREETING_PATTERNS:
        if re.match(pattern_info["pattern"], query_text, re.IGNORECASE):
            return pattern_info["response"]
    return None


class SettingsPayload(BaseModel):
    base_url: str
    model: str
    api_key: Optional[str] = None


# ============================ 会话接口 ============================
@app.post("/api/create_session")
async def create_session():
    session_id = str(uuid.uuid4())
    return {"session_id": session_id}


@app.get("/api/history/{session_id}")
async def get_history(session_id: str):
    try:
        history = db_client.fetch_recent_history(session_id)
        total_count = db_client.get_session_count(session_id)
        return {
            "session_id": session_id,
            "history": history,
            "total_count": total_count,
        }
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"获取历史记录失败: {exc}")


@app.get("/api/session_count/{session_id}")
async def get_session_count(session_id: str):
    try:
        total_count = db_client.get_session_count(session_id)
        return {"session_id": session_id, "total_count": total_count}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"获取会话数失败: {exc}")


@app.get("/api/sessions")
async def get_all_sessions():
    try:
        sessions = db_client.fetch_all_sessions()
        return {"sessions": sessions, "total": len(sessions)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"获取会话列表失败: {exc}")


@app.delete("/api/history")
async def clear_all_history():
    try:
        success = db_client.clear_all_sessions_history()
        if success:
            return {"status": "success", "message": "所有历史记录已清除"}
        raise HTTPException(status_code=500, detail="清除历史记录失败")
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"清除历史记录失败: {exc}")


# ============================ 设置接口 ============================
@app.get("/api/settings")
async def get_settings():
    return settings_store.public_dict()


@app.post("/api/settings")
async def save_settings(payload: SettingsPayload):
    try:
        settings_store.save_llm(payload.base_url, payload.model, payload.api_key)
        if not settings_store.get_llm().configured:
            raise HTTPException(status_code=400, detail="请填写有效的 API Key")
        llm_factory.reload()
        return {"ok": True, "settings": settings_store.public_dict()}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/settings/test")
async def test_settings(payload: SettingsPayload):
    result = await llm_factory.test_connection(
        base_url=payload.base_url,
        model=payload.model,
        api_key=payload.api_key,
    )
    return result


# ============================ WebSocket 流式问答 ============================
@app.websocket("/api/stream")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            request_data = json.loads(data)
            query = request_data.get("query")
            source_filter = request_data.get("source_filter")
            session_id = request_data.get("session_id", str(uuid.uuid4()))
            start_time = time.time()

            if not query or not query.strip():
                await websocket.send_json({"type": "error", "error": "查询内容不能为空"})
                continue

            # 只允许配置中的技术方向，防止任意过滤值
            if source_filter and source_filter not in config.VALID_SOURCES:
                source_filter = None

            await websocket.send_json({"type": "start", "session_id": session_id})

            # 分支 1：问候语
            greeting_response = check_greeting(query)
            if greeting_response:
                db_client.update_session_history(session_id, query, greeting_response)
                for char in greeting_response:
                    await websocket.send_json({
                        "type": "token",
                        "token": char,
                        "session_id": session_id,
                    })
                await websocket.send_json({
                    "type": "end",
                    "session_id": session_id,
                    "is_complete": True,
                    "processing_time": time.time() - start_time,
                })
                continue

            # 分支 2：FAQ / RAG
            try:
                async for token, is_complete in qa_system.search(
                    query,
                    scores_filter=source_filter,
                    session_id=session_id,
                ):
                    await websocket.send_json({
                        "type": "token",
                        "token": token,
                        "session_id": session_id,
                    })
                    if is_complete:
                        await websocket.send_json({
                            "type": "end",
                            "session_id": session_id,
                            "is_complete": True,
                            "processing_time": time.time() - start_time,
                        })
                        break
            except Exception as query_error:  # noqa: BLE001
                logger.exception("查询处理失败")
                await websocket.send_json({
                    "type": "error",
                    "error": f"查询处理失败: {query_error}",
                })
                break
    except WebSocketDisconnect as exc:
        logger.info("WebSocket disconnected: code=%s, reason=%s", exc.code, exc.reason)
    except Exception as exc:  # noqa: BLE001
        logger.exception("WebSocket error")
        try:
            await websocket.send_json({"type": "error", "error": str(exc)})
        except Exception:
            pass
    finally:
        # 连接已被客户端关闭时不再重复 close，避免 ASGI 警告
        if websocket.client_state != WebSocketState.DISCONNECTED:
            try:
                await websocket.close()
            except Exception:
                pass


# ============================ 健康检查 / 静态资源 ============================
@app.get("/health")
async def health_check():
    vector_count = None
    try:
        vector_count = qa_system.rag_system.vector_store.count()
    except Exception:
        vector_count = None
    return {
        "status": "healthy",
        "ready": True,
        "storage_backend": config.STORAGE_BACKEND,
        "llm_configured": settings_store.is_configured(),
        "vector_count": vector_count,
    }


@app.get("/api/sources")
async def get_sources():
    return {"sources": config.VALID_SOURCES}


app.mount("/static", StaticFiles(directory=str(paths.STATIC_DIR)), name="static")


@app.get("/")
async def read_root():
    return FileResponse(
        str(paths.STATIC_DIR / "index.html"),
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=config.SERVER_HOST, port=config.SERVER_PORT, reload=False)

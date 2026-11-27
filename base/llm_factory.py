"""LLM 客户端工厂。

统一使用 OpenAI 兼容协议（ChatOpenAI），从而兼容 DeepSeek、通义、智谱、
OpenAI 以及本地 Ollama 的 /v1 接口。配置来自可写的 SettingsStore，
保存设置后调用 reload() 即可生效。
"""
from __future__ import annotations

import asyncio
import time
from typing import Optional

from base.logger import logger
from base.settings_store import LLMSettings, get_settings_store


class LLMNotConfigured(RuntimeError):
    """尚未配置可用的 LLM（引导前端打开设置）。"""


class LLMFactory:
    def __init__(self, settings_store=None):
        self.settings_store = settings_store or get_settings_store()
        self._cache: dict[tuple, object] = {}

    def reload(self) -> None:
        self._cache.clear()
        logger.info("LLM 配置已重新加载")

    def get(self, temperature: float = 0.1):
        settings = self.settings_store.get_llm()
        if not settings.configured:
            raise LLMNotConfigured("尚未配置大模型，请先在设置中填写 Base URL、模型名和 API Key")

        cache_key = (settings.base_url, settings.model, settings.api_key, temperature)
        llm = self._cache.get(cache_key)
        if llm is None:
            from langchain_openai import ChatOpenAI

            llm = ChatOpenAI(
                model=settings.model,
                api_key=settings.api_key,
                base_url=settings.base_url,
                temperature=temperature,
                timeout=60,
                max_retries=1,
            )
            self._cache[cache_key] = llm
        return llm

    async def test_connection(
        self,
        base_url: str,
        model: str,
        api_key: Optional[str] = None,
        timeout: float = 20.0,
    ) -> dict:
        """用临时配置发一条最小请求，不污染缓存。"""
        saved = self.settings_store.get_llm()
        effective_key = (api_key or "").strip()
        if not effective_key or "****" in effective_key:
            effective_key = saved.api_key

        base_url = (base_url or saved.base_url or "").strip().rstrip("/")
        model = (model or saved.model or "").strip()

        if not base_url or not base_url.startswith(("http://", "https://")):
            return {"ok": False, "error": "Base URL 必须以 http:// 或 https:// 开头"}
        if not model:
            return {"ok": False, "error": "模型名不能为空"}
        if not effective_key:
            return {"ok": False, "error": "API Key 不能为空"}

        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model=model,
            api_key=effective_key,
            base_url=base_url,
            temperature=0,
            timeout=timeout,
            max_tokens=32,
            max_retries=0,
        )

        started = time.perf_counter()
        try:
            response = await asyncio.wait_for(
                llm.ainvoke("请只回复四个字：连接成功"),
                timeout=timeout,
            )
            latency_ms = int((time.perf_counter() - started) * 1000)
            content = response.content if isinstance(response.content, str) else str(response.content)
            return {
                "ok": True,
                "latency_ms": latency_ms,
                "message": content[:120],
            }
        except asyncio.TimeoutError:
            return {"ok": False, "error": f"连接超时（>{int(timeout)} 秒），请检查网络或 Base URL"}
        except Exception as exc:  # noqa: BLE001 - 需要把供应商错误翻译成人话
            status = getattr(exc, "status_code", None)
            text = str(exc)
            if status == 401 or "401" in text or "Unauthorized" in text:
                return {"ok": False, "error": "API Key 无效或已过期（401）"}
            if status == 404 or "404" in text or "Not Found" in text:
                return {"ok": False, "error": "接口或模型不存在（404），请检查 Base URL 与模型名"}
            if "Connection" in type(exc).__name__ or "ConnectError" in text:
                return {"ok": False, "error": "无法连接服务，请检查网络与 Base URL"}
            logger.warning("LLM 测试连接失败: %s", text[:300])
            return {"ok": False, "error": f"连接失败：{text[:200]}"}


llm_factory = LLMFactory()


def get_llm_factory() -> LLMFactory:
    return llm_factory

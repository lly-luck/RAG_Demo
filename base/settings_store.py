"""运行期可修改的用户配置（目前仅 LLM）。

优先级：环境变量 > 用户目录 config.ini > 便携目录内置 config.ini。
用户配置只写 [llm]，不把 API Key 写进程序目录。
"""
from __future__ import annotations

import configparser
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from base import paths
from base.config import config


@dataclass(frozen=True)
class LLMSettings:
    base_url: str
    model: str
    api_key: str

    @property
    def configured(self) -> bool:
        placeholder_keys = {"sk-xxxx", "sk-your-key", "your-api-key", "xxxx"}
        key = self.api_key.strip()
        return (
            bool(key)
            and key.lower() not in placeholder_keys
            and bool(self.base_url.strip())
            and bool(self.model.strip())
        )


class SettingsStore:
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = Path(config_path) if config_path else paths.CONFIG_PATH

    def _read_user_config(self) -> configparser.ConfigParser:
        parser = configparser.ConfigParser()
        if self.config_path.is_file():
            parser.read(self.config_path, encoding="utf-8-sig")
        return parser

    def get_llm(self) -> LLMSettings:
        parser = self._read_user_config()

        api_key = (
            os.getenv("DEEPSEEK_API_KEY")
            or parser.get("llm", "llm_api_key", fallback="")
            or config.LLM_API_KEY
            or ""
        )
        base_url = (
            os.getenv("DEEPSEEK_BASE_URL")
            or parser.get("llm", "llm_base_url", fallback="")
            or config.LLM_BASE_URL
            or "https://api.deepseek.com"
        )
        model = (
            os.getenv("RAG_LLM_MODEL")
            or os.getenv("LLM_MODEL")
            or parser.get("llm", "model", fallback="")
            or config.LLM_MODEL
            or "deepseek-chat"
        )

        return LLMSettings(
            base_url=str(base_url).strip().rstrip("/"),
            model=str(model).strip(),
            api_key=str(api_key).strip(),
        )

    def is_configured(self) -> bool:
        return self.get_llm().configured

    def masked_key(self) -> str:
        key = self.get_llm().api_key
        if not key:
            return ""
        if len(key) <= 8:
            return "****"
        return f"{key[:3]}****{key[-4:]}"

    def public_dict(self) -> dict:
        settings = self.get_llm()
        return {
            "configured": settings.configured,
            "base_url": settings.base_url,
            "model": settings.model,
            "api_key_masked": self.masked_key(),
        }

    def save_llm(self, base_url: str, model: str, api_key: Optional[str] = None) -> LLMSettings:
        base_url = (base_url or "").strip().rstrip("/")
        model = (model or "").strip()
        if not base_url or not base_url.startswith(("http://", "https://")):
            raise ValueError("Base URL 必须以 http:// 或 https:// 开头")
        if not model:
            raise ValueError("模型名不能为空")

        parser = self._read_user_config()
        if not parser.has_section("llm"):
            parser.add_section("llm")

        old_key = parser.get("llm", "llm_api_key", fallback="")
        new_key = (api_key or "").strip()
        # 前端留空或回传掩码表示“保持原 Key”
        if not new_key or "****" in new_key:
            effective_key = old_key
        else:
            effective_key = new_key

        parser.set("llm", "llm_base_url", base_url)
        parser.set("llm", "model", model)
        parser.set("llm", "llm_api_key", effective_key)

        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(
            prefix="config-",
            suffix=".ini.tmp",
            dir=str(self.config_path.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                parser.write(handle)
            os.replace(temp_path, self.config_path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

        return self.get_llm()


settings_store = SettingsStore()


def get_settings_store() -> SettingsStore:
    return settings_store

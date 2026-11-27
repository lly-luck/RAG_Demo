import configparser
import json
import os

from base import paths

# 兼容旧代码：项目根目录（便携目录下即 app/）
BASE_DIR = str(paths.APP_DIR)


class Config:
    def __init__(self):
        # 配置优先级：内置 config.ini < 用户目录 config.ini；环境变量在读取后覆盖
        self.config_path = str(paths.CONFIG_PATH)
        self.bundled_config_path = str(paths.APP_DIR / "config.ini")

        self.config = configparser.ConfigParser()
        self.config.read(
            [self.bundled_config_path, self.config_path],
            encoding="utf-8-sig",
        )

        # MySQL 配置（仅 external 模式使用）
        self.MYSQL_HOST = self.config.get("mysql", "host", fallback="localhost")
        self.MYSQL_USER = self.config.get("mysql", "user", fallback="root")
        self.MYSQL_PASSWORD = self.config.get("mysql", "password", fallback="password")
        self.MYSQL_DATABASE = self.config.get("mysql", "database", fallback="subject_kg")

        # Redis 配置（仅 external 模式使用）
        self.REDIS_HOST = self.config.get("redis", "host", fallback="localhost")
        self.REDIS_PORT = self.config.getint("redis", "port", fallback=6379)
        self.REDIS_DB = self.config.getint("redis", "db", fallback=0)

        # 日志配置
        self.LOG_FILE = self.config.get("logger", "log_file", fallback="logs/app.log")

        # ===================== 存储后端 =====================
        # embedded：SQLite + 内存缓存 + Chroma（便携包默认）
        # external：MySQL + Redis + Milvus（开发机原模式）
        self.STORAGE_BACKEND = os.getenv(
            "RAG_DEMO_STORAGE_BACKEND",
            self.config.get("storage", "backend", fallback="embedded"),
        ).strip().lower()

        # ===================== Milvus 向量库配置（external） =====================
        self.MILVUS_URI = os.getenv(
            "MILVUS_PORT",
            self.config.get("milvus", "uri", fallback="http://localhost:19530"),
        )
        self.MILVUS_DATABASE_NAME = os.getenv(
            "MILVUS_DATABASE_NAME",
            self.config.get("milvus", "database_name", fallback="rag_qa"),
        )
        self.MILVUS_COLLECTION_NAME = os.getenv(
            "MILVUS_COLLECTION_NAME",
            self.config.get("milvus", "collection_name", fallback="rag_kb"),
        )

        # ===================== 内嵌存储路径 =====================
        self.USER_DATA_DIR = str(paths.USER_DATA_DIR)
        self.DATA_RUNTIME_DIR = str(paths.DATA_DIR)
        self.SQLITE_PATH = str(paths.DATA_DIR / "app.db")
        self.VECTOR_DB_DIR = str(paths.DATA_DIR / "vector_db")

        # ===================== LLM 大模型配置（默认值；运行期以 SettingsStore 为准） =====================
        self.LLM_MODEL = os.getenv(
            "RAG_LLM_MODEL",
            os.getenv("LLM_MODEL", self.config.get("llm", "model", fallback="deepseek-chat")),
        )
        self.LLM_API_KEY = os.getenv(
            "DEEPSEEK_API_KEY",
            self.config.get("llm", "llm_api_key", fallback=""),
        )
        self.LLM_BASE_URL = os.getenv(
            "DEEPSEEK_BASE_URL",
            self.config.get("llm", "llm_base_url", fallback="https://api.deepseek.com"),
        )

        # ===================== 检索分块参数 =====================
        self.PARENT_CHUNK_SIZE = self.config.getint("retrieval", "parent_chunk_size", fallback=1200)
        self.CHILD_CHUNK_SIZE = self.config.getint("retrieval", "child_chunk_size", fallback=300)
        self.CHUNK_OVERLAP = self.config.getint("retrieval", "chunk_overlap", fallback=50)
        self.RETRIEVAL_K = self.config.getint("retrieval", "retrieval_k", fallback=3)
        self.CANDIDATE_M = self.config.getint("retrieval", "candidate_m", fallback=2)

        # ===================== 应用业务配置 =====================
        raw_sources = self.config.get(
            "app",
            "valid_sources",
            fallback='["ai","java","test","ops","bigdata"]',
        )
        try:
            parsed_sources = json.loads(raw_sources)
            self.VALID_SOURCES = [str(item) for item in parsed_sources]
        except (TypeError, ValueError, json.JSONDecodeError):
            self.VALID_SOURCES = ["ai", "java", "test", "ops", "bigdata"]
        self.CUSTOMER_SERVICE_PHONE = self.config.get(
            "app", "customer_service_phone", fallback="13800138001"
        )

        # ===================== 服务配置 =====================
        self.SERVER_HOST = os.getenv(
            "RAG_DEMO_HOST",
            self.config.get("server", "host", fallback="127.0.0.1"),
        )
        self.SERVER_PORT = int(
            os.getenv(
                "RAG_DEMO_PORT",
                self.config.get("server", "port", fallback="8080"),
            )
        )

        # ===================== 目录配置 =====================
        self.DATA_DIR = str(paths.RAW_DATA_DIR)  # 原始文档根目录（构建知识库用）
        self.MODELS_DIR = str(paths.MODELS_DIR)  # 本地模型根目录
        self.SEEDS_DIR = str(paths.SEEDS_DIR)


# 单例模式：全局只加载一次配置
config = Config()


if __name__ == "__main__":
    print("存储后端:", config.STORAGE_BACKEND)
    print("用户数据目录:", config.USER_DATA_DIR)
    print("SQLite:", config.SQLITE_PATH)
    print("向量库目录:", config.VECTOR_DB_DIR)
    print("模型目录:", config.MODELS_DIR)
    print("LLM:", config.LLM_MODEL, config.LLM_BASE_URL)
    print("Milvus:", config.MILVUS_COLLECTION_NAME)

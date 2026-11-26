import configparser
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class Config:
    def __init__(self):
        # 拼接绝对路径
        self.config_path = os.path.join(BASE_DIR, 'config.ini')

        # 创建配置解析器
        self.config = configparser.ConfigParser()
        # 读取配置文件
        self.config.read(self.config_path, encoding='utf-8-sig')

        # MySQL 配置
        self.MYSQL_HOST = self.config.get('mysql', "host", fallback="localhost")
        self.MYSQL_USER = self.config.get('mysql', "user", fallback="root")
        self.MYSQL_PASSWORD = self.config.get('mysql', "password", fallback="password")
        self.MYSQL_DATABASE = self.config.get('mysql', "database", fallback="subject_kg")

        # Redis 配置
        self.REDIS_HOST = self.config.get('redis', 'host', fallback='localhost')  # Redis 主机地址
        self.REDIS_PORT = self.config.getint('redis', 'port', fallback=6379)  # Redis 端口
        # self.REDIS_PASSWORD = self.config.get('redis', 'password', fallback='123456')       # Redis 密码
        self.REDIS_DB = self.config.getint('redis', 'db', fallback=0)  # Redis 数据库编号

        # 日志配置
        self.LOG_FILE = self.config.get('logger', 'log_file', fallback='logs/app.log')  # 日志文件路径

        # ===================== Milvus 向量库配置 =====================
        self.MILVUS_URI = os.getenv("MILVUS_PORT", self.config.get("milvus", "uri", fallback="http://localhost:19530"))
        self.MILVUS_DATABASE_NAME = os.getenv("MILVUS_DATABASE_NAME",
                                              self.config.get("milvus", "database_name", fallback="rag_qa"))
        self.MILVUS_COLLECTION_NAME = os.getenv("MILVUS_COLLECTION_NAME",
                                                self.config.get("milvus", "collection_name", fallback="rag_kb"))

        # ===================== LLM 大模型配置 =====================
        self.LLM_MODEL = self.config.get("llm", "model", fallback="deepseek-flash")
        self.LLM_API_KEY = os.getenv("DEEPSEEK_API_KEY", self.config.get("llm", "llm_api_key"))
        self.LLM_BASE_URL = os.getenv("DEEPSEEK_BASE_URL",
                                      self.config.get("llm", "llm_base_url", fallback="https://api.deepseek.com"))

        # ===================== 检索分块参数 =====================
        self.PARENT_CHUNK_SIZE = self.config.getint("retrieval", "parent_chunk_size", fallback=1200)
        self.CHILD_CHUNK_SIZE = self.config.getint("retrieval", "child_chunk_size", fallback=300)
        self.CHUNK_OVERLAP = self.config.getint("retrieval", "chunk_overlap", fallback=50)
        self.RETRIEVAL_K = self.config.getint("retrieval", "retrieval_k", fallback=3)
        self.CANDIDATE_M = self.config.getint("retrieval", "candidate_m", fallback=2)

        # ===================== 应用业务配置 =====================
        self.VALID_SOURCES = eval(
            self.config.get("app", "valid_sources", fallback='["ai","java","test","ops","bigdata"]'))
        self.CUSTOMER_SERVICE_PHONE = self.config.get("app", "customer_service_phone", fallback="13800138001")

        # ===================== 目录配置 =====================
        self.DATA_DIR = os.path.join(BASE_DIR, "rag_qa", "data")  # 原始文档根目录
        self.MODELS_DIR = os.path.join(BASE_DIR, "model")  # 本地模型根目录


# 单例模式：全局只加载一次配置
config = Config()

if __name__ == '__main__':
    conf = Config()
    print("MySQL 主机:", conf.MYSQL_HOST)
    print("Redis 端口:", conf.REDIS_PORT)
    print("日志路径:", conf.LOG_FILE)

    print("Milvus:", conf.MILVUS_COLLECTION_NAME)
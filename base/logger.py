import logging
import os
from logging.handlers import RotatingFileHandler

from base import paths
from base.config import config


def _resolve_log_path(log_file: str) -> str:
    """相对路径统一放到可写的 USER_DATA_DIR/logs，绝对路径原样使用。"""
    if os.path.isabs(log_file):
        return log_file
    # 只取文件名，避免把 config 里的 logs/ 再拼一层
    return str(paths.LOG_DIR / os.path.basename(log_file))


def setup_logging(log_file: str = config.LOG_FILE):
    paths.LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = _resolve_log_path(log_file)

    logger = logging.getLogger("RAG-QA")
    logger.setLevel(logging.DEBUG)

    # 避免重复添加处理器
    if logger.handlers:
        return logger

    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # 让 uvicorn 的日志也进入同一个文件
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        if not any(isinstance(handler, RotatingFileHandler) for handler in uvicorn_logger.handlers):
            uvicorn_logger.addHandler(file_handler)

    return logger


# 全局单例日志对象
logger = setup_logging()

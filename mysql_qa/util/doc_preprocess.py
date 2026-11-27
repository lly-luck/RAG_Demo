"""
文本预处理工具模块
功能：对用户输入/问题文本进行标准化预处理（小写转换、中文分词）
为后续检索、匹配提供标准化文本
"""
import jieba

from base import paths
from base.logger import logger

# 把 jieba 前缀词典缓存固定到可写用户目录，避免在程序/项目目录生成 jieba.cache
try:
    _jieba_cache_dir = paths.USER_DATA_DIR / "cache"
    _jieba_cache_dir.mkdir(parents=True, exist_ok=True)
    jieba.dt.tmp_dir = str(_jieba_cache_dir)
except OSError:
    pass


def preprocess_text(text):
    """
    文本预处理核心函数：统一小写 + jieba 中文分词
    :param text: 原始输入文本
    :return: 分词后的词汇列表，异常时返回空列表
    """
    logger.debug(f"开始文本预处理：{text}")

    try:
        # 文本小写转换 + jieba 精确分词，返回词列表
        return jieba.lcut(text.lower())
    except AttributeError as e:
        # 捕获文本为空/非字符串类型等异常
        logger.error(f"文本预处理异常: {e}")
        return []
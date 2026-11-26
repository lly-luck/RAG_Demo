"""
Redis 缓存客户端
"""
import redis
import json
from base.config import config
from base.logger import logger


class RedisClient:

    def __init__(self):
        """
        初始化 Redis 连接
        从全局配置读取连接参数，自动解码响应为字符串，记录连接状态
        """
        try:
            self.redis_client = redis.Redis(
                host=config.REDIS_HOST,
                port=config.REDIS_PORT,
                db=config.REDIS_DB,
                decode_responses=True
            )
            logger.info(f"redis 连接成功")
        except redis.RedisError as e:
            logger.error(f"redis 连接失败：{e}")
            raise

    def set_data(self, key, value):
        """
        通用数据存储：将数据序列化为 JSON 存入 Redis
        :param key: 缓存键名
        :param value: 待存储数据（支持字典/列表等可序列化对象）
        """
        try:
            self.redis_client.set(key, json.dumps(value, ensure_ascii=False))
            logger.info(f"redis 数据存储成功")
        except redis.RedisError as e:
            logger.error(f"redis 数据存储失败：{e}")


    def get_data(self, key):
        """
        通用数据获取：从 Redis 读取并反序列化 JSON 数据
        :param key: 缓存键名
        :        return: 解析后的数据 / None（无数据）
        """
        try:
            result = self.redis_client.get(key)
            return json.loads(result) if result else None
        except redis.RedisError as e:
            logger.error(f"redis 通用数据获取失败：{e}")


    def get_answer(self, query):
        """
        问答专用：根据问题查询缓存答案
        :param query: 用户问题
        :return: 缓存答案 / None（未命中）
        """
        try:
            result = self.redis_client.get(f"answer:{query}")
            return json.loads(result) if result else None
        except redis.RedisError as e:
            logger.error(f"redis 答案查询失败：{e}")


if __name__ == '__main__':
    redcli = RedisClient()
    query = "测试问题222"
    answer = "测试答案222"
    redcli.set_data(f"answer:{query}", answer);
    print(redcli.get_answer("测试问题222"))
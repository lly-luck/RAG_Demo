from pymilvus import MilvusClient

# 初始化客户端(用于连接milvus数据库)
client = MilvusClient(uri="http://127.0.0.1:19530")


# 创建数据库
client.create_database("milvus_test")


# 查看数据库
dbs = client.list_databases()
print(f"现有数据库：{dbs}")


# 删除数据库
# client.drop_database("milvus_demos")
"""
RAG 问题分类模块
功能：使用 BERT 模型对用户问题进行二分类，区分 通用知识 与 专业咨询
"""
import os

import torch
from transformers import BertTokenizer, BertForSequenceClassification
from base.logger import logger


class QueryClassifier:
    """用户问题分类器"""

    def __init__(self):
        # BERT模型目录
        project_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        model_dir = os.path.join(project_path, "model", "bert_query_classifier")
        # BERT预训练自带 tokenizer（字粒度）
        self.tokenizer = BertTokenizer.from_pretrained(model_dir)
        # BERT问题分类模型
        self.bert_model = BertForSequenceClassification.from_pretrained(model_dir).eval()
        logger.info("问题分类模型加载成功")

    def predict_category(self, query: str):
        """
        预测问题分类
        :param query: 用户问题字符串
        :return: "通用知识" / "专业咨询"
        """
        if not query or not isinstance(query, str):
            return "通用知识"

        try:
            # BERT分词：原始文本转为模型需要的张量输入
            encodings = self.tokenizer(
                query,
                truncation=True,  # 文本超长则截断
                padding=True,  # 文本过短补占位符，对齐长度
                max_length=128,  # 序列最大token长度
                return_tensors="pt"  # 返回PyTorch张量
            )
            # 模型推理
            with torch.no_grad():
                # logits拿到分类原始分数
                # argmax取得分最高类别下标
                # item() 张量转为普通整数
                prediction = torch.argmax(self.bert_model(**encodings).logits, dim=1).item()

            # 映射业务标签：1=专业咨询，0=通用知识
            return "专业咨询" if prediction == 1 else "通用知识"

        except Exception as e:
            logger.error(f"问题分类预测失败: {e}")
            return "通用知识"


if __name__ == '__main__':
    classifier = QueryClassifier()
    test_queries = [
        "springboot的原理是什么",
        "AI学科的学费是多少",
        "你好",
        "大模型是什么",
    ]

    for q in test_queries:
        cat = classifier.predict_category(q)
        print(f"问题：{q} -> 分类：{cat}")

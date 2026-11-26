# 模型说明：仓库里的模型可能已经落后，请下载最新版

> ⚠️ **一句话结论：`model/` 目录里的模型是参考实现时的旧版本，不建议直接沿用。请到官方模型页下载当前最新版本，再放回 `model/` 下同名目录。**

本文说明三件事：为什么不把模型放进仓库、本地这份模型有哪些"过时"风险、以及怎么换成最新版。

---

## 1. 为什么仓库里没有模型权重

| 原因 | 说明 |
| --- | --- |
| 体积 | 本地 `model/` 约 **6.7 GB**（`bge-m3` 的 `pytorch_model.bin`、`onnx/model.onnx`、`bge-reranker-large` 的权重各占数百 MB～2 GB） |
| GitHub 限制 | 单文件硬上限 **100 MB**，超过直接拒绝推送；仓库建议控制在 1 GB 以内 |
| 发布习惯 | 权重属于"可再下载的产物"，用官方的模型仓库分发更合适，代码仓库只保留代码与配置 |

因此 `.gitignore` 中忽略了整个 `model/` 目录。需要权重时按下面的地址自行下载。

---

## 2. 这份本地模型"可能落后"在哪里

| 目录 | 用途 | 版本风险 |
| --- | --- | --- |
| `model/bge-m3/` | Embedding 向量模型，负责把文档块与问题编码成向量 | 参考实现基于 `BAAI/bge-m3` 的早期发布；官方后续持续更新权重，旧副本在长文本、多语言、稀疏/多向量检索上的表现弱于新版 |
| `model/bge-reranker-large/` | 交叉编码器重排模型，对召回候选重新打分 | 官方已推出 `bge-reranker-v2-m3`（更小、更快、多语言更强），`large` 这一代相对老 |
| `model/bert_query_classifier/` | "通用知识 / 专业咨询"二分类，决定走 FAQ 还是 RAG | 这是**按当时语料微调**的小模型，换业务、换语料后准确率会明显下降，建议用你自己的数据重训 |

另外 `model/` 内还混有下载工具产生的缓存/重复文件（`.msc`、`.mv`、`onnx/model.onnx` 与 `pytorch_model.bin` 是同一权重的两种格式），可以只保留实际用到的那一份来省空间。

---

## 3. 去哪里下载最新模型

| 模型 | HuggingFace | ModelScope（国内更快） | 说明 |
| --- | --- | --- | --- |
| bge-m3 | <https://huggingface.co/BAAI/bge-m3> | <https://modelscope.cn/models/BAAI/bge-m3> | 支持 dense / sparse / multi-vector，1024 维，多语言 |
| bge-reranker-large | <https://huggingface.co/BAAI/bge-reranker-large> | <https://modelscope.cn/models/BAAI/bge-reranker-large> | 旧版重排模型 |
| bge-reranker-v2-m3（推荐替换） | <https://huggingface.co/BAAI/bge-reranker-v2-m3> | <https://modelscope.cn/models/BAAI/bge-reranker-v2-m3> | 更新的一代，体积更小、效果更好 |
| bert 基座（用于重训分类器） | <https://huggingface.co/google-bert/bert-base-chinese> | <https://modelscope.cn/models/google-bert/bert-base-chinese> | 也可用 `hfl/chinese-roberta-wwm-ext` |

**下载后的目录要求**（代码里路径写死，名字不要改，除非同步改代码）：

```text
model/
├── bge-m3/                  # 包含 config.json / tokenizer* / pytorch_model.bin（或 model.safetensors）
├── bge-reranker-large/      # 同上
└── bert_query_classifier/   # config.json + model.safetensors + vocab.txt
```

### 用命令行下载（示例）

```bash
# 方式一：huggingface-cli（需 pip install huggingface_hub）
huggingface-cli download BAAI/bge-m3 --local-dir model/bge-m3 --local-dir-use-symlinks False
huggingface-cli download BAAI/bge-reranker-v2-m3 --local-dir model/bge-reranker-v2-m3

# 方式二：modelscope（国内网络更稳）
python -c "from modelscope import snapshot_download; snapshot_download('BAAI/bge-m3', cache_dir='./model')"

# 方式三：git（需要 git-lfs）
git lfs install
git clone https://huggingface.co/BAAI/bge-m3 model/bge-m3
```

---

## 4. 换成新版本后要检查的代码点

1. **路径**：`base/config.py` 的 `MODELS_DIR`，以及各模块里 `model/bge-m3`、`model/bge-reranker-large` 的硬编码字符串。
2. **向量维度**：Milvus Collection 的 `dim` 需与新模型一致（`bge-m3` 为 1024；换成 768 维模型要重建集合）。
3. **归一化与距离度量**：换了 embedding 模型后，`normalize_embeddings`、`metric_type`（IP / COSINE）、相似度阈值都要重新标定。
4. **重排模型接口**：`bge-reranker-v2-m3` 与 `bge-reranker-large` 的调用方式（`FlagReranker`）基本一致，但分数分布不同，命中阈值需重新测。
5. **分类器**：换基座后必须用 `rag_qa/core/query_classifier.py` 对应的训练脚本重新微调，否则二分类结果不可信。

> 提示：换模型属于"效果调优"，建议先用小批量真实问题做 A/B（召回率、重排命中率、回答满意度），确认指标提升后再整体替换。

---

## 5. 如果确实想把权重复制到 GitHub

正常仓库无法容纳 6.7 GB 权重，可选方案：

- **Git LFS**：`git lfs track "model/**"`，但 GitHub 免费额度只有 1 GB 存储 / 1 GB 月流量，超出需付费数据包。
- **Release 附件**：把权重打包成不超过 2 GB 的分卷，作为 Release 的 asset 上传（不占仓库体积）。
- **网盘 / 对象存储**：最省事，README 里给出下载链接即可。

---

_最后更新：随代码提交同步维护。如果你发现模型页已迁移或有更新的官方型号，欢迎直接提 PR 更新本文件。_

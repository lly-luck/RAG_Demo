# 便携版交付与构建说明

本文面向开发者，说明如何把项目构建为 Windows 便携包、如何验证与更新。
最终用户请看便携包内的 `README.txt`。

## 交付形态

- Windows 便携文件夹 `RAGDemo-portable/`，双击 `launcher.exe` 启动。
- 不写注册表、不创建系统服务；删除文件夹即卸载。
- 首次启动把 `runtime.zip` 解压到 `%LOCALAPPDATA%\RAGDemo\runtime\<版本>`，并执行一次
  `conda-unpack`；之后便携目录可随意移动/复制。
- 默认数据目录：`%LOCALAPPDATA%\RAGDemo`；在便携目录放 `portable.txt` 可切换为
  `<便携目录>\.ragdemo` 的完全绿色模式。

## 构建前置条件

- Windows 10/11 64 位。
- Python 3.12 conda 环境 `edu_rag`（已安装项目依赖、CPU 版 torch）。
- 本机 MySQL 可访问（用于导出 FAQ 种子）；或已存在 `packaging/seeds/faq.sqlite`。
- 网络可访问 npm registry、ModelScope / HF mirror（准备前端 vendor 与 reranker-base）。
- 磁盘：至少 15GB 空闲（构建 + 产物）；建议放在 D 盘。便携目录约 5.6GB，首次运行后运行时缓存约 2.1GB。

## 构建

```powershell
conda activate edu_rag
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
# 若未激活环境，也可显式指定：
# $env:EDU_RAG_PYTHON = "<你的 conda 环境>\python.exe"
```

常用参数：

```powershell
# 跳过知识库重建（已有 packaging/seeds/vector_db）
powershell -ExecutionPolicy Bypass -File packaging\build.ps1 --skip-kb
# 跳过运行时打包（已有 build/runtime.zip）
powershell -ExecutionPolicy Bypass -File packaging\build.ps1 --skip-runtime
# 强制重建知识库/运行时
powershell -ExecutionPolicy Bypass -File packaging\build.ps1 --force
# 只用精选文档建库（例如全量建库太慢时）
powershell -ExecutionPolicy Bypass -File packaging\build.ps1 --kb-data-dir D:\rag_curated_docs
```

流水线步骤（`packaging/build.py`）：

1. 检查/安装 `conda-pack`、`PyInstaller`、7-Zip。
2. `export_faq.py`：MySQL `subjects_kg.jpkb` → `packaging/seeds/faq.sqlite`。
3. `prepare_models.py`：ModelScope 下载 `BAAI/bge-reranker-base`（只取 safetensors）。
4. `build_kb.py`：`rag_qa/data` → 父子分块 → BGE-M3 → Chroma `packaging/seeds/vector_db`。
5. `vendor_assets`：npm 拉取 marked / Font Awesome 到 `static/vendor`。
6. `conda-pack`：`edu_rag` → `build/runtime.zip`。
7. PyInstaller：`packaging/launcher.py` → `build/launcher_dist/launcher/`（onedir）。
8. staging：`dist/RAGDemo-portable/{app,runtime.zip,launcher/,启动.bat,...}`。
9. 冒烟测试（staging app + dev Python）。
10. 7-Zip 压缩为 `dist/RAGDemo-portable-<version>.7z`（实测约 2.9GB），输出 SHA256。

## 产物结构

```
RAGDemo-portable/
├── app/                 # 源码 + static + model + seeds
├── runtime.zip          # conda-pack 运行时（实测约 1.9GB）
├── launcher/            # PyInstaller onedir
│   ├── launcher.exe
│   └── _internal/...
├── 启动.bat             # 双击入口
├── 创建快捷方式.bat
└── README.txt
```

启动器采用 onedir 而不是 onefile：部分 Windows 安全策略会阻止 onefile 在 Temp
下解压，onedir 更稳；代价是多一个 `_internal` 文件夹。

打包时排除 `model/bge-m3/onnx` 与 `model/bge-reranker-large`，模型总量约 3.6GB。

## 验证

1. 开发态冒烟：

```bash
python app.py
python packaging/smoke_test.py --base-url http://127.0.0.1:8080 --wait 240
```

2. 模拟干净环境：

- 停止 MySQL/Docker；把 `LOCALAPPDATA` 指向临时目录，`PATH` 精简。
- 把 `dist/RAGDemo-portable` 复制到无空格/非项目路径，运行 `启动.bat`（或 `launcher\launcher.exe`）。
- 首次启动应解压运行时、加载模型、自动开浏览器。
- 首次运行后把目录复制到另一个路径再启动，确认复用运行时缓存且问答正常。
- 用 `portable.txt` 模式再跑一次，确认数据落在便携目录。
- 把目录放到含中文/空格路径（如 `D:\答辩 演示\RAGDemo`）再跑一次。

3. 检查：

- `%LOCALAPPDATA%\RAGDemo\logs\launcher.log`、`server.err.log` 无异常。
- 便携目录文件未被改写。
- 日志中没有 MySQL/Redis/Milvus 连接尝试（embedded 模式）。
- 退出 launcher 后无残留 `python.exe` 进程。

## 常见问题

- **conda-pack 失败**：确认在 `edu_rag` 环境执行，且 `conda` 在 PATH；可先在
  `edu_rag` 中 `pip install setuptools conda-pack`。
- **conda-unpack 失败**：确认 `runtime.zip` 解压后根目录有 `python.exe`；启动器优先执行
  `python.exe Scripts\conda-unpack-script.py`（noconsole 下比 `.exe` 包装器更稳），失败再回退到
  `Scripts\conda-unpack.exe`。
- **首次启动很慢**：解压 2.1GB 运行时 + 加载 3.6GB 模型，属正常；建议 SSD。
- **端口冲突**：launcher 自动选择 8080–8109 或系统空闲端口。
- **杀软/SmartScreen**：launcher 未签名，可能被误报，添加信任即可。
- **FAT32 U 盘**：装不下（单文件 >4GB），请用 NTFS/exFAT。

## 本次构建记录（2026-11-27）

- 版本：`1.0.0`
- 知识库：`LLM基础知识` + `03_Claude-Code与Agent实战手册`（精选 2 篇，176 个子块；全量 5 篇建库约需 30–60 分钟，可用 `--kb-data-dir` 指定目录重建）
- 便携目录：`dist/RAGDemo-portable`（约 5.5GB）
- 分发包：`dist/RAGDemo-portable-1.0.0.7z`（2.83GB）
- SHA256：`7a3c97a27267bf46f197c42a3b867e0886e0c33675a5cad0b6be23b572bf5f94`
- 已验证：
  - 无 MySQL/Redis/Milvus 的 embedded 启动；
  - FAQ、问候、RAG 流式回答（冒烟 9 项全绿）；
  - 打包运行时换路径解压 + `conda-unpack` + `import torch/chromadb`；
  - 启动器首次运行解压、启动服务、`/health` 200、退出码 0；
  - 设置接口：未配置提示、保存、掩码返回、错误 Key 返回 401 友好提示。
- 验证环境说明：本机构建沙箱限制子进程写入 `%LOCALAPPDATA%`，启动器测试使用 `--data-dir`
  指向工作区；目标机按默认 `%LOCALAPPDATA%\\RAGDemo` 运行前，建议按本文“验证”章节做一次彩排。

## 更新与回滚

- 修改代码后重新构建；运行时缓存按 `VERSION` 隔离（`runtime\<版本>`），旧版本可保留。
- 回滚：用旧版本便携目录启动；或把 `VERSION` 改回旧值并保留对应运行时缓存。
- 用户数据（SQLite/Chroma/config）在 `%LOCALAPPDATA%\RAGDemo`，升级不覆盖；如需重置，
  删除该目录后重新启动即可从种子初始化。

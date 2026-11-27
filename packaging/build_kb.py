"""构建 Chroma 知识库种子。

复用现有的文档加载/父子分块逻辑，把 rag_qa/data 下的 PDF 写入 Chroma，
产物默认放在 packaging/seeds/vector_db，随便携包分发。

用法：
    python packaging/build_kb.py --force
    python packaging/build_kb.py --data-dir D:/rag_test_docs --output D:/rag_test_vector --force
"""
from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def reorganize_data_dir(data_dir: Path) -> None:
    """把历史遗留的 data/ 目录并入 ai_data/，保证 source 标签合法。"""
    legacy = data_dir / "data"
    if not legacy.is_dir():
        return
    target = data_dir / "ai_data"
    target.mkdir(parents=True, exist_ok=True)
    moved = 0
    for item in legacy.iterdir():
        destination = target / item.name
        if destination.exists():
            print(f"[skip] 已存在：{destination}")
            continue
        shutil.move(str(item), str(destination))
        moved += 1
    try:
        legacy.rmdir()
    except OSError:
        pass
    print(f"已把 {moved} 个文件从 data/ 移到 ai_data/")


def build(data_dir: Path, output_dir: Path, collection_name: str, force: bool) -> int:
    from base.config import config
    from rag_qa.core.chroma_store import ChromaVectorStore
    from rag_qa.core.document_processor import process_documents
    from rag_qa.core.model_registry import get_embedding_model

    if output_dir.exists():
        if not force:
            raise SystemExit(f"输出目录已存在：{output_dir}（加 --force 重建）")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    print(f"[1/3] 加载并切分文档：{data_dir}")
    chunks = process_documents(str(data_dir))
    print(f"      子块数量：{len(chunks)}，耗时 {time.perf_counter() - started:.1f}s")

    print("[2/3] 加载 BGE-M3 嵌入模型")
    embedding = get_embedding_model()

    print(f"[3/3] 写入 Chroma：{output_dir}")
    store = ChromaVectorStore(
        persist_dir=str(output_dir),
        collection_name=collection_name,
        embedding=embedding,
        reranker=None,
        load_models=False,
    )
    store.add_documents(chunks)
    total = store.count()
    print(f"完成：{total} 个子块，总耗时 {time.perf_counter() - started:.1f}s")
    return total


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-dir",
        default=str(ROOT / "rag_qa" / "data"),
        help="原始文档目录",
    )
    parser.add_argument(
        "--output",
        default=str(ROOT / "packaging" / "seeds" / "vector_db"),
        help="Chroma 持久化目录",
    )
    parser.add_argument("--collection", default=None, help="集合名，默认取 config.ini")
    parser.add_argument("--force", action="store_true", help="删除已有输出并重建")
    parser.add_argument(
        "--skip-reorganize",
        action="store_true",
        help="不自动把 data/ 并入 ai_data/",
    )
    args = parser.parse_args()

    from base.config import config

    data_dir = Path(args.data_dir)
    if not args.skip_reorganize:
        reorganize_data_dir(data_dir)

    build(
        data_dir=data_dir,
        output_dir=Path(args.output),
        collection_name=args.collection or config.MILVUS_COLLECTION_NAME,
        force=args.force,
    )


if __name__ == "__main__":
    main()

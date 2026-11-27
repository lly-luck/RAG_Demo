"""准备便携包所需的 bge-reranker-base。

只下载 CrossEncoder 需要的文件（safetensors + tokenizer），不下载 onnx 和
pytorch_model.bin，避免多占约 2.2GB。

用法：
    python packaging/prepare_models.py
    python packaging/prepare_models.py --output model/bge-reranker-base --force
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

MODEL_ID = "BAAI/bge-reranker-base"
FILES = [
    "config.json",
    "configuration.json",
    "model.safetensors",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "sentencepiece.bpe.model",
]
MIN_WEIGHT_SIZE = 1_000_000_000  # 约 1.11GB


def _needs_download(path: Path, name: str) -> bool:
    if not path.is_file():
        return True
    if name == "model.safetensors" and path.stat().st_size < MIN_WEIGHT_SIZE:
        return True
    return False


def download_from_modelscope(target_dir: Path, force: bool) -> None:
    from modelscope.hub.file_download import model_file_download

    for name in FILES:
        target = target_dir / name
        if not force and not _needs_download(target, name):
            print(f"[skip] {name}")
            continue
        print(f"[modelscope] {name} ...")
        model_file_download(
            model_id=MODEL_ID,
            file_path=name,
            local_dir=str(target_dir),
        )


def download_from_hf_mirror(target_dir: Path, force: bool) -> None:
    from huggingface_hub import hf_hub_download

    for name in FILES:
        target = target_dir / name
        if not force and not _needs_download(target, name):
            print(f"[skip] {name}")
            continue
        print(f"[hf-mirror] {name} ...")
        hf_hub_download(
            repo_id=MODEL_ID,
            filename=name,
            local_dir=str(target_dir),
            endpoint="https://hf-mirror.com",
        )


def verify(target_dir: Path) -> None:
    missing = [name for name in FILES if not (target_dir / name).is_file()]
    if missing:
        raise RuntimeError(f"缺少模型文件: {', '.join(missing)}")
    weight = target_dir / "model.safetensors"
    size = weight.stat().st_size
    if size < MIN_WEIGHT_SIZE:
        raise RuntimeError(f"model.safetensors 大小异常: {size} bytes")
    print(f"reranker-base 就绪：{target_dir}（{size / 1024**3:.2f} GB）")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default=str(ROOT / "model" / "bge-reranker-base"),
        help="输出目录",
    )
    parser.add_argument("--force", action="store_true", help="强制重新下载")
    args = parser.parse_args()

    target_dir = Path(args.output)
    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        download_from_modelscope(target_dir, args.force)
    except Exception as exc:  # noqa: BLE001
        print(f"ModelScope 下载失败，切换 HF mirror：{exc}")
        download_from_hf_mirror(target_dir, args.force)

    verify(target_dir)


if __name__ == "__main__":
    main()

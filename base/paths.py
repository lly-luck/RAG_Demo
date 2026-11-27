"""应用路径解析。

把“只读的程序资源”和“可写的用户数据”分开：

- APP_DIR：便携目录下的 app 文件夹（源码、模型、static、seeds）。
- USER_DATA_DIR：默认 %LOCALAPPDATA%\\RAGDemo，可通过 RAG_DEMO_DATA_DIR 覆盖。
  若便携目录下存在 portable.txt 且目录可写，则使用 <便携目录>\\.ragdemo，
  实现“配置/数据/运行时随文件夹走”的完全绿色模式。

所有运行期写入（日志、SQLite、Chroma、用户配置、运行时解压）都必须走
USER_DATA_DIR，保证程序目录本身不被修改。
"""
from __future__ import annotations

import os
import shutil
import warnings
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent

# 只读资源
def _resolve_seeds_dir() -> Path:
    override = os.environ.get("RAG_DEMO_SEEDS_DIR")
    if override:
        return Path(override).expanduser().resolve()
    primary = APP_DIR / "seeds"
    if primary.is_dir():
        return primary
    # 开发态：构建产物默认落在 packaging/seeds，安装包会把它复制到 app/seeds
    fallback = APP_DIR / "packaging" / "seeds"
    if fallback.is_dir():
        return fallback
    return primary


SEEDS_DIR = _resolve_seeds_dir()
MODELS_DIR = APP_DIR / "model"
STATIC_DIR = APP_DIR / "static"
RAW_DATA_DIR = APP_DIR / "rag_qa" / "data"


def _is_writable_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_probe"
        probe.write_text("", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def _resolve_user_data_dir() -> Path:
    override = os.environ.get("RAG_DEMO_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()

    # 便携模式：需要用户显式放置 portable.txt，避免把数据意外写到 U 盘/程序目录
    portable_flag = APP_DIR.parent / "portable.txt"
    if not portable_flag.is_file():
        # 开发态：允许放在项目根目录
        portable_flag = APP_DIR / "portable.txt"
    if portable_flag.is_file():
        candidate = portable_flag.parent / ".ragdemo"
        if _is_writable_dir(candidate):
            return candidate.resolve()
        warnings.warn(
            f"检测到 {portable_flag} 但 {candidate} 不可写，回退到 LOCALAPPDATA。",
            RuntimeWarning,
        )

    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata).resolve() / "RAGDemo"
    return Path.home() / "AppData" / "Local" / "RAGDemo"


USER_DATA_DIR = _resolve_user_data_dir()
DATA_DIR = USER_DATA_DIR / "data"
LOG_DIR = USER_DATA_DIR / "logs"
RUNTIME_DIR = USER_DATA_DIR / "runtime"
CONFIG_PATH = USER_DATA_DIR / "config.ini"


def is_portable_mode() -> bool:
    """当前是否使用便携目录内的 .ragdemo 作为数据目录。"""
    return USER_DATA_DIR == (APP_DIR.parent / ".ragdemo").resolve()


def ensure_user_data() -> dict:
    """创建用户数据目录，并在首次运行时复制预构建种子。

    返回复制状态，调用方可据此记录日志。
    """
    for directory in (USER_DATA_DIR, DATA_DIR, LOG_DIR):
        directory.mkdir(parents=True, exist_ok=True)

    result = {
        "db_seeded": False,
        "vector_seeded": False,
        "missing": [],
    }

    db_target = DATA_DIR / "app.db"
    db_seed = SEEDS_DIR / "faq.sqlite"
    if not db_target.exists():
        if db_seed.is_file():
            shutil.copy2(db_seed, db_target)
            result["db_seeded"] = True
        else:
            result["missing"].append(str(db_seed))

    vector_target = DATA_DIR / "vector_db"
    vector_seed = SEEDS_DIR / "vector_db"
    if not vector_target.exists():
        if vector_seed.is_dir():
            shutil.copytree(vector_seed, vector_target)
            result["vector_seeded"] = True
        else:
            result["missing"].append(str(vector_seed))

    return result

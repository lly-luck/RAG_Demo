"""便携包构建流水线。

前置条件：
- 在 edu_rag 环境（Python 3.12 + CPU torch）中运行本脚本；
- 本机 MySQL 可访问（导出 FAQ 种子），或已有 packaging/seeds/faq.sqlite；
- 网络可访问 npm registry / ModelScope（准备前端 vendor 与 reranker-base）。

用法：
    python packaging/build.py
    python packaging/build.py --skip-kb --skip-runtime
    python packaging/build.py --force
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGING = ROOT / "packaging"
BUILD = ROOT / "build"
DIST = ROOT / "dist"
STAGE = DIST / "RAGDemo-portable"


def log(message: str) -> None:
    print(f"\n=== {message} ===", flush=True)


def run(command, cwd=ROOT, check=True, capture=False):
    print("$", " ".join(str(item) for item in command), flush=True)
    kwargs = {"cwd": str(cwd)}
    if capture:
        kwargs["capture_output"] = True
        kwargs["text"] = True
        kwargs["encoding"] = "utf-8"
        kwargs["errors"] = "replace"
    result = subprocess.run(command, **kwargs)
    if check and result.returncode != 0:
        detail = ""
        if capture:
            detail = f"\nstdout:\n{result.stdout[-2000:]}\nstderr:\n{result.stderr[-2000:]}"
        raise SystemExit(f"命令失败（{result.returncode}）：{command}{detail}")
    return result


def python_exe() -> str:
    return os.environ.get("EDU_RAG_PYTHON", sys.executable)


def ensure_tools() -> None:
    log("检查构建工具")
    py = python_exe()
    for package in ("conda-pack", "pyinstaller"):
        result = run([py, "-m", "pip", "show", package], check=False, capture=True)
        if result.returncode != 0:
            run([py, "-m", "pip", "install", package])


def find_7z() -> str | None:
    for candidate in (
        shutil.which("7z"),
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
    ):
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def export_faq(force: bool) -> None:
    seed = PACKAGING / "seeds" / "faq.sqlite"
    if seed.is_file() and not force:
        log(f"FAQ 种子已存在，跳过：{seed}")
        return
    log("导出 MySQL FAQ 到 SQLite")
    run([python_exe(), str(PACKAGING / "export_faq.py")])


def prepare_models(force: bool) -> None:
    target = ROOT / "model" / "bge-reranker-base" / "model.safetensors"
    if target.is_file() and target.stat().st_size > 1_000_000_000 and not force:
        log("reranker-base 已存在，跳过")
        return
    log("准备 bge-reranker-base")
    run([python_exe(), str(PACKAGING / "prepare_models.py")] + (["--force"] if force else []))


def build_kb(force: bool, data_dir: str | None = None) -> None:
    seed = PACKAGING / "seeds" / "vector_db"
    if seed.is_dir() and not force:
        log(f"Chroma 种子已存在，跳过：{seed}")
        return
    log("构建 Chroma 知识库")
    command = [python_exe(), str(PACKAGING / "build_kb.py"), "--force"]
    if data_dir:
        command.extend(["--data-dir", data_dir])
    run(command)


def vendor_assets(force: bool) -> None:
    target = ROOT / "static" / "vendor" / "marked.min.js"
    if target.is_file() and not force:
        log("前端 vendor 已存在，跳过")
        return
    log("准备前端 vendor（marked / Font Awesome）")
    temp = PACKAGING / "vendor_tmp"
    temp.mkdir(parents=True, exist_ok=True)
    run([
        "npm", "install", "--prefix", str(temp), "--no-save", "--no-audit", "--no-fund",
        "marked@12", "@fortawesome/fontawesome-free@6.4.0",
    ])
    vendor = ROOT / "static" / "vendor"
    (vendor / "fontawesome" / "css").mkdir(parents=True, exist_ok=True)
    (vendor / "fontawesome" / "webfonts").mkdir(parents=True, exist_ok=True)
    shutil.copy2(temp / "node_modules/marked/marked.min.js", vendor / "marked.min.js")
    shutil.copy2(temp / "node_modules/marked/LICENSE.md", vendor / "marked.LICENSE.md")
    shutil.copy2(
        temp / "node_modules/@fortawesome/fontawesome-free/css/all.min.css",
        vendor / "fontawesome" / "css" / "all.min.css",
    )
    shutil.copy2(
        temp / "node_modules/@fortawesome/fontawesome-free/LICENSE.txt",
        vendor / "fontawesome" / "LICENSE.txt",
    )
    for font in (temp / "node_modules/@fortawesome/fontawesome-free/webfonts").iterdir():
        shutil.copy2(font, vendor / "fontawesome" / "webfonts" / font.name)


def pack_runtime(force: bool) -> None:
    BUILD.mkdir(parents=True, exist_ok=True)
    output = BUILD / "runtime.zip"
    if output.is_file() and not force:
        log(f"runtime.zip 已存在，跳过：{output}")
        return
    log("conda-pack 打包运行时")
    py = Path(python_exe())
    conda_pack = py.parent / "Scripts" / "conda-pack.exe"
    if conda_pack.is_file():
        command = [str(conda_pack)]
    else:
        command = [python_exe(), "-m", "conda_pack"]
    run(command + ["-n", "edu_rag", "--format", "zip", "-o", str(output), "--force"])


def build_launcher() -> None:
    log("PyInstaller 构建 launcher（onedir，避免 onefile 临时目录兼容问题）")
    run([
        python_exe(), "-m", "PyInstaller",
        str(PACKAGING / "launcher.py"),
        "--onedir", "--noconsole", "--clean", "--noconfirm",
        "--name", "launcher",
        "--distpath", str(BUILD / "launcher_dist"),
        "--workpath", str(BUILD / "launcher_work"),
        "--specpath", str(BUILD / "launcher_spec"),
    ])


def copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".idea", "logs"))


def stage() -> None:
    log("组装便携目录")
    if STAGE.exists():
        shutil.rmtree(STAGE, ignore_errors=True)
    app = STAGE / "app"
    app.mkdir(parents=True)

    for name in (
        "app.py",
        "faq_milvus.py",
        "config.ini",
        "VERSION",
        "requirements.txt",
        "README.md",
        "MODEL_NOTICE.md",
    ):
        source = ROOT / name
        if source.is_file():
            shutil.copy2(source, app / name)

    for name in ("base", "mysql_qa", "rag_qa", "storage", "static"):
        copy_tree(ROOT / name, app / name)

    seeds_src = PACKAGING / "seeds"
    copy_tree(seeds_src, app / "seeds")

    model_src = ROOT / "model"
    model_dst = app / "model"
    model_dst.mkdir(parents=True, exist_ok=True)
    model_ignore = shutil.ignore_patterns(
        "onnx", "bge-reranker-large", "*.msc", "*.mv", "._____temp",
        "__pycache__", "*.pyc", "README.md", "imgs",
    )
    shutil.copytree(model_src, model_dst, dirs_exist_ok=True, ignore=model_ignore)

    shutil.copy2(BUILD / "runtime.zip", STAGE / "runtime.zip")
    launcher_src = BUILD / "launcher_dist" / "launcher"
    if not (launcher_src / "launcher.exe").is_file():
        raise SystemExit(f"未找到 launcher：{launcher_src / 'launcher.exe'}")
    copy_tree(launcher_src, STAGE / "launcher")
    shutil.copy2(PACKAGING / "README-portable.txt", STAGE / "README.txt")

    (STAGE / "启动.bat").write_text(
        '@echo off\nchcp 65001 >nul\ncd /d "%~dp0"\nstart "" "%~dp0launcher\\launcher.exe"\n',
        encoding="utf-8",
    )
    (STAGE / "创建快捷方式.bat").write_text(
        '@echo off\n'
        'chcp 65001 >nul\n'
        'powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws=New-Object -ComObject WScript.Shell; '
        "$lnk=$ws.CreateShortcut([Environment]::GetFolderPath('Desktop')+'\\智慧问答系统.lnk'); "
        "$lnk.TargetPath='%~dp0launcher\\launcher.exe'; $lnk.WorkingDirectory='%~dp0'; "
        "$lnk.IconLocation='%~dp0launcher\\launcher.exe'; $lnk.Save()\"\n"
        'echo 已创建桌面快捷方式\npause\n',
        encoding="utf-8",
    )


def smoke_test(skip_rag: bool = True) -> None:
    log("对 staging 目录做冒烟测试")
    data_dir = BUILD / "smoke_data"
    shutil.rmtree(data_dir, ignore_errors=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    for key in ("RAG_DEMO_SEEDS_DIR", "DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL"):
        env.pop(key, None)
    env.update({
        "RAG_DEMO_DATA_DIR": str(data_dir),
        "RAG_DEMO_STORAGE_BACKEND": "embedded",
        "PYTHONUTF8": "1",
    })
    out_path = BUILD / "smoke_server.log"
    with out_path.open("w", encoding="utf-8") as log_handle:
        process = subprocess.Popen(
            [python_exe(), "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8098"],
            cwd=str(STAGE / "app"),
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
        )
    try:
        command = [
            python_exe(), str(PACKAGING / "smoke_test.py"),
            "--base-url", "http://127.0.0.1:8098",
            "--wait", "240",
            "--faq-db", str(STAGE / "app" / "seeds" / "faq.sqlite"),
        ]
        if skip_rag:
            command.append("--skip-rag")
        run(command)
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


def compress() -> None:
    log("压缩便携包")
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    seven_zip = find_7z()
    if seven_zip:
        output = DIST / f"RAGDemo-portable-{version}.7z"
        # 模型权重与 runtime.zip 已基本不可压缩，用 -mx=1 换取更快的打包速度
        run([seven_zip, "a", "-t7z", "-mx=1", "-y", str(output), str(STAGE)])
    else:
        print("未找到 7-Zip，退回 zip（体积更大）。建议 winget install 7zip.7zip")
        output = shutil.make_archive(str(DIST / f"RAGDemo-portable-{version}"), "zip", STAGE)
        output = Path(output)

    hasher = hashlib.sha256()
    with output.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            hasher.update(chunk)
    digest = hasher.hexdigest()
    checksum = output.with_suffix(output.suffix + ".sha256")
    checksum.write_text(f"{digest}  {output.name}\n", encoding="utf-8")
    print(f"产物：{output}（{output.stat().st_size / 1024**3:.2f} GB）")
    print(f"SHA256：{digest}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-kb", action="store_true")
    parser.add_argument("--skip-runtime", action="store_true")
    parser.add_argument("--skip-launcher", action="store_true")
    parser.add_argument("--skip-compress", action="store_true")
    parser.add_argument("--kb-data-dir", default=None, help="构建知识库的原始文档目录")
    parser.add_argument("--force", action="store_true", help="重建所有缓存产物")
    args = parser.parse_args()

    started = time.perf_counter()
    DIST.mkdir(parents=True, exist_ok=True)

    ensure_tools()
    export_faq(args.force)
    prepare_models(args.force)
    vendor_assets(args.force)
    if not args.skip_kb:
        build_kb(args.force, args.kb_data_dir)
    if not args.skip_runtime:
        pack_runtime(args.force)
    if not args.skip_launcher:
        build_launcher()

    stage()
    launcher_ok = (BUILD / "launcher_dist" / "launcher" / "launcher.exe").is_file()
    if (BUILD / "runtime.zip").is_file() and launcher_ok:
        smoke_test(skip_rag=True)
    else:
        print("跳过冒烟测试：缺少 runtime.zip 或 launcher")

    if not args.skip_compress:
        compress()

    print(f"\n完成，耗时 {time.perf_counter() - started:.1f}s")


if __name__ == "__main__":
    main()

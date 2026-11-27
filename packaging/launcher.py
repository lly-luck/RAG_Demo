"""便携包启动器。

职责：
1. 首次运行把 runtime.zip 解压到固定缓存目录，并执行一次 conda-unpack；
2. 选择空闲端口，启动 runtime\\python.exe -m uvicorn app:app；
3. 轮询 /health，就绪后自动打开浏览器；
4. 关闭窗口时终止服务进程。

开发态可直接运行：
    python packaging/launcher.py --runtime-python D:\\...\\envs\\edu_rag\\python.exe --app-dir .
打包态由 PyInstaller 生成 launcher.exe，放在便携目录根。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import webbrowser
import zipfile
from pathlib import Path

APP_TITLE = "智慧问答系统"
DEFAULT_VERSION = "1.0.0"
HEALTH_TIMEOUT = 240


def get_base_dir(app_dir_arg: str | None = None) -> Path:
    if app_dir_arg:
        return Path(app_dir_arg).resolve()
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        # 兼容 onedir：便携包根/launcher/launcher.exe
        if (exe_dir / "app").is_dir() or (exe_dir / "runtime.zip").is_file():
            return exe_dir
        if (exe_dir.parent / "app").is_dir() or (exe_dir.parent / "runtime.zip").is_file():
            return exe_dir.parent
        return exe_dir
    return Path(__file__).resolve().parent.parent


def get_app_dir(base_dir: Path) -> Path:
    candidate = base_dir / "app"
    return candidate if (candidate / "app.py").is_file() else base_dir


def writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_probe"
        probe.write_text("", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def resolve_data_dir(base_dir: Path, override: str | None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    if (base_dir / "portable.txt").is_file():
        candidate = base_dir / ".ragdemo"
        if writable(candidate):
            return candidate.resolve()
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local).resolve() / "RAGDemo"
    return Path.home() / "AppData" / "Local" / "RAGDemo"


def read_version(base_dir: Path) -> str:
    for candidate in (base_dir / "VERSION", base_dir / "app" / "VERSION"):
        if candidate.is_file():
            value = candidate.read_text(encoding="utf-8").strip()
            if value:
                return value
    return DEFAULT_VERSION


def find_free_port(preferred: int = 8080) -> int:
    for port in [preferred] + list(range(preferred + 1, preferred + 30)):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def health_ok(port: int, timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/health", timeout=timeout
        ) as response:
            data = json.loads(response.read())
            return bool(data.get("ready", True))
    except Exception:
        return False


class Launcher:
    def __init__(self, base_dir: Path, app_dir: Path, data_dir: Path, version: str,
                 preferred_port: int, no_browser: bool, runtime_python: str | None):
        self.base_dir = base_dir
        self.app_dir = app_dir
        self.data_dir = data_dir
        self.version = version
        self.preferred_port = preferred_port
        self.no_browser = no_browser
        self.runtime_python_override = runtime_python

        self.logs_dir = data_dir / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.logs_dir / "launcher.log"
        self.server_out = self.logs_dir / "server.out.log"
        self.server_err = self.logs_dir / "server.err.log"
        self.port_file = data_dir / "port.txt"

        self.runtime_dir = data_dir / "runtime" / version
        self.process: subprocess.Popen | None = None
        self.port: int | None = None
        self.failed = False
        self._out_handle = None
        self._err_handle = None

        self.root = None
        self.status_var = None
        self.detail_var = None
        self.progress = None
        self.buttons = []

    # ---------------------------- 日志 ----------------------------
    def log(self, message: str) -> None:
        line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {message}"
        print(line)
        try:
            with self.log_file.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except OSError:
            pass

    # ---------------------------- UI ----------------------------
    def run(self) -> None:
        import tkinter as tk
        from tkinter import messagebox, ttk

        self.root = tk.Tk()
        self.root.title(APP_TITLE)
        self.root.geometry("480x280")
        self.root.resizable(False, False)
        try:
            self.root.iconbitmap(default="")
        except Exception:
            pass

        frame = ttk.Frame(self.root, padding=20)
        frame.pack(fill="both", expand=True)

        title = ttk.Label(frame, text=APP_TITLE, font=("Microsoft YaHei", 15, "bold"))
        title.pack(anchor="w")
        subtitle = ttk.Label(frame, text="本地 RAG 知识问答 · 首次启动需要初始化运行时", foreground="#666666")
        subtitle.pack(anchor="w", pady=(2, 14))

        self.status_var = tk.StringVar(value="准备启动…")
        status = ttk.Label(frame, textvariable=self.status_var, font=("Microsoft YaHei", 10), wraplength=430)
        status.pack(anchor="w")

        self.detail_var = tk.StringVar(value="")
        detail = ttk.Label(frame, textvariable=self.detail_var, foreground="#888888", wraplength=430)
        detail.pack(anchor="w", pady=(4, 10))

        self.progress = ttk.Progressbar(frame, mode="indeterminate")
        self.progress.pack(fill="x", pady=(0, 16))

        button_row = ttk.Frame(frame)
        button_row.pack(fill="x", side="bottom")
        self.open_button = ttk.Button(button_row, text="打开页面", command=self.open_browser, state="disabled")
        self.open_button.pack(side="left", padx=(0, 8))
        self.log_button = ttk.Button(button_row, text="打开日志", command=self.open_logs)
        self.log_button.pack(side="left", padx=(0, 8))
        self.exit_button = ttk.Button(button_row, text="退出", command=self.on_close)
        self.exit_button.pack(side="right")

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.progress.start(12)

        threading.Thread(target=self._bootstrap, daemon=True).start()
        self.root.mainloop()

    def set_status(self, status: str, detail: str = "") -> None:
        def update():
            self.status_var.set(status)
            self.detail_var.set(detail)

        if self.root:
            self.root.after(0, update)
        else:
            print(status, detail)

    def _bootstrap(self) -> None:
        try:
            # 单实例：已有服务则直接打开浏览器
            if self.port_file.is_file():
                try:
                    existing_port = int(self.port_file.read_text(encoding="utf-8").strip())
                except ValueError:
                    existing_port = None
                if existing_port and health_ok(existing_port):
                    self.port = existing_port
                    self.set_status("服务已在运行", f"http://127.0.0.1:{existing_port}/")
                    if not self.no_browser:
                        self.open_browser()
                    return

            runtime_python = self.prepare_runtime()
            self.start_server(runtime_python)
        except Exception as exc:  # noqa: BLE001
            self.failed = True
            self.log(f"启动失败：{exc}\n{traceback.format_exc()}")
            self.set_status("启动失败", str(exc))
            self.progress_stop()
            if self.root:
                from tkinter import messagebox

                self.root.after(
                    0,
                    lambda: messagebox.showerror(
                        APP_TITLE,
                        f"启动失败：{exc}\n\n日志：{self.log_file}\n服务日志：{self.server_err}",
                    ),
                )

    def run_headless(self, check: bool = False) -> int:
        """无 GUI 模式，便于自动化验证。"""
        self._bootstrap()
        if self.failed:
            self.on_close()
            return 1
        if check:
            self.on_close()
            return 0
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.on_close()
            return 0

    def progress_stop(self) -> None:
        if self.root and self.progress:
            self.root.after(0, self.progress.stop)

    def prepare_runtime(self) -> Path:
        if self.runtime_python_override:
            path = Path(self.runtime_python_override).resolve()
            if not path.is_file():
                raise RuntimeError(f"指定的 Python 不存在：{path}")
            self.log(f"使用开发态 Python：{path}")
            return path

        # 开发态可直接使用项目根下的 runtime/
        local_runtime = self.base_dir / "runtime"
        if (local_runtime / "python.exe").is_file():
            self.log(f"使用本地 runtime：{local_runtime}")
            return local_runtime / "python.exe"

        runtime_python = self.runtime_dir / "python.exe"
        ready = self.runtime_dir / ".ready"
        if runtime_python.is_file() and ready.is_file():
            return runtime_python

        zip_path = self.base_dir / "runtime.zip"
        if not zip_path.is_file():
            raise RuntimeError(f"缺少运行时包：{zip_path}")

        self.set_status("首次初始化运行时…", "正在解压 Python 运行环境，可能需要 1–3 分钟")
        if self.runtime_dir.exists():
            # 不删除用户数据；仅移除不完整的运行时目录
            shutil.rmtree(self.runtime_dir, ignore_errors=True)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(self.runtime_dir)

        runtime_python = self.runtime_dir / "python.exe"
        if not runtime_python.is_file():
            # conda-pack 偶尔会多包一层目录
            nested = list(self.runtime_dir.glob("*/python.exe"))
            if nested:
                nested_root = nested[0].parent
                for item in nested_root.iterdir():
                    shutil.move(str(item), str(self.runtime_dir / item.name))
                nested_root.rmdir()
                runtime_python = self.runtime_dir / "python.exe"
        if not runtime_python.is_file():
            raise RuntimeError("运行时解压后未找到 python.exe")

        self.set_status("初始化运行时…", "正在修正 conda 环境路径（conda-unpack）")
        self.run_conda_unpack(runtime_python)
        ready.write_text(time.strftime("%Y-%m-%d %H:%M:%S"), encoding="utf-8")
        return runtime_python

    def run_conda_unpack(self, runtime_python: Path) -> None:
        commands = [
            # 优先用 python 直接执行脚本：noconsole 启动器下 .exe 包装器可能异常退出
            [str(runtime_python), str(self.runtime_dir / "Scripts" / "conda-unpack-script.py")],
            [str(self.runtime_dir / "Scripts" / "conda-unpack.exe")],
        ]
        last_error = ""
        for command in commands:
            if command[0] and not Path(command[0]).is_file():
                continue
            self.log(f"执行：{' '.join(command)}")
            result = subprocess.run(
                command,
                cwd=str(self.runtime_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode == 0:
                self.log("conda-unpack 成功")
                return
            last_error = (result.stderr or result.stdout or "").strip()
            self.log(f"conda-unpack 失败（退出码 {result.returncode}）：{last_error[:500]}")
        raise RuntimeError(f"conda-unpack 失败：{last_error[:300]}")

    def build_env(self) -> dict:
        env = os.environ.copy()
        for key in ("PYTHONHOME", "PYTHONPATH", "CONDA_PREFIX", "CONDA_DEFAULT_ENV"):
            env.pop(key, None)
        env.update({
            "RAG_DEMO_DATA_DIR": str(self.data_dir),
            "RAG_DEMO_STORAGE_BACKEND": "embedded",
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "TOKENIZERS_PARALLELISM": "false",
            "ANONYMIZED_TELEMETRY": "False",
            "CHROMA_TELEMETRY": "False",
        })
        env.pop("DEEPSEEK_API_KEY", None)
        env.pop("DEEPSEEK_BASE_URL", None)
        env.pop("RAG_DEMO_SEEDS_DIR", None)
        return env

    def start_server(self, runtime_python: Path) -> None:
        self.port = find_free_port(self.preferred_port)
        self.port_file.write_text(str(self.port), encoding="utf-8")
        self.log(f"启动服务：python={runtime_python} port={self.port} cwd={self.app_dir}")

        self._out_handle = self.server_out.open("a", encoding="utf-8", errors="replace")
        self._err_handle = self.server_err.open("a", encoding="utf-8", errors="replace")
        command = [
            str(runtime_python),
            "-m", "uvicorn", "app:app",
            "--host", "127.0.0.1",
            "--port", str(self.port),
            "--log-level", "info",
        ]
        self.process = subprocess.Popen(
            command,
            cwd=str(self.app_dir),
            env=self.build_env(),
            stdout=self._out_handle,
            stderr=self._err_handle,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        self.set_status("正在加载模型…", "首次启动约 15–40 秒，请稍候")
        deadline = time.time() + HEALTH_TIMEOUT
        while time.time() < deadline:
            if self.process.poll() is not None:
                tail = self.tail_log(self.server_err, 12)
                raise RuntimeError(f"服务进程提前退出（{self.process.returncode}）\n{tail}")
            if health_ok(self.port):
                self.log("服务就绪")
                self.set_status("服务已启动", f"http://127.0.0.1:{self.port}/")
                self.progress_stop()
                if self.root:
                    self.root.after(0, lambda: self.open_button.configure(state="normal"))
                if not self.no_browser:
                    self.open_browser()
                return
            elapsed = int(time.time() - (deadline - HEALTH_TIMEOUT))
            self.set_status("正在加载模型…", f"已等待 {elapsed}s，请稍候")
            time.sleep(1)

        raise RuntimeError(f"服务启动超时（{HEALTH_TIMEOUT}s）\n{self.tail_log(self.server_err, 12)}")

    @staticmethod
    def tail_log(path: Path, lines: int) -> str:
        try:
            content = path.read_text(encoding="utf-8", errors="replace").splitlines()
            return "\n".join(content[-lines:])
        except OSError:
            return ""

    def open_browser(self) -> None:
        if self.port:
            webbrowser.open(f"http://127.0.0.1:{self.port}/")

    def open_logs(self) -> None:
        try:
            os.startfile(str(self.logs_dir))  # type: ignore[attr-defined]
        except Exception:
            pass

    def on_close(self) -> None:
        self.log("用户退出，正在停止服务…")
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception:
                try:
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(self.process.pid)],
                        capture_output=True,
                    )
                except Exception:
                    pass
        for handle in (self._out_handle, self._err_handle):
            try:
                handle.close()
            except Exception:
                pass
        if self.root:
            self.root.destroy()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-dir", default=None, help="便携目录根（默认自动推断）")
    parser.add_argument("--data-dir", default=None, help="覆盖用户数据目录")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--headless", action="store_true", help="不显示窗口（自动化测试）")
    parser.add_argument("--check", action="store_true", help="无窗口模式下就绪后立即退出")
    parser.add_argument("--runtime-python", default=None, help="开发态指定 python.exe")
    args = parser.parse_args()

    base_dir = get_base_dir(args.app_dir)
    app_dir = get_app_dir(base_dir)
    data_dir = resolve_data_dir(base_dir, args.data_dir)
    version = read_version(base_dir)
    launcher = Launcher(
        base_dir=base_dir,
        app_dir=app_dir,
        data_dir=data_dir,
        version=version,
        preferred_port=args.port,
        no_browser=args.no_browser,
        runtime_python=args.runtime_python,
    )
    if args.headless or args.check:
        raise SystemExit(launcher.run_headless(check=args.check))
    launcher.run()


if __name__ == "__main__":
    main()

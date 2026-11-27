"""便携包冒烟测试。

用法：
    python packaging/smoke_test.py --base-url http://127.0.0.1:8080 --wait 240
    python packaging/smoke_test.py --base-url http://127.0.0.1:8080 --skip-rag
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def http_json(base_url: str, path: str, method: str = "GET", payload: dict | None = None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def wait_ready(base_url: str, timeout: int) -> dict:
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            return http_json(base_url, "/health")
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(2)
    raise RuntimeError(f"服务在 {timeout}s 内未就绪：{last_error}")


async def ask(base_url: str, query: str, session_id: str, timeout: float = 180.0):
    import websockets

    ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://") + "/api/stream"
    text = ""
    events = []
    async with websockets.connect(ws_url, open_timeout=20) as websocket:
        await websocket.send(json.dumps({
            "query": query,
            "source_filter": None,
            "session_id": session_id,
        }))
        while True:
            message = json.loads(await asyncio.wait_for(websocket.recv(), timeout=timeout))
            event_type = message.get("type")
            events.append(event_type)
            if event_type == "token":
                text += message.get("token", "")
            elif event_type == "end":
                return text, events, None
            elif event_type == "error":
                return text, events, message.get("error", "unknown error")


def pick_faq_question(db_path: Path) -> str | None:
    if not db_path.is_file():
        return None
    connection = sqlite3.connect(str(db_path))
    try:
        row = connection.execute(
            "SELECT question FROM jpkb WHERE question IS NOT NULL AND length(question) > 2 LIMIT 1"
        ).fetchone()
    finally:
        connection.close()
    return row[0] if row else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--wait", type=int, default=240)
    parser.add_argument("--skip-rag", action="store_true")
    parser.add_argument("--faq-db", default=str(ROOT / "packaging" / "seeds" / "faq.sqlite"))
    args = parser.parse_args()

    failures = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        if condition:
            print(f"[PASS] {name}")
        else:
            print(f"[FAIL] {name} {detail}")
            failures.append(name)

    health = wait_ready(args.base_url, args.wait)
    print("health:", health)
    check("health ready", health.get("status") == "healthy")
    check("embedded backend", health.get("storage_backend") == "embedded")

    settings = http_json(args.base_url, "/api/settings")
    check("settings endpoint", "configured" in settings)

    sources = http_json(args.base_url, "/api/sources")
    check("sources endpoint", bool(sources.get("sources")))

    session = http_json(args.base_url, "/api/create_session", "POST", {})
    session_id = session["session_id"]
    check("create session", bool(session_id))

    greeting_text, greeting_events, greeting_error = asyncio.run(
        ask(args.base_url, "你好", session_id, timeout=60)
    )
    check("greeting", bool(greeting_text.strip()) and greeting_error is None,
          f"events={greeting_events} err={greeting_error}")

    faq_question = pick_faq_question(Path(args.faq_db))
    if faq_question:
        faq_text, faq_events, faq_error = asyncio.run(
            ask(args.base_url, faq_question, session_id, timeout=90)
        )
        check("FAQ hit", bool(faq_text.strip()) and faq_error is None,
              f"q={faq_question!r} events={faq_events} err={faq_error}")
    else:
        print("[SKIP] FAQ 种子不存在")

    history = http_json(args.base_url, f"/api/history/{session_id}")
    check("history saved", history.get("total_count", 0) >= 1, str(history))

    if not args.skip_rag:
        if settings.get("configured"):
            rag_text, rag_events, rag_error = asyncio.run(
                ask(args.base_url, "什么是大语言模型？", session_id, timeout=180)
            )
            check("RAG answer", bool(rag_text.strip()) and rag_error is None,
                  f"events={rag_events[:5]}... err={rag_error}")
        else:
            print("[SKIP] LLM 未配置，跳过 RAG 生成测试")

    if failures:
        print(f"\n{len(failures)} 项失败：{', '.join(failures)}")
        return 1
    print("\n全部冒烟检查通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

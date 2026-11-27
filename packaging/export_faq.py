"""从本机 MySQL 导出 FAQ 到便携包使用的 SQLite 种子。

用法（在项目根目录）：
    python packaging/export_faq.py
    python packaging/export_faq.py --output packaging/seeds/faq.sqlite
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def export_faq(output_path: Path) -> int:
    import pymysql

    from base.config import config

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    connection = pymysql.connect(
        host=config.MYSQL_HOST,
        user=config.MYSQL_USER,
        password=config.MYSQL_PASSWORD,
        database=config.MYSQL_DATABASE,
        charset="utf8mb4",
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, subject_name, question, answer FROM jpkb ORDER BY id")
            rows = cursor.fetchall()
    finally:
        connection.close()

    sqlite_conn = sqlite3.connect(str(output_path))
    try:
        sqlite_conn.executescript(
            """
            CREATE TABLE jpkb (
                id INTEGER PRIMARY KEY,
                subject_name TEXT,
                question TEXT,
                answer TEXT
            );
            CREATE INDEX idx_jpkb_question ON jpkb(question);

            CREATE TABLE conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );
            CREATE INDEX idx_conversations_session ON conversations(session_id, timestamp);
            """
        )
        sqlite_conn.executemany(
            "INSERT INTO jpkb (id, subject_name, question, answer) VALUES (?, ?, ?, ?)",
            rows,
        )
        sqlite_conn.commit()
        sqlite_conn.execute("VACUUM")
    finally:
        sqlite_conn.close()

    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default=str(ROOT / "packaging" / "seeds" / "faq.sqlite"),
        help="输出 SQLite 路径",
    )
    args = parser.parse_args()
    output = Path(args.output)
    count = export_faq(output)
    print(f"已导出 {count} 条 FAQ -> {output}")


if __name__ == "__main__":
    main()

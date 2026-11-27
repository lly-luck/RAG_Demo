"""SQLite 实现（便携包默认后端）。

单进程内共享一个连接，用 RLock 串行化写操作；WAL 提升并发读性能。
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from typing import List, Optional

from base.config import config
from base.logger import logger


class SQLiteClient:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = str(db_path or config.SQLITE_PATH)
        self._lock = threading.RLock()
        self.connection = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            timeout=30,
        )
        self.connection.row_factory = sqlite3.Row
        with self._lock:
            self.connection.execute("PRAGMA journal_mode=WAL")
            self.connection.execute("PRAGMA synchronous=NORMAL")
            self.connection.execute("PRAGMA busy_timeout=30000")
            self.connection.execute("PRAGMA foreign_keys=ON")
        self._ensure_schema()
        logger.info("SQLite 连接成功: %s", self.db_path)

    def _ensure_schema(self) -> None:
        with self._lock, self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS jpkb (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject_name TEXT,
                    question TEXT,
                    answer TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_jpkb_question ON jpkb(question);

                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_conversations_session
                    ON conversations(session_id, timestamp);
                """
            )

    # ============================ FAQ ============================
    def fetch_questions(self) -> List[str]:
        try:
            with self._lock:
                rows = self.connection.execute("SELECT question FROM jpkb").fetchall()
            questions = [row[0] for row in rows if row[0] is not None]
            logger.info("总查询到%d条问题", len(questions))
            return questions
        except sqlite3.Error as exc:
            logger.error("问题列表查询失败：%s", exc)
            return []

    def fetch_answer(self, question: str) -> Optional[str]:
        try:
            with self._lock:
                row = self.connection.execute(
                    "SELECT answer FROM jpkb WHERE question = ? LIMIT 1",
                    (question,),
                ).fetchone()
            return row[0] if row else None
        except sqlite3.Error as exc:
            logger.error("答案查询失败：%s", exc)
            return None

    # ============================ 会话历史 ============================
    def fetch_recent_history(self, session_id: str) -> list:
        if not session_id:
            return []
        try:
            with self._lock:
                rows = self.connection.execute(
                    """
                    SELECT question, answer
                    FROM conversations
                    WHERE session_id = ?
                    ORDER BY timestamp DESC, id DESC
                    LIMIT ?
                    """,
                    (session_id, 5),
                ).fetchall()
            history = [{"question": row[0], "answer": row[1]} for row in rows]
            return history[::-1]
        except sqlite3.Error as exc:
            logger.error("获取对话历史失败: %s", exc)
            return []

    def update_session_history(self, session_id: str, question: str, answer: str) -> list:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with self._lock, self.connection:
                self.connection.execute(
                    """
                    INSERT INTO conversations (session_id, question, answer, timestamp)
                    VALUES (?, ?, ?, ?)
                    """,
                    (session_id, question, answer, timestamp),
                )
                self.connection.execute(
                    """
                    DELETE FROM conversations
                    WHERE session_id = ? AND id NOT IN (
                        SELECT id FROM conversations
                        WHERE session_id = ?
                        ORDER BY timestamp DESC, id DESC
                        LIMIT 5
                    )
                    """,
                    (session_id, session_id),
                )
            return self.fetch_recent_history(session_id)
        except sqlite3.Error as exc:
            logger.error("更新会话历史失败: %s", exc)
            raise

    def clear_session_history(self, session_id: str) -> bool:
        try:
            with self._lock, self.connection:
                self.connection.execute(
                    "DELETE FROM conversations WHERE session_id = ?",
                    (session_id,),
                )
            logger.info("会话 %s 历史已清除", session_id)
            return True
        except sqlite3.Error as exc:
            logger.error("清除会话历史失败: %s", exc)
            return False

    def clear_all_sessions_history(self) -> bool:
        try:
            with self._lock, self.connection:
                self.connection.execute("DELETE FROM conversations")
            logger.info("所有会话历史已清除")
            return True
        except sqlite3.Error as exc:
            logger.error("清除所有会话历史失败: %s", exc)
            return False

    def fetch_all_sessions(self) -> list:
        try:
            with self._lock:
                rows = self.connection.execute(
                    """
                    SELECT session_id, COUNT(*) AS count, MAX(timestamp) AS last_time
                    FROM conversations
                    GROUP BY session_id
                    ORDER BY last_time DESC
                    """
                ).fetchall()
            return [
                {
                    "session_id": row[0],
                    "count": row[1],
                    "last_time": row[2] or "",
                }
                for row in rows
            ]
        except sqlite3.Error as exc:
            logger.error("获取会话列表失败: %s", exc)
            return []

    def get_session_count(self, session_id: str) -> int:
        try:
            with self._lock:
                row = self.connection.execute(
                    "SELECT COUNT(*) FROM conversations WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
            return int(row[0]) if row else 0
        except sqlite3.Error as exc:
            logger.error("获取会话总数失败: %s", exc)
            return 0

    def close(self) -> None:
        try:
            with self._lock:
                self.connection.close()
            logger.info("SQLite 连接已关闭")
        except sqlite3.Error as exc:
            logger.error("连接关闭失败: %s", exc)

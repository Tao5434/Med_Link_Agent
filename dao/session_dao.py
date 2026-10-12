"""会话表数据访问（`sessions`：id / user_id / title / create_time / update_time）。

注意：现有表**没有 scene 字段**，场景信息存放在 encounters 与 messages.metadata 中。
"""
from __future__ import annotations

from typing import List, Optional

from utils.db import db


class SessionDao:
    @staticmethod
    def upsert(session_id: str, user_id: str, title: str) -> None:
        """会话不存在则创建，存在则刷新标题与更新时间。"""
        exists = db.query_one("SELECT id FROM sessions WHERE id = %s", (session_id,))
        if exists:
            db.update(
                "UPDATE sessions SET update_time = NOW(), "
                "title = CASE WHEN title IS NULL OR title = '' THEN %s ELSE title END "
                "WHERE id = %s",
                (title, session_id),
            )
        else:
            db.execute(
                "INSERT INTO sessions (id, user_id, title, create_time, update_time) "
                "VALUES (%s, %s, %s, NOW(), NOW())",
                (session_id, user_id, title),
            )

    @staticmethod
    def touch(session_id: str) -> None:
        db.update("UPDATE sessions SET update_time = NOW() WHERE id = %s", (session_id,))

    @staticmethod
    def get(session_id: str) -> Optional[dict]:
        return db.query_one(
            "SELECT id, user_id, title, create_time, update_time FROM sessions WHERE id = %s",
            (session_id,),
        )

    @staticmethod
    def list_by_user(user_id: str, limit: int = 50) -> List[dict]:
        return db.query_all(
            "SELECT s.id, s.user_id, s.title, s.create_time, s.update_time, "
            "       (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.id) AS message_count "
            "FROM sessions s WHERE s.user_id = %s "
            "ORDER BY s.update_time DESC, s.create_time DESC LIMIT %s",
            (user_id, limit),
        )

    @staticmethod
    def delete(session_id: str) -> int:
        """删除会话（同时清理其消息），返回受影响行数。"""
        with db.transaction() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM messages WHERE session_id = %s", (session_id,))
                affected = cur.execute("DELETE FROM sessions WHERE id = %s", (session_id,))
        return affected

    @staticmethod
    def count(user_id: Optional[str] = None) -> int:
        if user_id:
            row = db.query_one("SELECT COUNT(*) AS c FROM sessions WHERE user_id = %s", (user_id,))
        else:
            row = db.query_one("SELECT COUNT(*) AS c FROM sessions")
        return int(row["c"]) if row else 0

    @staticmethod
    def clear_all() -> None:
        with db.transaction() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM messages")
                cur.execute("DELETE FROM sessions")

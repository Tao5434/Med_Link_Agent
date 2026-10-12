"""会话消息表数据访问（`messages`：id / session_id / role / content / metadata / create_time）。

注意：现有表**没有 user_id 字段**，用户归属通过 ``sessions.user_id`` 关联。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from config.settings import settings
from utils.db import db


class MessageDao:
    @staticmethod
    def add(
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        return db.insert_one(
            "INSERT INTO messages (session_id, role, content, metadata, create_time) "
            "VALUES (%s, %s, %s, %s, NOW())",
            (
                session_id,
                role,
                content,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )

    @staticmethod
    def list_by_session(session_id: str, limit: Optional[int] = None) -> List[dict]:
        """按时间正序返回最近 limit 条消息。"""
        limit = limit or settings.HISTORY_MESSAGES_LIMIT
        rows = db.query_all(
            "SELECT id, session_id, role, content, metadata, create_time FROM messages "
            "WHERE session_id = %s ORDER BY id DESC LIMIT %s",
            (session_id, limit),
        )
        rows.reverse()
        return [MessageDao._decode(r) for r in rows]

    @staticmethod
    def recent(session_id: str, limit: Optional[int] = None) -> List[dict]:
        """最近 N 条对话记忆（需求 3.2）。"""
        return MessageDao.list_by_session(session_id, limit or settings.HISTORY_MEMORY_LIMIT)

    @staticmethod
    def _decode(row: dict) -> dict:
        row["metadata"] = _loads(row.get("metadata"))
        return row

    @staticmethod
    def delete_by_session(session_id: str) -> int:
        return db.delete("DELETE FROM messages WHERE session_id = %s", (session_id,))

    @staticmethod
    def count(user_id: Optional[str] = None) -> int:
        if user_id:
            row = db.query_one(
                "SELECT COUNT(*) AS c FROM messages m JOIN sessions s ON s.id = m.session_id "
                "WHERE s.user_id = %s",
                (user_id,),
            )
        else:
            row = db.query_one("SELECT COUNT(*) AS c FROM messages")
        return int(row["c"]) if row else 0


def _loads(value: Any) -> Any:
    """MySQL JSON 列在 pymysql 中以字符串返回，这里统一反序列化。"""
    if value is None:
        return {}
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return {}

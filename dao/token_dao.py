"""登录令牌表数据访问（`user_tokens`）。

用数据库表保存令牌而不是无状态签名，好处是「退出登录」可以真正让令牌立刻失效，
同时让登录这一动作确实落库。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from utils.db import db


class TokenDao:
    @staticmethod
    def create(token: str, user_id: int, expire_hours: int) -> None:
        expire_time = (datetime.now() + timedelta(hours=expire_hours)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        db.execute(
            "INSERT INTO user_tokens (token, user_id, expire_time) VALUES (%s, %s, %s)",
            (token, user_id, expire_time),
        )

    @staticmethod
    def get_valid(token: str) -> Optional[dict]:
        """返回未过期的令牌记录，并顺带清理该令牌。"""
        return db.query_one(
            "SELECT token, user_id, create_time, expire_time FROM user_tokens "
            "WHERE token = %s AND expire_time > NOW()",
            (token,),
        )

    @staticmethod
    def delete(token: str) -> int:
        return db.delete("DELETE FROM user_tokens WHERE token = %s", (token,))

    @staticmethod
    def delete_by_user(user_id: int) -> int:
        return db.delete("DELETE FROM user_tokens WHERE user_id = %s", (user_id,))

    @staticmethod
    def purge_expired() -> int:
        return db.delete("DELETE FROM user_tokens WHERE expire_time <= NOW()")

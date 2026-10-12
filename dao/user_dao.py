"""用户表数据访问（`user` 表：id / account / password / create_time）。

密码沿用现有库的 MD5 存储方式（现有 admin 记录的 password 即 MD5("123456")）。
"""
from __future__ import annotations

from typing import Optional

from utils.db import db


class UserDao:
    @staticmethod
    def get_by_account(account: str) -> Optional[dict]:
        return db.query_one(
            "SELECT id, account, password, create_time FROM `user` WHERE account = %s",
            (account,),
        )

    @staticmethod
    def get_by_id(user_id: int) -> Optional[dict]:
        return db.query_one(
            "SELECT id, account, password, create_time FROM `user` WHERE id = %s",
            (user_id,),
        )

    @staticmethod
    def create(account: str, password_md5: str) -> int:
        return db.insert_one(
            "INSERT INTO `user` (account, password) VALUES (%s, %s)",
            (account, password_md5),
        )

    @staticmethod
    def update_password(user_id: int, password_md5: str) -> int:
        return db.update(
            "UPDATE `user` SET password = %s WHERE id = %s", (password_md5, user_id)
        )

    @staticmethod
    def count() -> int:
        row = db.query_one("SELECT COUNT(*) AS c FROM `user`")
        return int(row["c"]) if row else 0

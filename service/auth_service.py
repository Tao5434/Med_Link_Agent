"""登录 / 注册 / 退出 / 用户资料服务。

账号密码校验完全基于数据库 ``user`` 表：注册写一条 ``user`` 记录，
登录比对 MD5 密码并签发一条 ``user_tokens`` 记录。
"""
from __future__ import annotations

import re
import uuid
from typing import Optional

from config.settings import settings
from dao.appointment_dao import AppointmentDao
from dao.encounter_dao import EncounterDao
from dao.session_dao import SessionDao
from dao.token_dao import TokenDao
from dao.user_dao import UserDao
from schema.dto.user_dto import UserLoginDto, UserRegisterDto
from utils.function import md5_encrypt

ACCOUNT_RE = re.compile(r"^[A-Za-z0-9_@.\-]{3,32}$")


class AuthError(ValueError):
    """业务校验失败（对应用户可见的提示）。"""


class AuthService:
    # ------------------------------------------------------------------
    @staticmethod
    def _issue_token(user_id: int) -> dict:
        token = uuid.uuid4().hex + uuid.uuid4().hex[:32]
        TokenDao.purge_expired()
        TokenDao.create(token, user_id, settings.AUTH_TOKEN_EXPIRE_HOURS)
        return {"token": token, "expires_in_hours": settings.AUTH_TOKEN_EXPIRE_HOURS}

    @staticmethod
    def _payload(user: dict, token_info: dict) -> dict:
        return {
            "user_id": str(user["id"]),
            "user_pk": int(user["id"]),
            "account": user["account"],
            "token": token_info["token"],
            "expires_in_hours": token_info["expires_in_hours"],
            "create_time": str(user.get("create_time") or ""),
        }

    # ------------------------------------------------------------------
    @staticmethod
    def register(dto: UserRegisterDto) -> dict:
        account = (dto.account or "").strip()
        password = dto.password or ""

        if not ACCOUNT_RE.match(account):
            raise AuthError("账号需为 3~32 位字母、数字或 _ @ . - 组合")
        if len(password) < 6:
            raise AuthError("密码长度不能少于 6 位")
        if UserDao.get_by_account(account):
            raise AuthError("该账号已被注册，请更换账号")

        user_id = UserDao.create(account, md5_encrypt(password))
        user = UserDao.get_by_id(user_id)
        return AuthService._payload(user, AuthService._issue_token(user_id))

    @staticmethod
    def login(dto: UserLoginDto) -> dict:
        account = (dto.account or "").strip()
        password = dto.password or ""
        if not account or not password:
            raise AuthError("请输入账号和密码")

        user = UserDao.get_by_account(account)
        if not user or user["password"] != md5_encrypt(password):
            raise AuthError("账号或密码错误")

        return AuthService._payload(user, AuthService._issue_token(int(user["id"])))

    @staticmethod
    def logout(token: Optional[str]) -> bool:
        if not token:
            return False
        return TokenDao.delete(token) > 0

    @staticmethod
    def profile(user: dict) -> dict:
        user_id = user["user_id"]
        return {
            "user_id": user_id,
            "user_pk": user["user_pk"],
            "account": user["account"],
            "token_expire_time": str(user.get("token_expire_time") or ""),
            "stats": {
                "sessions": SessionDao.count(user_id),
                "encounters": EncounterDao.count(user_id),
                "appointments": AppointmentDao.count(user_id),
            },
        }

    @staticmethod
    def change_password(user: dict, old_password: str, new_password: str) -> None:
        row = UserDao.get_by_id(user["user_pk"])
        if not row or row["password"] != md5_encrypt(old_password or ""):
            raise AuthError("原密码不正确")
        if len(new_password or "") < 6:
            raise AuthError("新密码长度不能少于 6 位")
        UserDao.update_password(user["user_pk"], md5_encrypt(new_password))
        # 改密后使其余令牌失效
        TokenDao.delete_by_user(user["user_pk"])

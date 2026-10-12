"""登录鉴权：Bearer 令牌解析与当前用户依赖。

令牌存放在 ``user_tokens`` 表中，因此「退出登录」可以真正让令牌立即失效。
"""
from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException

from dao.token_dao import TokenDao
from dao.user_dao import UserDao


def parse_bearer(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return authorization.strip() or None


def resolve_user(authorization: Optional[str]) -> Optional[dict]:
    """根据 Authorization 头解析当前用户，失败返回 None。"""
    token = parse_bearer(authorization)
    if not token:
        return None
    record = TokenDao.get_valid(token)
    if not record:
        return None
    user = UserDao.get_by_id(record["user_id"])
    if not user:
        return None
    return {
        "user_id": str(user["id"]),          # char(36) 业务表使用的用户标识
        "user_pk": int(user["id"]),          # health_profiles.user_id 使用 int
        "account": user["account"],
        "token": token,
        "token_expire_time": record.get("expire_time"),
    }


def current_user(authorization: Optional[str] = Header(None)) -> dict:
    """FastAPI 依赖：要求已登录。"""
    user = resolve_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="未登录或登录状态已过期，请重新登录")
    return user


def optional_user(authorization: Optional[str] = Header(None)) -> Optional[dict]:
    """FastAPI 依赖：登录可选。"""
    return resolve_user(authorization)

"""会话与数据管理接口（需求 4.2）。全部需要登录，且只能操作自己的数据。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from config.settings import settings
from dao.message_dao import MessageDao
from dao.session_dao import SessionDao
from service.settings_service import SettingsService
from utils.response_model import error_message, success_data, success_data_message
from utils.security import current_user

session_router = APIRouter(prefix="/api/sessions", tags=["会话管理"])


@session_router.get("", summary="我的会话列表")
async def list_sessions(
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
    user: dict = Depends(current_user),
):
    rows = SessionDao.list_by_user(user["user_id"], limit)
    return success_data({"sessions": rows, "total": len(rows)})


@session_router.get("/{session_id}/messages", summary="会话消息（最多 100 条）")
async def session_messages(
    session_id: str,
    limit: int = Query(None, ge=1, le=100, description="返回条数，默认 20，上限 100"),
    user: dict = Depends(current_user),
):
    session = SessionDao.get(session_id)
    if not session or session.get("user_id") != user["user_id"]:
        return error_message("会话不存在")
    rows = MessageDao.list_by_session(session_id, limit or settings.DEFAULT_MESSAGES_LIMIT)
    return success_data({"session": session, "messages": rows, "total": len(rows)})


@session_router.delete("/{session_id}", summary="删除指定会话")
async def delete_session(session_id: str, user: dict = Depends(current_user)):
    session = SessionDao.get(session_id)
    if not session or session.get("user_id") != user["user_id"]:
        return error_message("会话不存在")
    SessionDao.delete(session_id)
    return success_data_message({"ok": True, "session_id": session_id}, "删除成功")


@session_router.delete("", summary="清空全部数据")
async def clear_all(user: dict = Depends(current_user)):
    """清空 sessions / messages / encounters / appointments 等表。

    普通用户仅清理自己的数据；管理员账号（``admin``）执行全库清理。
    """
    return success_data_message(
        SettingsService.clear_all(user), "已清空全部数据"
    )

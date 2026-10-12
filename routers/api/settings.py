"""系统设置与平台指标接口（需求 3.7）。需登录；指标按当前用户统计。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from service.settings_service import SettingsService
from utils.response_model import success_data
from utils.security import current_user

settings_router = APIRouter(prefix="/api", tags=["系统设置"])


@settings_router.get("/settings", summary="系统设置状态")
async def get_settings(user: dict = Depends(current_user)):
    data = SettingsService.get_settings()
    data["current_user"] = {"user_id": user["user_id"], "account": user["account"]}
    return success_data(data)


@settings_router.get("/metrics", summary="平台指标（当前用户）")
async def get_metrics(user: dict = Depends(current_user)):
    return success_data(SettingsService.metrics(user["user_id"]))

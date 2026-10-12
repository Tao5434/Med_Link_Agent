"""问诊记录接口（需求 3.5 FR-RECORD）。仅返回当前登录用户的记录。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from config.settings import settings
from service.record_service import RecordService
from utils.response_model import error_message, success_data
from utils.security import current_user

record_router = APIRouter(prefix="/api/records", tags=["问诊记录"])


@record_router.get("", summary="我的问诊记录（近 7/30/180 天）")
async def list_records(
    days: int = Query(settings.RECORD_DEFAULT_DAYS, ge=1, le=365, description="统计天数"),
    limit: int = Query(200, ge=1, le=500, description="返回条数"),
    user: dict = Depends(current_user),
):
    records = RecordService.list_records(user["user_id"], days, limit)
    return success_data({"records": records, "total": len(records), "days": days})


@record_router.get("/{record_id}", summary="问诊记录详情")
async def record_detail(record_id: int, user: dict = Depends(current_user)):
    record = RecordService.get_record(record_id, user["user_id"])
    if not record:
        return error_message("记录不存在")
    return success_data(record)

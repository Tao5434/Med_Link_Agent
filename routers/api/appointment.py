"""预约挂号接口（需求 3.6）。用户身份取自登录令牌。

注意：``appointments`` 表没有 fee 字段，挂号费按医生职称派生后返回。
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from config.settings import settings
from schema.dto.appointment_dto import AppointmentCreateDto
from service.appointment_service import AppointmentService
from utils.response_model import success_data, success_data_message
from utils.security import current_user

appointment_router = APIRouter(prefix="/api/appointments", tags=["预约挂号"])


@appointment_router.get("/schedule", summary="科室排班（未来 N 天上午/下午号源）")
async def schedule(
    department: str = Query(..., description="科室名称"),
    days: int = Query(settings.APPOINTMENT_SCHEDULE_DAYS, ge=1, le=30, description="排班天数"),
    user: dict = Depends(current_user),
):
    data = AppointmentService.schedule_for_department(department, user["user_id"], days)
    data["appointments"] = AppointmentService.list_by_user(user["user_id"])
    return success_data(data)


@appointment_router.post("", summary="创建预约")
async def create_appointment(dto: AppointmentCreateDto, user: dict = Depends(current_user)):
    result = AppointmentService.create(
        user_id=user["user_id"],
        department=dto.department,
        doctor=dto.doctor,
        visit_date=dto.visit_date,
        period=dto.period,
        doctor_title=dto.doctor_title or "",
        time_slot=dto.time_slot or "",
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("message", "预约失败"))
    return success_data_message(result, result.get("message", "预约成功"))


@appointment_router.get("", summary="我的预约")
async def list_appointments(user: dict = Depends(current_user)):
    appointments = AppointmentService.list_by_user(user["user_id"])
    return success_data({"appointments": appointments, "total": len(appointments)})


@appointment_router.delete("/{appointment_id}", summary="取消预约")
async def cancel_appointment(appointment_id: int, user: dict = Depends(current_user)):
    result = AppointmentService.cancel(appointment_id, user["user_id"])
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("message", "取消失败"))
    return success_data_message(result, result.get("message", "已取消预约"))


@appointment_router.post("/intent", summary="预约意图识别（扩展）")
async def parse_intent(
    payload: dict = Body(..., examples=[{"message": "帮我挂明天上午消化科的号"}]),
    user: dict = Depends(current_user),
):
    message = str(payload.get("message") or "")
    intent = AppointmentService.parse_intent(message)
    if not AppointmentService.detect_intent(message):
        return success_data({"is_appointment_intent": False, "intent": intent})
    return success_data({"is_appointment_intent": True, "intent": intent})

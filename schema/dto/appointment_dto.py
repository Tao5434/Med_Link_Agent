"""预约挂号相关 DTO。"""
from typing import Optional

from pydantic import BaseModel, Field


class AppointmentCreateDto(BaseModel):
    user_id: Optional[str] = Field(None, description="用户ID")
    department: str = Field(..., description="科室名称")
    doctor: str = Field(..., description="医生姓名")
    visit_date: str = Field(..., description="就诊日期 YYYY-MM-DD")
    period: str = Field(..., description="时段：上午/下午")
    doctor_title: Optional[str] = Field(None, description="医生职称")
    time_slot: Optional[str] = Field(None, description="时间段，如 08:30-11:30")
    fee: Optional[float] = Field(None, description="挂号费")

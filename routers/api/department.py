"""科室接口。科室列表直接读取 ``departments`` 表（当前 16 个，含急诊科）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from dao.departments_dao import DepartmentsDao
from dao.doctor_schedule_dao import DoctorScheduleDao
from utils.response_model import success_data
from utils.security import current_user

department_router = APIRouter(prefix="/api/departments", tags=["科室"])


@department_router.get("", summary="科室列表")
async def list_departments(user: dict = Depends(current_user)):
    rows = DepartmentsDao.list_active()
    return success_data(
        {
            "departments": rows,
            "names": [r["department_name"] for r in rows],
            "total": len(rows),
        }
    )


@department_router.get("/schedules", summary="全部医生排班号源")
async def list_schedules(user: dict = Depends(current_user)):
    rows = DoctorScheduleDao.list_all()
    return success_data({"schedules": rows, "total": len(rows)})

"""预约挂号服务（需求 3.6 FR-APPOINTMENT）。

排班数据来源：
* 医生花名册与总号源 → 数据库 ``doctor_schedules``（每科室 2 名医生，含 total_slots）；
* 剩余号源 → 由 ``appointments`` 表实时统计（status='booked'）；
* 每次预约 / 取消后回写 ``doctor_schedules.booked_slots``，保持计数器与明细一致。

挂号费：``appointments`` 表没有 fee 字段，按医生职称派生（主任医师 50 / 副主任医师 35）。
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Dict, List, Optional

from config.settings import settings
from dao.appointment_dao import AppointmentDao
from dao.departments_dao import DepartmentsDao
from dao.doctor_schedule_dao import DoctorScheduleDao
from utils.enums import STATUS_BOOKED, period_from_db, period_to_db, status_from_db
from utils.function import date_after, weekday_cn
from utils.schema import DEFAULT_FEE, TITLE_FEE

PERIOD_TIME_SLOT = {"上午": "08:30-11:30", "下午": "14:00-17:00"}
PERIODS = list(PERIOD_TIME_SLOT.keys())


class AppointmentService:
    # ------------------------------------------------------------------
    # 排班
    # ------------------------------------------------------------------
    @staticmethod
    def schedule_for_department(department: str, user_id: str = None, days: int = None) -> Dict:
        """基于医生排班表生成某科室未来 N 天的号源。"""
        department = DepartmentsDao.normalize(department) if department else "内科"
        days = max(1, min(days or settings.APPOINTMENT_SCHEDULE_DAYS, 30))

        dept_code = DepartmentsDao.code_of(department)
        roster = DoctorScheduleDao.list_by_department_code(dept_code) if dept_code else []

        schedules: List[Dict] = []
        if not roster:
            # 该科室尚无排班记录：返回空列表，前端提示暂无可预约号源
            return {"department": department, "department_code": dept_code, "days": days,
                    "doctors": [], "schedules": []}

        for offset in range(days):
            date_str = date_after(offset)
            for index, period in enumerate(PERIODS):
                # 上/下午轮流出诊，保证同一天两个时段医生不同
                doctor_row = roster[offset % len(roster)] if index == 0 else roster[(offset + 1) % len(roster)]
                quota = int(doctor_row["total_slots"] or 0)
                booked = AppointmentDao.booked_count(
                    department, doctor_row["doctor"], date_str, period
                )
                remaining = max(0, quota - booked)
                title = doctor_row["doctor_title"] or ""
                schedules.append(
                    {
                        "schedule_id": doctor_row["id"],
                        "department": department,
                        "department_code": dept_code,
                        "doctor": doctor_row["doctor"],
                        "doctor_title": title,
                        "visit_date": date_str,
                        "weekday": weekday_cn(date_str),
                        "period": period,
                        "time_slot": PERIOD_TIME_SLOT[period],
                        "quota": quota,
                        "booked": booked,
                        "remaining": remaining,
                        "fee": TITLE_FEE.get(title, DEFAULT_FEE),
                        "available": remaining > 0,
                    }
                )

        return {
            "department": department,
            "department_code": dept_code,
            "days": days,
            "doctors": roster,
            "schedules": schedules,
        }

    # ------------------------------------------------------------------
    # 预约 / 取消
    # ------------------------------------------------------------------
    @staticmethod
    def create(
        user_id: str,
        department: str,
        doctor: str,
        visit_date: str,
        period: str,
        doctor_title: str = "",
        time_slot: str = "",
    ) -> Dict:
        """创建预约。返回 {ok, appointment_id, code, deduplicated, appointments}。"""
        department = DepartmentsDao.normalize(department)

        # 幂等：相同（用户+科室+医生+日期+时段）已预约则直接返回既有记录
        existing = AppointmentDao.find_active(user_id, department, doctor, visit_date, period)
        if existing:
            return {
                "ok": True,
                "appointment_id": existing["id"],
                "code": f"YL{int(existing['id']):06d}",
                "deduplicated": True,
                "message": "该号源您已预约，已为您返回原预约记录",
                "appointments": AppointmentService.list_by_user(user_id),
            }

        slot = AppointmentService._find_slot(department, doctor, visit_date, period)
        if slot is None:
            return {
                "ok": False,
                "message": "未找到对应的排班号源，请重新选择科室与时段",
                "appointments": AppointmentService.list_by_user(user_id),
            }
        if slot["remaining"] <= 0:
            return {
                "ok": False,
                "message": "当前号源已约满",
                "appointments": AppointmentService.list_by_user(user_id),
            }

        doctor_title = doctor_title or slot["doctor_title"]
        time_slot = time_slot or slot["time_slot"]

        new_id = AppointmentDao.add(
            user_id=user_id,
            department=department,
            doctor=doctor,
            doctor_title=doctor_title,
            visit_date=visit_date,
            period=period,
            time_slot=time_slot,
        )
        # 回写医生已预约数
        DoctorScheduleDao.recompute_booked(department, doctor)

        return {
            "ok": True,
            "appointment_id": new_id,
            "code": f"YL{int(new_id):06d}",
            "deduplicated": False,
            "message": "预约成功",
            "appointments": AppointmentService.list_by_user(user_id),
        }

    @staticmethod
    def cancel(appointment_id: int, user_id: str = None) -> Dict:
        """取消预约（仅 status='booked' 生效）。"""
        record = AppointmentDao.get(appointment_id)
        if not record:
            return {"ok": False, "message": "预约记录不存在"}
        if user_id and record.get("user_id") != user_id:
            return {"ok": False, "message": "无权操作该预约记录"}
        if record.get("status") != STATUS_BOOKED:
            return {"ok": False, "message": "该预约已取消，无需重复操作"}

        affected = AppointmentDao.cancel(appointment_id)
        if affected:
            DoctorScheduleDao.recompute_booked(record["department"], record["doctor"])
        return {
            "ok": affected > 0,
            "message": "已取消预约" if affected else "取消失败",
            "appointments": AppointmentService.list_by_user(user_id or record.get("user_id")),
        }

    @staticmethod
    def list_by_user(user_id: str) -> List[dict]:
        rows = AppointmentDao.list_by_user(user_id)
        return [AppointmentService._to_card(r) for r in rows]

    # ------------------------------------------------------------------
    # 扩展：预约意图识别
    # ------------------------------------------------------------------
    INTENT_KEYWORDS = ["预约", "挂号", "挂个号", "挂个", "约个号", "帮我挂", "帮我约", "排班", "号源"]

    @staticmethod
    def detect_intent(text: str) -> bool:
        return any(kw in (text or "") for kw in AppointmentService.INTENT_KEYWORDS)

    @staticmethod
    def parse_intent(text: str) -> Dict:
        from agent import rules

        text = text or ""
        department, hits, _ = rules.match_department(text)
        if not DepartmentsDao.exists(department):
            department = "内科"

        visit_date = ""
        if "今天" in text:
            visit_date = date_after(0)
        elif "明天" in text:
            visit_date = date_after(1)
        elif "后天" in text:
            visit_date = date_after(2)
        else:
            m = re.search(r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})", text)
            if m:
                visit_date = m.group(1).replace("/", "-")
            else:
                m = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]", text)
                if m:
                    visit_date = f"{datetime.now().year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"

        period = ""
        if "上午" in text or "早上" in text:
            period = "上午"
        elif "下午" in text or "晚上" in text:
            period = "下午"

        return {
            "department": department,
            "visit_date": visit_date,
            "period": period,
            "symptom_hits": hits,
            "complete": bool(department and visit_date and period),
        }

    # ------------------------------------------------------------------
    @staticmethod
    def _find_slot(department: str, doctor: str, visit_date: str, period: str) -> Optional[Dict]:
        schedule = AppointmentService.schedule_for_department(department)
        for slot in schedule["schedules"]:
            if (
                slot["doctor"] == doctor
                and slot["visit_date"] == visit_date
                and slot["period"] == period
            ):
                return slot
        return None

    @staticmethod
    def _to_card(row: Dict) -> Dict:
        title = row.get("doctor_title") or ""
        return {
            "id": row.get("id"),
            "code": f"YL{int(row['id']):06d}" if row.get("id") else "",
            "user_id": row.get("user_id"),
            "department": row.get("department"),
            "doctor": row.get("doctor"),
            "doctor_title": title,
            "visit_date": str(row.get("visit_date") or ""),
            "weekday": weekday_cn(str(row.get("visit_date") or "")),
            "period": period_from_db(row.get("period")),
            "time_slot": row.get("time_slot"),
            "fee": TITLE_FEE.get(title, DEFAULT_FEE),
            "status": status_from_db(row.get("status")),
            "cancellable": row.get("status") == STATUS_BOOKED,
            "created_at": str(row.get("create_time") or ""),
        }


# 便于外部直接使用
_ = period_to_db

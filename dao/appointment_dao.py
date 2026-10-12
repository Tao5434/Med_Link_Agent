"""预约表数据访问（`appointments`）。

字段：id / user_id / department / doctor / doctor_title /
      visit_date(DATE) / period / time_slot / status / create_time / update_time

注意：现有表**没有 fee 字段**，挂号费按医生职称在前端/服务层派生。

每次预约或取消后，都会重算对应医生的 ``doctor_schedules.booked_slots``，
保证「已预约数」与 appointments 表始终一致。
"""
from __future__ import annotations

from typing import List, Optional

from utils.db import db
from utils.enums import STATUS_BOOKED, STATUS_CANCELLED, period_to_db


class AppointmentDao:
    @staticmethod
    def add(
        user_id: str,
        department: str,
        doctor: str,
        doctor_title: str,
        visit_date: str,
        period: str,
        time_slot: str,
    ) -> int:
        return db.insert_one(
            "INSERT INTO appointments (user_id, department, doctor, doctor_title, visit_date, "
            "period, time_slot, status, create_time, update_time) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())",
            (
                user_id,
                department,
                doctor,
                doctor_title,
                visit_date,
                period_to_db(period),
                time_slot,
                STATUS_BOOKED,
            ),
        )

    @staticmethod
    def find_active(
        user_id: str, department: str, doctor: str, visit_date: str, period: str
    ) -> Optional[dict]:
        """幂等去重：相同（用户+科室+医生+日期+时段）的「已预约」记录。"""
        return db.query_one(
            "SELECT * FROM appointments WHERE user_id = %s AND department = %s AND doctor = %s "
            "AND visit_date = %s AND period = %s AND status = %s",
            (user_id, department, doctor, visit_date, period_to_db(period), STATUS_BOOKED),
        )

    @staticmethod
    def get(appointment_id: int) -> Optional[dict]:
        return db.query_one("SELECT * FROM appointments WHERE id = %s", (appointment_id,))

    @staticmethod
    def list_by_user(user_id: str, limit: int = 100) -> List[dict]:
        return db.query_all(
            "SELECT * FROM appointments WHERE user_id = %s "
            "ORDER BY visit_date DESC, id DESC LIMIT %s",
            (user_id, limit),
        )

    @staticmethod
    def booked_count(department: str, doctor: str, visit_date: str, period: str) -> int:
        row = db.query_one(
            "SELECT COUNT(*) AS c FROM appointments WHERE department = %s AND doctor = %s "
            "AND visit_date = %s AND period = %s AND status = %s",
            (department, doctor, visit_date, period_to_db(period), STATUS_BOOKED),
        )
        return int(row["c"]) if row else 0

    @staticmethod
    def cancel(appointment_id: int) -> int:
        """取消仅对 status='booked' 的记录生效。"""
        return db.update(
            "UPDATE appointments SET status = %s, update_time = NOW() "
            "WHERE id = %s AND status = %s",
            (STATUS_CANCELLED, appointment_id, STATUS_BOOKED),
        )

    @staticmethod
    def count(user_id: Optional[str] = None) -> int:
        if user_id:
            row = db.query_one(
                "SELECT COUNT(*) AS c FROM appointments WHERE user_id = %s AND status = %s",
                (user_id, STATUS_BOOKED),
            )
        else:
            row = db.query_one("SELECT COUNT(*) AS c FROM appointments")
        return int(row["c"]) if row else 0

    @staticmethod
    def clear_all() -> None:
        db.delete("DELETE FROM appointments")

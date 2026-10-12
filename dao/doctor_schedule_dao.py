"""医生排班号源表数据访问（`doctor_schedules`）。

字段：id / department_code / doctor / doctor_title /
      total_slots / booked_slots / is_active / create_time / update_time

本表是「科室 → 出诊医生 + 每人总号源」的花名册；具体某一天上午/下午的剩余号源，
由 appointments 表实时统计得出，并回写 ``booked_slots`` 保持两者一致。
"""
from __future__ import annotations

from typing import List, Optional

from utils.db import db
from utils.enums import STATUS_BOOKED


class DoctorScheduleDao:
    @staticmethod
    def list_by_department_code(department_code: str) -> List[dict]:
        return db.query_all(
            "SELECT id, department_code, doctor, doctor_title, total_slots, booked_slots, is_active "
            "FROM doctor_schedules WHERE department_code = %s AND is_active = 1 ORDER BY id ASC",
            (department_code,),
        )

    @staticmethod
    def get_by_id(schedule_id: int) -> Optional[dict]:
        return db.query_one(
            "SELECT id, department_code, doctor, doctor_title, total_slots, booked_slots, is_active "
            "FROM doctor_schedules WHERE id = %s",
            (schedule_id,),
        )

    @staticmethod
    def list_all() -> List[dict]:
        return db.query_all(
            "SELECT ds.id, ds.department_code, d.department_name, ds.doctor, ds.doctor_title, "
            "ds.total_slots, ds.booked_slots FROM doctor_schedules ds "
            "LEFT JOIN departments d ON d.department_code = ds.department_code "
            "WHERE ds.is_active = 1 ORDER BY d.sort_order ASC, ds.id ASC"
        )

    @staticmethod
    def recompute_booked(department: str, doctor: str) -> int:
        """把某医生的已预约数重算并写回 ``booked_slots``。

        以 appointments 表（status='booked'）为唯一事实来源，避免计数器漂移。
        """
        return db.update(
            "UPDATE doctor_schedules ds SET ds.booked_slots = ("
            "  SELECT COUNT(*) FROM appointments a "
            "  WHERE a.department = %s AND a.doctor = ds.doctor AND a.status = %s"
            ") WHERE ds.doctor = %s "
            "  AND ds.department_code = ("
            "    SELECT d.department_code FROM departments d WHERE d.department_name = %s LIMIT 1"
            "  )",
            (department, STATUS_BOOKED, doctor, department),
        )

    @staticmethod
    def remaining_for(department: str, doctor: str, visit_date: str, period_db: str) -> int:
        """某医生某天某时段的剩余号源 = total_slots − 已预约数。"""
        row = db.query_one(
            "SELECT ds.total_slots, ("
            "  SELECT COUNT(*) FROM appointments a "
            "  WHERE a.department = %s AND a.doctor = ds.doctor "
            "    AND a.visit_date = %s AND a.period = %s AND a.status = %s"
            ") AS booked FROM doctor_schedules ds "
            "JOIN departments d ON d.department_code = ds.department_code "
            "WHERE d.department_name = %s AND ds.doctor = %s AND ds.is_active = 1 LIMIT 1",
            (department, visit_date, period_db, STATUS_BOOKED, department, doctor),
        )
        if not row:
            return 0
        return max(0, int(row["total_slots"] or 0) - int(row["booked"] or 0))

    @staticmethod
    def count() -> int:
        row = db.query_one("SELECT COUNT(*) AS c FROM doctor_schedules")
        return int(row["c"]) if row else 0

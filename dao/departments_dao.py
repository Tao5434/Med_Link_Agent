"""科室字典表数据访问（`departments`）。

科室列表以**数据库为准**（当前库中 16 个，含急诊科），不再硬编码在配置里；
``config.settings.DEPARTMENTS`` 仅作为数据库不可用时的兜底。
"""
from __future__ import annotations

import threading
import time
from typing import List, Optional

from config.settings import settings
from utils.db import DatabaseError, db

_CACHE_TTL = 60
_cache: dict = {"names": None, "rows": None, "at": 0.0}
_lock = threading.Lock()


class DepartmentsDao:
    @staticmethod
    def list_active(force: bool = False) -> List[dict]:
        """启用中的科室，按 sort_order 排序。"""
        now = time.time()
        if not force and _cache["rows"] and now - _cache["at"] < _CACHE_TTL:
            return _cache["rows"]
        try:
            rows = db.query_all(
                "SELECT id, department_code, department_name, sort_order, is_active "
                "FROM departments WHERE is_active = 1 ORDER BY sort_order ASC, id ASC"
            )
        except DatabaseError:
            rows = []
        if not rows:
            # 兜底：数据库不可用时使用配置常量，保证分诊链路不中断
            rows = [
                {
                    "id": i + 1,
                    "department_code": f"D{i + 1:03d}",
                    "department_name": name,
                    "sort_order": i + 1,
                    "is_active": 1,
                }
                for i, name in enumerate(settings.DEPARTMENTS)
            ]
        with _lock:
            _cache.update({"rows": rows, "names": [r["department_name"] for r in rows], "at": now})
        return rows

    @staticmethod
    def get_names(force: bool = False) -> List[str]:
        rows = DepartmentsDao.list_active(force)
        return [r["department_name"] for r in rows]

    @staticmethod
    def get_by_name(name: str) -> Optional[dict]:
        for row in DepartmentsDao.list_active():
            if row["department_name"] == name:
                return row
        return None

    @staticmethod
    def get_by_code(code: str) -> Optional[dict]:
        for row in DepartmentsDao.list_active():
            if row["department_code"] == code:
                return row
        return None

    @staticmethod
    def code_of(name: str) -> str:
        row = DepartmentsDao.get_by_name(name)
        if row:
            return row["department_code"]
        try:
            return db.query_one(
                "SELECT department_code FROM departments WHERE department_name = %s", (name,)
            )["department_code"]
        except Exception:  # noqa: BLE001
            return ""

    @staticmethod
    def name_of(code: str) -> str:
        row = DepartmentsDao.get_by_code(code)
        return row["department_name"] if row else code

    @staticmethod
    def exists(name: str) -> bool:
        return name in DepartmentsDao.get_names()

    @staticmethod
    def normalize(name: str, default: str = "内科") -> str:
        """把模型输出的科室名归一化到数据库中的科室列表内。"""
        if not name:
            return default
        text = str(name).strip()
        names = DepartmentsDao.get_names()
        if text in names:
            return text
        for candidate in names:
            if candidate in text or text in candidate:
                return candidate
        return default

    @staticmethod
    def invalidate() -> None:
        with _lock:
            _cache.update({"rows": None, "names": None, "at": 0.0})


# 兼容旧调用名
DepartmentsDao.get_all_departments = staticmethod(lambda: DepartmentsDao.list_active())

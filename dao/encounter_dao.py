"""问诊记录表数据访问（`encounters`）。

字段：id / session_id / user_id / scene / chief_complaint / risk_level /
      department / summary / metadata(JSON) / create_time

``risk_level`` 入库存英文枚举（low / medium / high），由 Service 层负责中英转换。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from config.settings import settings
from utils.db import db
from utils.enums import risk_to_db


class EncounterDao:
    @staticmethod
    def add(
        session_id: Optional[str],
        user_id: str,
        scene: str,
        chief_complaint: str,
        risk_level: str,
        department: str,
        summary: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        return db.insert_one(
            "INSERT INTO encounters (session_id, user_id, scene, chief_complaint, risk_level, "
            "department, summary, metadata, create_time) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())",
            (
                session_id,
                user_id,
                scene,
                chief_complaint,
                risk_to_db(risk_level),
                department,
                summary,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )

    @staticmethod
    def list_recent(user_id: str, days: Optional[int] = None, limit: int = 200) -> List[dict]:
        """查询近 N 天的问诊记录，按时间倒序。"""
        days = max(1, min(int(days or settings.RECORD_DEFAULT_DAYS), 365))
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        rows = db.query_all(
            "SELECT id, session_id, user_id, scene, chief_complaint, risk_level, department, "
            "summary, metadata, create_time FROM encounters "
            "WHERE user_id = %s AND create_time >= %s "
            "ORDER BY create_time DESC, id DESC LIMIT %s",
            (user_id, since, limit),
        )
        return [EncounterDao._decode(r) for r in rows]

    @staticmethod
    def get(encounter_id: int) -> Optional[dict]:
        row = db.query_one(
            "SELECT id, session_id, user_id, scene, chief_complaint, risk_level, department, "
            "summary, metadata, create_time FROM encounters WHERE id = %s",
            (encounter_id,),
        )
        return EncounterDao._decode(row) if row else None

    @staticmethod
    def _decode(row: dict) -> dict:
        meta = row.get("metadata")
        if isinstance(meta, str) and meta:
            try:
                row["metadata"] = json.loads(meta)
            except (TypeError, ValueError):
                row["metadata"] = {}
        elif not meta:
            row["metadata"] = {}
        return row

    @staticmethod
    def count(user_id: Optional[str] = None, days: Optional[int] = None) -> int:
        sql = "SELECT COUNT(*) AS c FROM encounters"
        where, params = [], []
        if user_id:
            where.append("user_id = %s")
            params.append(user_id)
        if days:
            since = (datetime.now() - timedelta(days=int(days))).strftime("%Y-%m-%d %H:%M:%S")
            where.append("create_time >= %s")
            params.append(since)
        if where:
            sql += " WHERE " + " AND ".join(where)
        row = db.query_one(sql, tuple(params))
        return int(row["c"]) if row else 0

    @staticmethod
    def stats_by_risk(user_id: Optional[str] = None) -> List[dict]:
        if user_id:
            return db.query_all(
                "SELECT risk_level, COUNT(*) AS c FROM encounters WHERE user_id = %s "
                "GROUP BY risk_level",
                (user_id,),
            )
        return db.query_all("SELECT risk_level, COUNT(*) AS c FROM encounters GROUP BY risk_level")

    @staticmethod
    def stats_by_scene(user_id: Optional[str] = None) -> List[dict]:
        if user_id:
            return db.query_all(
                "SELECT scene, COUNT(*) AS c FROM encounters WHERE user_id = %s GROUP BY scene",
                (user_id,),
            )
        return db.query_all("SELECT scene, COUNT(*) AS c FROM encounters GROUP BY scene")

    @staticmethod
    def top_departments(user_id: Optional[str] = None, limit: int = 8) -> List[dict]:
        if user_id:
            return db.query_all(
                "SELECT department, COUNT(*) AS c FROM encounters "
                "WHERE user_id = %s AND department IS NOT NULL AND department != '' "
                "GROUP BY department ORDER BY c DESC LIMIT %s",
                (user_id, limit),
            )
        return db.query_all(
            "SELECT department, COUNT(*) AS c FROM encounters "
            "WHERE department IS NOT NULL AND department != '' "
            "GROUP BY department ORDER BY c DESC LIMIT %s",
            (limit,),
        )

    @staticmethod
    def clear_all() -> None:
        db.delete("DELETE FROM encounters")

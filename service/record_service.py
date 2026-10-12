"""问诊记录服务（需求 3.5 FR-RECORD）。"""
from __future__ import annotations

from typing import Dict, List, Optional

from config.settings import settings
from dao.encounter_dao import EncounterDao
from utils.enums import SCENE_FROM_DB, risk_from_db
from utils.text import truncate


class RecordService:
    @staticmethod
    def list_records(user_id: str, days: int = None, limit: int = 200) -> List[dict]:
        """查询近 N 天的分诊 / 问诊 / 用药记录，按时间倒序。"""
        days = settings.RECORD_DEFAULT_DAYS if days is None else max(1, min(int(days), 365))
        rows = EncounterDao.list_recent(user_id, days, limit)
        return [RecordService._to_card(r) for r in rows]

    @staticmethod
    def get_record(record_id: int, user_id: Optional[str] = None) -> Optional[dict]:
        row = EncounterDao.get(record_id)
        if not row:
            return None
        if user_id and row.get("user_id") != user_id:
            return None
        return RecordService._to_card(row)

    @staticmethod
    def _to_card(row: dict) -> Dict:
        """转换为前端卡片 + 弹窗详情结构（对应「网页展示」问诊记录页）。"""
        metadata = row.get("metadata") or {}
        evidence = metadata.get("evidence") or []
        scene = row.get("scene") or "triage"
        risk_level = risk_from_db(row.get("risk_level"))

        return {
            "id": row.get("id"),
            "session_id": row.get("session_id"),
            "user_id": row.get("user_id"),
            "scene": scene,
            "scene_label": SCENE_FROM_DB.get(scene, "分诊"),
            "created_at": str(row.get("create_time") or ""),
            "chief_complaint": row.get("chief_complaint"),
            "title": truncate(row.get("chief_complaint") or "", 20, suffix="…"),
            "risk_level": risk_level,
            "department": row.get("department") or "",
            "summary": row.get("summary") or "",
            "conclusion": row.get("summary") or "",
            "evidence_count": len(evidence),
            "evidence": evidence,
            "thinking_steps": metadata.get("thinking_steps") or [],
            "metrics": metadata.get("metrics") or {},
            "structured": metadata.get("structured") or {},
            "degradations": metadata.get("degradations") or [],
            "reason": RecordService._reason(row, evidence, risk_level),
        }

    @staticmethod
    def _reason(row: dict, evidence: list, risk_level: str) -> str:
        """分诊依据与原因（前端卡片底部展示）。"""
        parts = []
        if row.get("department"):
            parts.append(f"推荐科室：{row['department']}")
        if risk_level:
            parts.append(f"风险等级：{risk_level}")
        if evidence:
            titles = [e.get("title") for e in evidence[:2] if e.get("title")]
            if titles:
                parts.append("知识库依据：" + "、".join(titles))
        return "；".join(parts)

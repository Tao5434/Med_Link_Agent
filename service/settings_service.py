"""系统设置与数据管理服务（需求 3.7 FR-SETTINGS）。"""
from __future__ import annotations

from config.settings import settings
from dao.appointment_dao import AppointmentDao
from dao.departments_dao import DepartmentsDao
from dao.doctor_schedule_dao import DoctorScheduleDao
from dao.encounter_dao import EncounterDao
from dao.message_dao import MessageDao
from dao.report_dao import ReportDao
from dao.session_dao import SessionDao
from dao.user_dao import UserDao
from utils.db import db
from utils.enums import risk_from_db, SCENE_FROM_DB

from agent import research
from agent.llm import llm_client
from rag.rag import MedRag

ADMIN_ACCOUNT = "admin"


class SettingsService:
    @staticmethod
    def get_settings() -> dict:
        """系统设置状态。API Key 只返回是否已配置，不返回明文。"""
        rag_stats = {"backend": settings.RAG_BACKEND, "documents": 0, "chunks": 0}
        try:
            rag_stats = MedRag.stats()
        except Exception:  # noqa: BLE001
            pass

        return {
            "app_name": settings.APP_NAME,
            "app_version": settings.APP_VERSION,
            "llm_enabled": settings.llm_enabled(),
            "base_url": settings.LLM_BASE_URL,
            "model_name": settings.LLM_MODEL,
            "api_key_configured": settings.api_key_configured(),
            "llm_reachable": llm_client.probe() if llm_client.available else False,
            "deep_search_enabled": settings.DEEP_SEARCH_ENABLED,
            "deep_search": research.engine_status(),
            "rag_top_k": settings.RAG_TOP_K,
            "rag_backend": rag_stats.get("backend", settings.RAG_BACKEND),
            "knowledge_documents": rag_stats.get("documents", 0),
            "knowledge_chunks": rag_stats.get("chunks", 0),
            "departments": DepartmentsDao.get_names(),
            "department_total": len(DepartmentsDao.get_names()),
            "doctor_schedule_total": DoctorScheduleDao.count(),
            "user_total": UserDao.count(),
            "database": db.health(),
            "auth_required": settings.AUTH_REQUIRED,
            "token_expire_hours": settings.AUTH_TOKEN_EXPIRE_HOURS,
            "agent_chain": [
                "RouterAgent",
                "ContextAgent",
                "RAGAgent",
                "ResearchAgent",
                "ReasoningAgent",
                "FormatterAgent",
                "SafetyAgent",
            ],
        }

    # ------------------------------------------------------------------
    @staticmethod
    def clear_all(user: dict) -> dict:
        """清空数据。

        普通用户只清理自己的数据；``admin`` 账号执行全库清理
        （sessions / messages / encounters / appointments）。
        """
        user_id = user["user_id"]
        if user.get("account") == ADMIN_ACCOUNT:
            SessionDao.clear_all()
            EncounterDao.clear_all()
            AppointmentDao.clear_all()
            ReportDao.clear_all()
            db.delete("DELETE FROM health_profiles")
            scope = "all"
        else:
            with db.transaction() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM messages WHERE session_id IN "
                                "(SELECT id FROM sessions WHERE user_id = %s)", (user_id,))
                    cur.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
                    cur.execute("DELETE FROM encounters WHERE user_id = %s", (user_id,))
                    cur.execute("DELETE FROM appointments WHERE user_id = %s", (user_id,))
            ReportDao.delete_by_user(user_id)
            scope = "self"

        # 号源计数重算，避免清空后 booked_slots 残留
        for row in DoctorScheduleDao.list_all():
            if row.get("department_name"):
                DoctorScheduleDao.recompute_booked(row["department_name"], row["doctor"])

        return {
            "ok": True,
            "scope": scope,
            "cleared": ["sessions", "messages", "encounters", "appointments"],
        }

    @staticmethod
    def delete_session(session_id: str) -> dict:
        affected = SessionDao.delete(session_id)
        return {"ok": affected > 0, "session_id": session_id}

    # ------------------------------------------------------------------
    @staticmethod
    def metrics(user_id: str = None) -> dict:
        """平台指标（GET /api/metrics），默认统计当前登录用户。"""
        return {
            "user_id": user_id,
            "sessions": SessionDao.count(user_id),
            "messages": MessageDao.count(user_id),
            "encounters": EncounterDao.count(user_id),
            "appointments": AppointmentDao.count(user_id),
            "reports": ReportDao.count_by_user(user_id) if user_id else 0,
            "risk_distribution": {
                risk_from_db(r["risk_level"]): r["c"]
                for r in EncounterDao.stats_by_risk(user_id)
            },
            "scene_distribution": {
                SCENE_FROM_DB.get(r["scene"], r["scene"]): r["c"]
                for r in EncounterDao.stats_by_scene(user_id)
            },
            "top_departments": [
                {"department": r["department"], "count": r["c"]}
                for r in EncounterDao.top_departments(user_id)
            ],
            "knowledge": _safe_rag_stats(),
            "departments": len(DepartmentsDao.get_names()),
            "doctor_schedules": DoctorScheduleDao.count(),
            "users": UserDao.count(),
            "llm_enabled": settings.llm_enabled(),
            "llm_reachable": llm_client.probe() if llm_client.available else False,
            "database": db.health(),
        }


def _safe_rag_stats() -> dict:
    try:
        return MedRag.stats()
    except Exception:  # noqa: BLE001
        return {"backend": settings.RAG_BACKEND, "documents": 0, "chunks": 0}

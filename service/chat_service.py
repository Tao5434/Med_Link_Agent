"""对话服务：会话管理 + 多 Agent 编排 + 记录落库（需求 3.1 / 3.2 / 3.3）。

用户身份来自登录令牌，写库时不再使用前端传入的 user_id。
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from config.settings import settings
from dao.encounter_dao import EncounterDao
from dao.health_profile_dao import HealthProfileDao
from dao.message_dao import MessageDao
from dao.session_dao import SessionDao
from schema.dto.agent_dto import AgentTrace, ChatRequest, ChatResponse, Evidence
from utils.function import new_session_id
from utils.text import truncate

from agent.triage_agent import TriageAgent, TriageAgentError

logger = logging.getLogger(__name__)


class ChatService:
    """统一对话入口（分诊 / 问诊 / 用药）。"""

    @staticmethod
    def handle(dto: ChatRequest, user: dict, scene: str = "auto") -> ChatResponse:
        """执行一次对话。

        :param dto: 对话请求
        :param user: 当前登录用户（含 user_id / user_pk）
        :param scene: 强制场景；auto 表示由 RouterAgent 自动路由
        """
        message = (dto.message or "").strip()
        if not message:
            raise ValueError("message 不能为空")

        user_id = user["user_id"]
        session_id = dto.session_id or new_session_id()

        # 1) 会话 upsert（标题取消息前 30 字）
        SessionDao.upsert(
            session_id, user_id, truncate(message, settings.SESSION_TITLE_LENGTH, suffix="")
        )

        # 2) 患者基础信息落库（health_profiles.user_id 为 int）
        patient_context = dto.patient_context.model_dump() if dto.patient_context else {}
        if patient_context and any(patient_context.values()):
            HealthProfileDao.upsert(user["user_pk"], patient_context)

        # 3) 读取历史对话（当前消息写入之前，避免重复）
        history = MessageDao.recent(session_id, settings.HISTORY_MEMORY_LIMIT)

        # 4) 写入用户消息
        MessageDao.add(session_id, "user", message, {"scene": scene})

        # 5) 多 Agent 编排
        try:
            state = TriageAgent.chat(
                message=message,
                user_id=user_id,
                session_id=session_id,
                scene=scene,
                patient_context=patient_context,
                history=history,
                enable_deep_search=dto.enable_deep_search,
            )
        except TriageAgentError as exc:
            logger.exception("Agent 编排失败")
            state = {
                "routed_scene": scene if scene != "auto" else "triage",
                "answer": f"当前服务暂时不可用，请稍后重试。（{exc}）",
                "risk_level": "低风险",
                "recommended_department": "",
                "evidence": [],
                "thinking_steps": [],
                "traces": [],
                "metrics": {"error": str(exc)},
                "degradations": [str(exc)],
                "structured": {},
            }

        response = ChatService._build_response(session_id, state)

        # 6) 写入助手回答（messages.metadata 存 JSON）
        MessageDao.add(
            session_id,
            "assistant",
            response.answer,
            {
                "scene": response.scene,
                "risk_level": response.risk_level,
                "recommended_department": response.recommended_department,
                "traces": [t.model_dump() for t in response.traces],
                "degraded": response.degraded,
            },
        )

        # 7) 落库问诊记录（encounters.risk_level 存英文枚举）
        EncounterDao.add(
            session_id=session_id,
            user_id=user_id,
            scene=response.scene,
            chief_complaint=message,
            risk_level=response.risk_level,
            department=response.recommended_department,
            summary=truncate(response.answer, 500),
            metadata={
                "evidence": [e.model_dump() for e in response.evidence],
                "metrics": response.metrics,
                "thinking_steps": response.thinking_steps,
                "structured": response.structured,
                "degradations": response.degradations,
            },
        )
        SessionDao.touch(session_id)

        return response

    # ------------------------------------------------------------------
    @staticmethod
    def _build_response(session_id: str, state: Dict[str, Any]) -> ChatResponse:
        scene = state.get("routed_scene") or state.get("scene") or "triage"
        evidence = [
            Evidence(**e) if isinstance(e, dict) else e for e in (state.get("evidence") or [])
        ][: settings.EVIDENCE_MAX]
        traces = [
            AgentTrace(**t) if isinstance(t, dict) else t for t in (state.get("traces") or [])
        ]
        metrics = dict(state.get("metrics") or {})
        metrics.update(
            {
                "rag_evidence_count": len(state.get("rag_evidence") or []),
                "web_evidence_count": len(state.get("web_evidence") or []),
                "evidence_count": len(evidence),
                "agent_calls": len(traces),
                "thinking_steps": len(state.get("thinking_steps") or []),
                "department": state.get("recommended_department", ""),
                "risk_level": state.get("risk_level", ""),
            }
        )

        return ChatResponse(
            session_id=session_id,
            scene=scene,
            recommended_department=state.get("recommended_department", "") or "",
            risk_level=state.get("risk_level", "低风险") or "低风险",
            answer=state.get("answer", "") or "",
            evidence=evidence,
            thinking_steps=list(state.get("thinking_steps") or []),
            traces=traces,
            metrics=metrics,
            structured=dict(state.get("structured") or {}),
            disclaimer=state.get("disclaimer") or settings.DISCLAIMER,
            degraded=bool(state.get("degradations")),
            degradations=list(state.get("degradations") or []),
        )

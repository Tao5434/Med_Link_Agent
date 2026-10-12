"""TriageAgent —— 分诊 / 问诊 / 用药 三类场景的统一 Agent 门面。

对上层 Service 暴露单一入口 ``TriageAgent.chat()``，内部驱动
Router → Context → RAG ∥ Research → Reasoning → Formatter → Safety 的多 Agent 编排。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from config.settings import settings
from dao.departments_dao import DepartmentsDao
from rag.rag import MedRag

from agent import rules
from agent.graph import run_agent
from agent.llm import llm_client
from agent.state import AgentState  # 兼容旧引用

__all__ = ["State", "TriageAgent", "TriageAgentError"]


class TriageAgentError(RuntimeError):
    """Agent 编排失败。"""


State = AgentState


class TriageAgent:
    """统一对话 Agent。"""

    SYSTEM_PROMPT = "见 agent/prompts.py 中各场景 System Prompt。"

    # ------------------------------------------------------------------
    @staticmethod
    def chat(
        message: str,
        user_id: str = "guest",
        session_id: str = "default",
        scene: str = "auto",
        patient_context: Optional[Dict[str, Any]] = None,
        history: Optional[List[Dict[str, Any]]] = None,
        enable_deep_search: bool = False,
    ) -> Dict[str, Any]:
        """执行一次多 Agent 编排。

        :return: 最终 AgentState（含 answer / evidence / traces / metrics 等）
        """
        if not message or not message.strip():
            raise TriageAgentError("用户消息不能为空")

        try:
            return run_agent(
                message=message.strip(),
                user_id=user_id,
                session_id=session_id,
                scene=scene,
                patient_context=patient_context,
                history=history,
                enable_deep_search=enable_deep_search,
            )
        except TriageAgentError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise TriageAgentError(f"Agent 编排失败：{exc}") from exc

    # ------------------------------------------------------------------
    @staticmethod
    def triage(message: str, **kwargs) -> Dict[str, Any]:
        return TriageAgent.chat(message, scene="triage", **kwargs)

    @staticmethod
    def consultation(message: str, **kwargs) -> Dict[str, Any]:
        return TriageAgent.chat(message, scene="consultation", **kwargs)

    @staticmethod
    def medication(message: str, **kwargs) -> Dict[str, Any]:
        return TriageAgent.chat(message, scene="medication", **kwargs)

    # ------------------------------------------------------------------
    @staticmethod
    def runtime_status() -> Dict[str, Any]:
        """运行态信息，供 /api/settings 与 /api/metrics 使用。"""
        return {
            "llm": llm_client.status(),
            "llm_probe_ok": llm_client.probe() if llm_client.available else False,
            "departments": DepartmentsDao.get_names(),
            "rag": MedRag.stats(),
            "deep_search_enabled": settings.DEEP_SEARCH_ENABLED,
            "rag_top_k": settings.RAG_TOP_K,
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

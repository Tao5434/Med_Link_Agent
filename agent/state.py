"""多 Agent 编排的共享状态（需求 3.8 C1）。

状态在 Router → Context → RAG ∥ Research → Reasoning → Formatter → Safety 之间流转。

注意：``rag_evidence`` / ``web_evidence`` / ``traces`` / ``thinking_steps`` /
``degradations`` 由**并发的** RAGAgent 与 ResearchAgent 同时写入，因此使用
``operator.add`` 归约器做增量合并；``metrics`` 使用字典归约器。各节点只需返回
「本次新增的部分」。
"""
from __future__ import annotations

import operator
from typing import Any, Dict, List, Optional

from typing_extensions import Annotated, TypedDict


def merge_dict(left: Optional[Dict[str, Any]], right: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """字典归约器：右侧覆盖左侧同名键。"""
    merged: Dict[str, Any] = dict(left or {})
    merged.update(right or {})
    return merged


class AgentState(TypedDict, total=False):
    # ---------------- 输入 ----------------
    message: str                    # 用户输入
    session_id: Optional[str]       # 会话 ID
    user_id: str                    # 用户 ID
    scene: str                      # 请求指定场景（可能为 auto）
    patient_context: Dict[str, Any]  # 患者基础信息
    history: List[Dict[str, Any]]   # 最近对话记忆
    enable_deep_search: bool        # 是否开启联网增强

    # ---------------- RouterAgent ----------------
    routed_scene: str               # 路由判定场景
    scene_label: str                # 场景中文名
    route_reason: str               # 路由依据

    # ---------------- ContextAgent ----------------
    search_query: str               # 检索查询词
    symptom_hints: List[str]        # 命中的症状线索
    local_assessment: Dict[str, Any]  # 本地症状/风险评估线索

    # ---------------- RAGAgent ∥ ResearchAgent ----------------
    rag_evidence: Annotated[List[Dict[str, Any]], operator.add]
    web_evidence: Annotated[List[Dict[str, Any]], operator.add]

    # ---------------- ReasoningAgent / FormatterAgent ----------------
    evidence: List[Dict[str, Any]]  # 合并后的证据
    structured: Dict[str, Any]      # 结构化推理结果
    answer: str                     # 面向用户的回答
    recommended_department: str     # 推荐科室
    risk_level: str                 # 风险等级
    needs_format: bool              # 输出不规范，需要 FormatterAgent 修复

    # ---------------- SafetyAgent ----------------
    disclaimer: str
    compliance: Dict[str, Any]

    # ---------------- 观测 ----------------
    traces: Annotated[List[Dict[str, Any]], operator.add]
    thinking_steps: Annotated[List[str], operator.add]
    metrics: Annotated[Dict[str, Any], merge_dict]
    degradations: Annotated[List[str], operator.add]


def initial_state(
    message: str,
    user_id: str,
    session_id: str,
    scene: str = "auto",
    patient_context: Optional[Dict[str, Any]] = None,
    history: Optional[List[Dict[str, Any]]] = None,
    enable_deep_search: bool = False,
) -> AgentState:
    return AgentState(
        message=message or "",
        session_id=session_id,
        user_id=user_id,
        scene=scene or "auto",
        patient_context=patient_context or {},
        history=history or [],
        enable_deep_search=bool(enable_deep_search),
        routed_scene="",
        scene_label="",
        route_reason="",
        search_query="",
        symptom_hints=[],
        local_assessment={},
        rag_evidence=[],
        web_evidence=[],
        evidence=[],
        structured={},
        answer="",
        recommended_department="",
        risk_level="低风险",
        needs_format=False,
        disclaimer="",
        compliance={},
        traces=[],
        thinking_steps=[],
        metrics={},
        degradations=[],
    )

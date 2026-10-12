"""多 Agent 编排图（需求 3.8 C1）。

    START → RouterAgent → ContextAgent → ┬→ RAGAgent      ─┐
                                          └→ ResearchAgent ─┴→ ReasoningAgent
                                              → FormatterAgent(条件) → SafetyAgent → END

RAGAgent 与 ResearchAgent 在同一个 superstep 中并发执行，ReasoningAgent 作为
join 节点等待两者完成（map-reduce 扇出/扇入）。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from langgraph.graph import END, START, StateGraph

from agent import nodes
from agent.state import AgentState, initial_state


def build_graph():
    builder = StateGraph(AgentState)

    builder.add_node("router", nodes.router_node)
    builder.add_node("context", nodes.context_node)
    builder.add_node("rag", nodes.rag_node)
    builder.add_node("research", nodes.research_node)
    builder.add_node("reasoning", nodes.reasoning_node)
    builder.add_node("formatter", nodes.formatter_node)
    builder.add_node("safety", nodes.safety_node)

    builder.add_edge(START, "router")
    builder.add_edge("router", "context")

    # 并发扇出：本地检索 ∥ 联网检索
    builder.add_edge("context", "rag")
    builder.add_edge("context", "research")

    # 扇入：两个 Agent 都完成后才进入推理
    builder.add_edge("rag", "reasoning")
    builder.add_edge("research", "reasoning")

    builder.add_conditional_edges(
        "reasoning",
        nodes.route_after_reasoning,
        {"formatter": "formatter", "safety": "safety"},
    )
    builder.add_edge("formatter", "safety")
    builder.add_edge("safety", END)

    return builder.compile()


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def run_agent(
    message: str,
    user_id: str,
    session_id: str,
    scene: str = "auto",
    patient_context: Optional[Dict[str, Any]] = None,
    history: Optional[list] = None,
    enable_deep_search: bool = False,
) -> Dict[str, Any]:
    """执行一次完整的多 Agent 编排，返回最终状态。"""
    state = initial_state(
        message=message,
        user_id=user_id,
        session_id=session_id,
        scene=scene,
        patient_context=patient_context,
        history=history,
        enable_deep_search=enable_deep_search,
    )
    return get_graph().invoke(state)

"""RouterAgent —— 业务场景路由。

把用户输入识别为「智能分诊 / 线上问诊 / 用药咨询」三类场景之一，
决定后续使用哪一套 System Prompt 与归一化策略。

* 优先使用规则路由（``agent.rules.route_scene``），离线可用、结果稳定；
* 当大模型可用时，用模型结果覆盖规则结果，提升长句、口语化表达的识别率。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from agent import rules
from agent.llm import llm_client
from agent.state import AgentState  # 兼容：外部可直接从此模块导入状态类型

logger = logging.getLogger(__name__)

SCENES = ("triage", "consultation", "medication")

ROUTER_PROMPT = """你是医疗平台的路由助手。请判断用户输入属于下面哪一类场景，只输出一个词：

triage —— 分诊：询问该挂哪个科室、推荐就诊科室、症状对应科室
consultation —— 问诊：描述症状、询问可能原因、是否需要就医、如何护理
medication —— 用药：询问药品能否同服、相互作用、禁忌、副作用、特殊人群用药

只允许输出 triage、consultation、medication 三者之一，不要输出其他任何内容。"""

__all__ = ["State", "SCENES", "route", "route_scene", "apply_route"]

State = AgentState


def route(message: str, requested: str = "auto") -> Dict[str, Any]:
    """返回路由结果字典。"""
    scene, reason = rules.route_scene(message, requested)
    return {
        "scene": scene,
        "label": rules.SCENE_LABELS.get(scene, scene),
        "reason": reason,
        "source": "rule",
    }


def route_scene(message: str, requested: str = "auto") -> Dict[str, Any]:
    """场景路由；大模型可用时用模型结果覆盖规则结果。"""
    result = route(message, requested)

    # 显式指定场景时不再调用模型
    if requested and requested not in ("auto", "", None):
        return result

    if not (llm_client.available and llm_client.probe()):
        return result

    try:
        raw = llm_client.chat(
            [
                {"role": "system", "content": ROUTER_PROMPT},
                {"role": "user", "content": message or ""},
            ],
            temperature=0.0,
            max_tokens=8,
        )
    except Exception as exc:  # noqa: BLE001
        logger.info("RouterAgent 模型路由失败，沿用规则结果: %s", exc)
        return result

    if not raw:
        return result

    text = raw.strip().lower()
    for scene in SCENES:
        if scene in text:
            result["scene"] = scene
            result["label"] = rules.SCENE_LABELS.get(scene, scene)
            result["reason"] = "大模型语义路由"
            result["source"] = "llm"
            break
    return result


def apply_route(state: AgentState) -> Dict[str, Any]:
    """把路由结果写回状态（供 LangGraph 节点使用）。"""
    result = route_scene(state.get("message", ""), state.get("scene", "auto"))
    return {
        "routed_scene": result["scene"],
        "scene_label": result["label"],
        "route_reason": result["reason"],
    }

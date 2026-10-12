"""多 Agent 编排链路的各个节点（需求 3.8）。

链路：Router → Context → (RAG ∥ Research) → Reasoning → Formatter(条件) → Safety

约定：带有 ``operator.add`` 归约器的状态键（traces / thinking_steps / degradations /
rag_evidence / web_evidence）**只返回本次新增的部分**，由 LangGraph 自动合并。
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from config.settings import settings
from dao.departments_dao import DepartmentsDao
from rag.rag import MedRag
from utils.compliance import compliance_guard
from utils.text import truncate

from agent import prompts, rules
from agent.llm import llm_client, parse_narrative
from agent.research import deep_search
from agent.state import AgentState

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ("recommended_department", "risk_level", "conclusion")


# ----------------------------------------------------------------------
# 观测辅助
# ----------------------------------------------------------------------
def _trace(agent: str, action: str, detail: str = "", duration_ms: int = 0, status: str = "ok") -> Dict[str, Any]:
    return {
        "agent": agent,
        "action": action,
        "detail": detail,
        "duration_ms": int(duration_ms),
        "status": status,
    }


def _departments() -> List[str]:
    try:
        return DepartmentsDao.get_names()
    except Exception:  # noqa: BLE001 - 数据库不可用时退回配置常量
        return list(settings.DEPARTMENTS)


# ----------------------------------------------------------------------
# 1. RouterAgent —— 场景路由
# ----------------------------------------------------------------------
def router_node(state: AgentState) -> Dict[str, Any]:
    start = time.perf_counter()
    scene, reason = rules.route_scene(state.get("message", ""), state.get("scene", "auto"))
    label = rules.SCENE_LABELS.get(scene, scene)
    elapsed = int((time.perf_counter() - start) * 1000)

    return {
        "routed_scene": scene,
        "scene_label": label,
        "route_reason": reason,
        "traces": [_trace("RouterAgent", f"场景路由 → {label}", reason, elapsed)],
        "thinking_steps": [f"RouterAgent：识别业务场景为「{label}」（{reason}）。"],
    }


# ----------------------------------------------------------------------
# 2. ContextAgent —— 患者上下文 + 历史对话 + 本地症状线索
# ----------------------------------------------------------------------
def context_node(state: AgentState) -> Dict[str, Any]:
    start = time.perf_counter()
    message = state.get("message", "")
    patient_context = state.get("patient_context") or {}
    history = state.get("history") or []

    hints = rules.symptom_hints(message)
    assessment = rules.assess_risk(message, patient_context)
    search_query = rules.build_search_query(message, patient_context, history)

    elapsed = int((time.perf_counter() - start) * 1000)
    detail = (
        f"症状线索 {len(hints)} 个；本地风险评估={assessment['risk_level']}；"
        f"历史对话 {len(history)} 条"
    )

    return {
        "search_query": search_query,
        "symptom_hints": hints,
        "local_assessment": assessment,
        "traces": [_trace("ContextAgent", "整理患者上下文与症状线索", detail, elapsed)],
        "thinking_steps": [
            f"ContextAgent：整理患者信息（{len(history)} 条历史对话），"
            f"命中症状线索 {('、'.join(hints)) if hints else '无'}，"
            f"本地风险评估为「{assessment['risk_level']}」（仅作参考线索）。"
        ],
    }


# ----------------------------------------------------------------------
# 3. RAGAgent —— 本地知识库召回（与 ResearchAgent 并发）
# ----------------------------------------------------------------------
def rag_node(state: AgentState) -> Dict[str, Any]:
    start = time.perf_counter()
    query = state.get("search_query") or state.get("message", "")
    try:
        evidence = MedRag.retrieve_info(query, settings.RAG_CHAIN_TOP_K)
        items = [e.model_dump() for e in evidence]
        status = "ok" if items else "degraded"
        detail = f"本地知识库召回 {len(items)} 条"
    except Exception as exc:  # noqa: BLE001
        logger.warning("RAG 检索失败: %s", exc)
        items, status, detail = [], "failed", f"本地知识库检索失败：{exc}"

    elapsed = int((time.perf_counter() - start) * 1000)
    step = (
        f"RAGAgent：从本地知识库召回 {len(items)} 条证据。"
        if items
        else "RAGAgent：本地知识库未召回相关证据。"
    )

    return {
        "rag_evidence": items,
        "traces": [_trace("RAGAgent", "本地知识库检索", detail, elapsed, status)],
        "thinking_steps": [step],
    }


# ----------------------------------------------------------------------
# 4. ResearchAgent —— 联网 DeepResearch（与 RAGAgent 并发）
# ----------------------------------------------------------------------
def research_node(state: AgentState) -> Dict[str, Any]:
    start = time.perf_counter()
    enabled = bool(state.get("enable_deep_search")) or settings.DEEP_SEARCH_ENABLED
    query = state.get("search_query") or state.get("message", "")

    if not enabled:
        elapsed = int((time.perf_counter() - start) * 1000)
        return {
            "web_evidence": [],
            "traces": [
                _trace(
                    "ResearchAgent",
                    "联网检索（未开启）",
                    "本次未开启联网增强，跳过联网检索",
                    elapsed,
                    "skipped",
                )
            ],
            "thinking_steps": ["ResearchAgent：本次未开启联网增强，跳过联网检索。"],
        }

    items = deep_search(query, settings.DEEP_SEARCH_TOP_K)
    elapsed = int((time.perf_counter() - start) * 1000)
    fallback = bool(items) and items[0].get("kind") == "fallback"
    status = "degraded" if fallback else ("ok" if items else "failed")

    step = (
        "ResearchAgent：联网检索不可用，已降级为「基于本地知识库与安全规则回答」。"
        if fallback
        else f"ResearchAgent：联网补充 {len(items)} 条资料。"
    )

    return {
        "web_evidence": items,
        "traces": [
            _trace(
                "ResearchAgent",
                "联网 DeepResearch",
                f"联网检索返回 {len(items)} 条" + ("（含降级提示）" if fallback else ""),
                elapsed,
                status,
            )
        ],
        "thinking_steps": [step],
    }


# ----------------------------------------------------------------------
# 5. ReasoningAgent —— 结构化医学推理（含完整降级顺序）
# ----------------------------------------------------------------------
def reasoning_node(state: AgentState) -> Dict[str, Any]:
    start = time.perf_counter()
    scene = state.get("routed_scene") or "triage"
    message = state.get("message", "")
    departments = _departments()

    evidence = _merge_evidence(state)
    new_degradations: List[str] = []
    new_steps: List[str] = []
    retries = 0
    structured: Optional[Dict[str, Any]] = None
    needs_format = False
    llm_used = False

    if llm_client.available and llm_client.probe():
        system_prompt = prompts.get_scene_prompt(scene, departments)
        user_prompt = _build_user_prompt(state, evidence)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # 第 1 步：标准 JSON 输出
        structured = llm_client.chat_json(messages)
        if structured is not None:
            llm_used = True
        else:
            retries += 1
            # 第 2 步：叙事解析
            raw = llm_client.chat(messages, temperature=0.1)
            structured = _from_narrative(raw)
            if structured is not None:
                needs_format = True
                llm_used = True
                new_degradations.append("模型未返回合法 JSON，已按叙事解析降级")

            # 第 3 步：JSON 修复
            if structured is None:
                retries += 1
                repair_messages = messages + [
                    {
                        "role": "user",
                        "content": "你上一次的输出不是合法 JSON。请只重新输出一个合法的 JSON 对象，"
                        "不要包含任何解释、不要使用 Markdown 代码块。",
                    }
                ]
                structured = llm_client.chat_json(repair_messages)
                if structured is not None:
                    needs_format = True
                    llm_used = True
                    new_degradations.append("模型 JSON 输出非法，已通过 JSON 修复重试")

            # 第 4 步：叙事重试
            if structured is None:
                retries += 1
                raw = llm_client.chat(
                    [
                        {"role": "system", "content": prompts.NARRATIVE_FALLBACK_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.1,
                )
                structured = _from_narrative(raw)
                if structured is not None:
                    needs_format = True
                    llm_used = True
                    new_degradations.append("模型结构化输出连续失败，已按叙事重试降级")
    else:
        reason = llm_client.last_error or "未配置或服务不可达"
        new_degradations.append(f"大模型不可用（{reason}），已启用规则 + 知识库降级模式")
        new_steps.append("ReasoningAgent：大模型不可用，切换到本地规则 + 知识库降级推理。")

    # 第 5 步：规则兜底
    if structured is None:
        structured = rules.fallback_structured(
            message=message,
            scene=scene,
            patient_context=state.get("patient_context"),
            evidence=evidence,
            local_assessment=state.get("local_assessment"),
            degraded_reason="; ".join(list(state.get("degradations") or []) + new_degradations),
        )
        needs_format = True

    structured = _normalize_structured(structured, scene, departments, state)
    elapsed = int((time.perf_counter() - start) * 1000)

    if not needs_format and any(not structured.get(f) for f in REQUIRED_FIELDS):
        needs_format = True

    mode = "大模型结构化推理" if llm_used else "本地规则兜底"
    n_local = len([e for e in evidence if e.get("kind") != "web"])
    n_web = len([e for e in evidence if e.get("kind") == "web"])

    new_steps.append(
        f"ReasoningAgent：结合患者信息 + {n_local} 条本地证据 + {n_web} 条联网资料完成推理，"
        f"给出推荐科室「{structured.get('recommended_department')}」、"
        f"风险等级「{structured.get('risk_level')}」。"
    )

    return {
        "structured": structured,
        "answer": structured.get("conclusion", ""),
        "recommended_department": structured.get("recommended_department", ""),
        "risk_level": structured.get("risk_level", "低风险"),
        "needs_format": needs_format,
        "evidence": evidence,
        "traces": [
            _trace(
                "ReasoningAgent",
                f"结构化医学推理（{mode}）",
                f"推荐科室={structured.get('recommended_department')}；"
                f"风险等级={structured.get('risk_level')}",
                elapsed,
                "ok" if llm_used else "degraded",
            )
        ],
        "thinking_steps": new_steps,
        "degradations": new_degradations,
        "metrics": {
            "llm_used": llm_used,
            "reasoning_retries": retries,
            "reasoning_mode": mode,
        },
    }


def _from_narrative(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    narrative = parse_narrative(raw, ["推荐科室", "风险等级", "结论", "依据", "红旗信号", "建议追问"])
    if not (narrative.get("结论") or narrative.get("推荐科室")):
        return None
    return {
        "recommended_department": narrative.get("推荐科室", ""),
        "risk_level": narrative.get("风险等级", ""),
        "conclusion": narrative.get("结论", ""),
        "reason": narrative.get("依据", ""),
        "red_flags": _split_list(narrative.get("红旗信号")),
        "follow_up": _split_list(narrative.get("建议追问")),
        "health_advice": [],
        "source": "narrative",
    }


# ----------------------------------------------------------------------
# 6. FormatterAgent —— 输出非法 JSON 时结构化修复（条件触发）
# ----------------------------------------------------------------------
def formatter_node(state: AgentState) -> Dict[str, Any]:
    start = time.perf_counter()
    before = dict(state.get("structured") or {})
    structured = _normalize_structured(before, state.get("routed_scene") or "triage", _departments(), state)
    changed = [k for k in structured if structured.get(k) != before.get(k)]

    elapsed = int((time.perf_counter() - start) * 1000)
    detail = f"修复字段：{'、'.join(changed)}" if changed else "字段已完整，无需修复"

    return {
        "structured": structured,
        "answer": structured.get("conclusion", ""),
        "recommended_department": structured.get("recommended_department", ""),
        "risk_level": structured.get("risk_level", "低风险"),
        "needs_format": False,
        "traces": [_trace("FormatterAgent", "结构化输出修复", detail, elapsed)],
        "thinking_steps": [f"FormatterAgent：校验并修复结构化输出（{detail}）。"],
    }


def route_after_reasoning(state: AgentState) -> str:
    """条件边：结构化输出不规范时进入 FormatterAgent。"""
    return "formatter" if state.get("needs_format") else "safety"


# ----------------------------------------------------------------------
# 7. SafetyAgent —— 合规检查 + 免责声明
# ----------------------------------------------------------------------
def safety_node(state: AgentState) -> Dict[str, Any]:
    start = time.perf_counter()
    structured = dict(state.get("structured") or {})
    scene = state.get("routed_scene") or "triage"

    answer = rules.structured_to_answer(structured, scene)
    guarded, audit = compliance_guard(answer)

    elapsed = int((time.perf_counter() - start) * 1000)
    detail = (
        f"替换绝对化表达 {len(audit['replaced_expressions'])} 处；"
        f"剔除处方剂量 {len(audit['stripped_dosage'])} 处；"
        f"免责声明{'已追加' if audit['disclaimer_appended'] else '已存在'}"
    )

    return {
        "answer": guarded,
        "disclaimer": settings.DISCLAIMER,
        "compliance": audit,
        "traces": [_trace("SafetyAgent", "医疗合规检查", detail, elapsed)],
        "thinking_steps": [f"SafetyAgent：执行医疗合规审查（{detail}），并确保免责声明存在。"],
        "metrics": {
            "compliance_hits": len(audit["replaced_expressions"]) + len(audit["stripped_dosage"])
        },
    }


# ----------------------------------------------------------------------
# 内部工具
# ----------------------------------------------------------------------
def _merge_evidence(state: AgentState) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    merged.extend(state.get("rag_evidence") or [])
    merged.extend(state.get("web_evidence") or [])
    return merged[: settings.EVIDENCE_MAX]


def _build_user_prompt(state: AgentState, evidence: List[Dict[str, Any]]) -> str:
    scene = state.get("routed_scene") or "triage"
    assessment = state.get("local_assessment") or {}
    return "\n\n".join(
        [
            f"【当前场景】{rules.SCENE_LABELS.get(scene, scene)}",
            f"【患者基础信息】{_context_text(state.get('patient_context'))}",
            f"【历史对话】\n{prompts.build_history_block(state.get('history') or [])}",
            f"【用户主诉】{state.get('message', '')}",
            "【本地症状线索（仅供参考，不得直接作为结论）】"
            f"命中症状：{'、'.join(state.get('symptom_hints') or []) or '无'}；"
            f"本地风险线索：{assessment.get('risk_level', '未知')}；"
            f"线索明细：{'、'.join(assessment.get('reasons') or []) or '无'}",
            f"【知识库与联网证据】\n{prompts.build_evidence_block(evidence, settings.EVIDENCE_MAX)}",
            "请依据以上信息输出 JSON 结果。",
        ]
    )


def _context_text(ctx: Optional[Dict[str, Any]]) -> str:
    if not ctx:
        return "未提供"
    parts = [
        f"{label}{ctx.get(key)}"
        for key, label in (
            ("age", "年龄"),
            ("gender", "性别"),
            ("chronic_diseases", "既往病史"),
            ("allergy_history", "过敏史"),
            ("medication_history", "用药史"),
        )
        if ctx.get(key)
    ]
    return "；".join(parts) if parts else "未提供"


def _split_list(value: Any) -> List[str]:
    import re

    if not value:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value).strip()
    if text in ("无", "没有", "无。", "none", "None", "null"):
        return []
    parts = [p.strip(" 。；;、,") for p in re.split(r"[、,，;；\n]", text)]
    return [p for p in parts if p and p not in ("无", "没有")]


def _normalize_structured(
    structured: Dict[str, Any],
    scene: str,
    departments: List[str],
    state: AgentState,
) -> Dict[str, Any]:
    """把模型输出归一化到系统约束范围内。"""
    result = dict(structured or {})

    dept = result.get("recommended_department") or result.get("department") or ""
    if scene == "medication":
        result["recommended_department"] = "药学门诊"
    else:
        normalized = _normalize_department(str(dept), departments)
        if not normalized:
            fallback_dept, _, _ = rules.match_department(state.get("message", ""))
            normalized = _normalize_department(fallback_dept, departments) or "内科"
        result["recommended_department"] = normalized

    result["risk_level"] = _normalize_risk(result.get("risk_level"))

    # 高风险统一引导到急诊科（departments 表中已包含「急诊科」）
    if result["risk_level"] == "高风险" and scene != "medication":
        emergency = _normalize_department("急诊科", departments)
        if emergency:
            result["recommended_department"] = emergency

    for field in ("red_flags", "follow_up", "health_advice"):
        result[field] = _split_list(result.get(field))

    if not result.get("conclusion"):
        result["conclusion"] = (
            f"根据目前提供的信息，建议到「{result['recommended_department']}」就诊评估，"
            f"风险等级为{result['risk_level']}。"
        )
    if not result.get("reason"):
        assessment = state.get("local_assessment") or {}
        result["reason"] = (
            f"结合患者主诉与本地线索"
            f"（{'、'.join(assessment.get('reasons') or []) or '未见明确高危信号'}），"
            f"并参考本地知识库证据综合判断。"
        )
    if not result.get("follow_up"):
        result["follow_up"] = [
            "症状持续多久了？是否在加重？",
            "是否伴随发热、呕吐等其他症状？",
            "是否有相关既往病史或正在服用的药物？",
        ]

    result.setdefault("source", "llm")
    return result


def _normalize_department(name: str, departments: List[str]) -> str:
    name = (name or "").strip().strip("「」\"'。 ")
    if not name:
        return ""
    if name in departments:
        return name
    for candidate in departments:
        if candidate in name or name in candidate:
            return candidate
    alias = {
        "心内科": "内科", "心血管内科": "内科", "普通内科": "内科", "急诊科": "内科",
        "消化内科": "消化科", "呼吸内科": "呼吸科", "神经科": "神经内科",
        "皮肤性病科": "皮肤科", "妇科": "妇产科", "产科": "妇产科",
        "泌尿科": "泌尿外科", "肾内科": "肾脏病中心", "内分泌": "内分泌科",
        "药剂科": "药学门诊", "药房": "药学门诊", "临床药学": "药学门诊",
        "骨科创伤": "骨科", "普外科": "外科", "全科": "内科",
    }
    for key, value in alias.items():
        if key in name:
            return value
    return ""


def _normalize_risk(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "低风险"
    if text in settings.RISK_LEVELS:
        return text
    low = text.lower()
    mapping = {
        "low": "低风险", "低": "低风险", "1": "低风险",
        "medium": "中风险", "mid": "中风险", "中": "中风险", "2": "中风险",
        "high": "高风险", "高": "高风险", "3": "高风险",
    }
    if low in mapping:
        return mapping[low]
    if "高" in text:
        return "高风险"
    if "中" in text:
        return "中风险"
    return "低风险"

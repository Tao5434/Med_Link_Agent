"""Agent 可调用工具集（供 LangChain ToolNode / 手工编排使用）。"""
from __future__ import annotations

from typing import Dict, List

from dao.departments_dao import DepartmentsDao
from rag.rag import MedRag
from schema.dto.agent_dto import Evidence

from agent import rules


def rag_retrieval_tool(query: str, top_k: int = 5) -> List[dict]:
    """本地医疗知识库检索工具。

    :param query: 用户问题（症状、疾病或药品相关）
    :param top_k: 返回条数
    :return: 证据列表 [{source,title,score,content,kind}]
    """
    evidence: List[Evidence] = MedRag.retrieve_info(query, top_k)
    return [e.model_dump() for e in evidence]


def get_all_departments_tool() -> List[dict]:
    """获取所有科室信息。

    :return: 科室列表，id=ID，department_name=科室名称，
             department_code=科室编码，is_active=是否启用（0/1）
    """
    return DepartmentsDao.get_all_departments()


def match_department_tool(symptom_text: str) -> Dict[str, object]:
    """根据症状文本给出候选科室（本地规则）。

    :param symptom_text: 症状描述文本
    :return: {department, hits, scores}
    """
    department, hits, scores = rules.match_department(symptom_text)
    return {"department": department, "hits": hits, "scores": scores}

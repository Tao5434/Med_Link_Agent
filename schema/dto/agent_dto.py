"""Agent 与对话相关的数据结构定义。"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PatientContext(BaseModel):
    """患者基础信息（对应前端「年龄/性别/既往病史/过敏史/用药史」）。"""

    age: Optional[str] = Field(None, description="年龄")
    gender: Optional[str] = Field(None, description="性别")
    chronic_diseases: Optional[str] = Field(None, description="既往病史")
    allergy_history: Optional[str] = Field(None, description="过敏史")
    medication_history: Optional[str] = Field(None, description="用药史")

    def to_text(self) -> str:
        parts = []
        if self.age:
            parts.append(f"年龄{self.age}岁")
        if self.gender:
            parts.append(f"性别{self.gender}")
        if self.chronic_diseases:
            parts.append(f"既往病史：{self.chronic_diseases}")
        if self.allergy_history:
            parts.append(f"过敏史：{self.allergy_history}")
        if self.medication_history:
            parts.append(f"用药史：{self.medication_history}")
        return "；".join(parts) if parts else "未提供患者基础信息"

    def is_empty(self) -> bool:
        return not any(
            [self.age, self.gender, self.chronic_diseases, self.allergy_history, self.medication_history]
        )


class ChatRequest(BaseModel):
    """统一对话请求（分诊 / 问诊 / 用药共用）。"""

    message: str = Field(..., description="用户输入的消息（症状主诉）")
    session_id: Optional[str] = Field(None, description="会话ID，不传则新建")
    user_id: Optional[str] = Field(None, description="用户ID")
    scene: Optional[str] = Field(None, description="场景：triage/consultation/medication，默认自动路由")
    patient_context: Optional[PatientContext] = Field(None, description="患者上下文")
    enable_deep_search: bool = Field(False, description="是否开启联网增强")


class Evidence(BaseModel):
    """可引用证据（需求 FR-RAG / FR-DEEPSEARCH）。"""

    source: str = Field(..., description="证据来源，如 knowledge_base/01_xxx.md")
    title: str = Field(..., description="证据标题")
    score: float = Field(0.0, description="相关性得分")
    content: str = Field(..., description="证据原文片段")
    kind: str = Field("local", description="证据类型：local/web/fallback")


class AgentTrace(BaseModel):
    """Agent 调用轨迹（需求 3.8）。"""

    agent: str = Field(..., description="Agent 名称")
    action: str = Field(..., description="执行动作")
    detail: str = Field("", description="细节说明")
    duration_ms: int = Field(0, description="耗时（毫秒）")
    status: str = Field("ok", description="状态：ok/degraded/skipped/failed")


class ChatResponse(BaseModel):
    """统一对话响应（需求 3.1 输出定义）。"""

    session_id: str = Field(..., description="会话ID")
    scene: str = Field(..., description="最终场景")
    recommended_department: str = Field("", description="推荐科室")
    risk_level: str = Field("低风险", description="风险等级：低风险/中风险/高风险")
    answer: str = Field("", description="面向用户的最终回答")
    evidence: List[Evidence] = Field(default_factory=list, description="证据列表")
    thinking_steps: List[str] = Field(default_factory=list, description="人类可读的推理步骤")
    traces: List[AgentTrace] = Field(default_factory=list, description="Agent 调用链")
    metrics: Dict[str, Any] = Field(default_factory=dict, description="推理量化指标")
    structured: Dict[str, Any] = Field(default_factory=dict, description="结构化推理结果")
    disclaimer: str = Field("", description="免责声明")
    degraded: bool = Field(False, description="是否发生降级")
    degradations: List[str] = Field(default_factory=list, description="降级原因说明")

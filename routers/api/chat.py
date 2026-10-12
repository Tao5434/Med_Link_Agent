"""对话类接口：健康检查 + 通用问诊 + 分诊 + 线上问诊 + 用药咨询。

除 ``/api/health`` 外均需登录，用户身份取自 Bearer 令牌（不再由前端传 user_id）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from config.settings import settings
from schema.dto.agent_dto import ChatRequest, ChatResponse
from service.chat_service import ChatService
from utils.db import db
from utils.response_model import error_message, success_data
from utils.security import current_user

from agent.triage_agent import TriageAgent
from rag.rag import MedRag

chat_router = APIRouter(prefix="/api", tags=["对话与分诊"])


@chat_router.get("/health", summary="健康检查（无需登录）")
async def health():
    """验收项 AC-1：GET /api/health 返回 {"status":"ok"}。"""
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "database": db.health(),
        "llm_enabled": settings.llm_enabled(),
    }


@chat_router.post("/chat", response_model=ChatResponse, summary="通用问诊（consultation 场景）")
async def chat(dto: ChatRequest, user: dict = Depends(current_user)):
    return ChatService.handle(dto, user, scene=dto.scene or "consultation")


@chat_router.post("/triage", response_model=ChatResponse, summary="智能分诊")
async def triage(dto: ChatRequest, user: dict = Depends(current_user)):
    return ChatService.handle(dto, user, scene="triage")


@chat_router.post("/consultation", response_model=ChatResponse, summary="线上问诊")
async def consultation(dto: ChatRequest, user: dict = Depends(current_user)):
    return ChatService.handle(dto, user, scene="consultation")


@chat_router.post("/medication", response_model=ChatResponse, summary="用药咨询")
async def medication(dto: ChatRequest, user: dict = Depends(current_user)):
    return ChatService.handle(dto, user, scene="medication")


@chat_router.get("/agent/status", summary="Agent 运行态（模型 / 知识库 / 科室）")
async def agent_status(user: dict = Depends(current_user)):
    return success_data(TriageAgent.runtime_status())


@chat_router.post("/knowledge/reload", summary="重建本地知识库索引")
async def reload_knowledge(user: dict = Depends(current_user)):
    try:
        MedRag.reload()
        return success_data(MedRag.stats())
    except Exception as exc:  # noqa: BLE001
        return error_message(f"重建索引失败：{exc}")

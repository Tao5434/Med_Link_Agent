"""LangChain 模型封装（可选）。

项目主链路使用 ``agent/llm.py`` 的 OpenAI 兼容客户端；
本模块保留 LangChain / Ollama 绑定，便于在需要 ToolNode、结构化输出等
LangChain 能力时使用。导入失败不会影响主链路。
"""
from __future__ import annotations

from typing import Any, Optional

from config.settings import settings

__all__ = ["get_chat_model", "get_embedding_model", "langchain_available"]


def langchain_available() -> bool:
    try:
        import langchain_ollama  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        return False


def get_chat_model(temperature: float = 0.3, num_predict: Optional[int] = None) -> Optional[Any]:
    """返回 ChatOllama 实例；依赖缺失时返回 None。"""
    if not langchain_available():
        return None
    from langchain_ollama import ChatOllama

    return ChatOllama(
        model=settings.OLLAMA_CHAT_MODEL,
        temperature=temperature,
        num_predict=num_predict or settings.LLM_MAX_TOKENS,
    )


def get_embedding_model() -> Optional[Any]:
    """返回 OllamaEmbeddings 实例；依赖缺失时返回 None。"""
    if not langchain_available():
        return None
    from langchain_ollama import OllamaEmbeddings

    return OllamaEmbeddings(model=settings.OLLAMA_EMBEDDING_MODEL)

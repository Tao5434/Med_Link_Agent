"""RAG 检索门面（需求 FR-RAG）。

对外统一暴露 ``MedRag``，内部按 ``RAG_BACKEND`` 选择实现：

* ``lightweight``（默认）：本地 Markdown + 关键词倒排 + TF-IDF 余弦相似度，
  完全离线可用，是保证「无 API Key 也能使用」的关键；
* ``chroma``：可选向量库实现，使用 llama-index + Chroma + Ollama Embedding，
  当本地已启动 Ollama 且安装了相关依赖时启用，失败自动回退 lightweight。
"""
from __future__ import annotations

from typing import List, Optional

from config.settings import settings
from rag.lightweight import LightweightRetriever
from schema.dto.agent_dto import Evidence


class MedRag:
    """知识库检索统一入口。"""

    _light = None
    _vector = None

    # ------------------------------------------------------------------
    @staticmethod
    def lightweight() -> LightweightRetriever:
        if MedRag._light is None:
            MedRag._light = LightweightRetriever()
        return MedRag._light

    @staticmethod
    def _get_vector_retriever():
        if settings.RAG_BACKEND != "chroma":
            return None
        if MedRag._vector is None:
            try:
                from rag.vector_store import ChromaRetriever

                MedRag._vector = ChromaRetriever()
            except Exception:  # noqa: BLE001 - 依赖缺失或模型不可用时静默回退
                MedRag._vector = False
        return MedRag._vector or None

    # ------------------------------------------------------------------
    @staticmethod
    def retrieve_info(query: str, top_k: Optional[int] = None) -> List[Evidence]:
        """检索本地知识库，返回可引用证据列表。"""
        top_k = top_k or settings.RAG_TOP_K
        vector = MedRag._get_vector_retriever()
        if vector is not None:
            try:
                results = vector.retrieve(query, top_k)
                if results:
                    return results
            except Exception:  # noqa: BLE001
                pass
        return MedRag.lightweight().retrieve(query, top_k)

    # ------------------------------------------------------------------
    @staticmethod
    def get_index():
        """兼容旧接口：返回轻量检索器（内置倒排索引与向量）。"""
        MedRag.lightweight().ensure_loaded()
        return MedRag.lightweight()

    @staticmethod
    def retriever_index():
        return MedRag.lightweight()

    @staticmethod
    def query_info(query: str) -> str:
        """无大模型时的抽取式摘要回答（兜底）。"""
        evidence = MedRag.retrieve_info(query, settings.RAG_TOP_K)
        if not evidence:
            return "本地知识库中暂未检索到与该问题直接相关的内容。"
        lines = ["根据本地健康知识库，可参考以下内容："]
        for i, item in enumerate(evidence, 1):
            lines.append(f"{i}. 【{item.title}】{item.content}")
        return "\n".join(lines)

    @staticmethod
    def query_index():
        return MedRag.lightweight()

    @staticmethod
    def stats() -> dict:
        return MedRag.lightweight().stats()

    @staticmethod
    def reload() -> None:
        if MedRag._light is not None:
            MedRag._light.reload()


if __name__ == "__main__":
    for ev in MedRag.retrieve_info("发热两天，咳嗽有黄痰", 3):
        print(f"[{ev.score}] {ev.title} ({ev.source})\n  {ev.content[:80]}\n")

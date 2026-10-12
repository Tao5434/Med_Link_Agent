"""可选的向量库检索实现（需求 2.3：向量数据库 chroma 或 milvus）。

仅在 ``RAG_BACKEND=chroma`` 且本地已启动 Ollama（提供 bge-m3 向量模型）时启用。
任何异常都会由 ``MedRag`` 捕获并回退到轻量检索，不影响主流程。
"""
from __future__ import annotations

from typing import List, Optional

from config.settings import settings
from schema.dto.agent_dto import Evidence
from utils.text import truncate


class ChromaRetriever:
    def __init__(self) -> None:
        import chromadb
        from llama_index.core import Settings, SimpleDirectoryReader, StorageContext, VectorStoreIndex
        from llama_index.core.node_parser import TokenTextSplitter
        from llama_index.embeddings.ollama import OllamaEmbedding
        from llama_index.vector_stores.chroma import ChromaVectorStore

        Settings.embed_model = OllamaEmbedding(model_name=settings.OLLAMA_EMBEDDING_MODEL)

        self.chroma_client = chromadb.PersistentClient(path=str(settings.VECTOR_DB_DIR))
        self.collection = self.chroma_client.get_or_create_collection("med_collection")
        self.vector_store = ChromaVectorStore(chroma_collection=self.collection)
        self.storage_context = StorageContext.from_defaults(vector_store=self.vector_store)

        if self.collection.count() == 0:
            documents = SimpleDirectoryReader(
                input_dir=str(settings.KNOWLEDGE_BASE_DIR)
            ).load_data()
            parser = TokenTextSplitter(
                chunk_size=settings.RAG_CHUNK_SIZE, chunk_overlap=settings.RAG_CHUNK_OVERLAP
            )
            nodes = parser.get_nodes_from_documents(documents, show_progress=False)
            VectorStoreIndex(nodes=nodes, storage_context=self.storage_context, show_progress=False)

        self.index = VectorStoreIndex.from_vector_store(vector_store=self.vector_store)

    def retrieve(self, query: str, top_k: Optional[int] = None) -> List[Evidence]:
        top_k = top_k or settings.RAG_TOP_K
        nodes = self.index.as_retriever(similarity_top_k=top_k).retrieve(query)
        evidence: List[Evidence] = []
        for node in nodes:
            meta = getattr(node.node, "metadata", {}) or {}
            file_name = meta.get("file_name", "knowledge_base")
            evidence.append(
                Evidence(
                    source=f"knowledge_base/{file_name}",
                    title=meta.get("file_name", "本地知识库"),
                    score=round(float(getattr(node, "score", 0.0) or 0.0), 4),
                    content=truncate(node.node.get_content(), 320),
                    kind="local",
                )
            )
        return evidence

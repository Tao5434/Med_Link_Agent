"""轻量本地知识库检索（需求 FR-RAG / 约束 2.4）。

实现要点：
* 载入 ``data/knowledge_base/*.md`` 并按 Markdown 标题切块；
* 构建「关键词倒排索引」用于快速候选召回；
* 使用 TF-IDF + 余弦相似度做相关性排序；
* 全程不依赖大模型 / 向量模型，保证无 API Key 时仍可检索。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from config.settings import settings
from schema.dto.agent_dto import Evidence
from utils.text import TfidfVectorizer, cosine, tokenize, truncate

HEADING_RE = re.compile(r"^(#{1,6})\s*(.+?)\s*$", re.M)


@dataclass
class Chunk:
    doc_id: str
    source: str
    title: str
    section: str
    content: str
    order: int

    @property
    def display_title(self) -> str:
        return f"{self.title} · {self.section}" if self.section else self.title


class LightweightRetriever:
    """本地 Markdown 知识库检索器。"""

    def __init__(self, kb_dir: Optional[Path] = None) -> None:
        self.kb_dir = Path(kb_dir or settings.KNOWLEDGE_BASE_DIR)
        self.chunks: List[Chunk] = []
        self.vectors: List[Dict[str, float]] = []
        self.inverted: Dict[str, List[int]] = {}
        self.vectorizer = TfidfVectorizer()
        self._loaded = False

    # ------------------------------------------------------------------
    # 载入与切块
    # ------------------------------------------------------------------
    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.reload()

    def reload(self) -> None:
        self.chunks = []
        self.vectors = []
        self.inverted = {}

        files = sorted(self.kb_dir.glob("*.md")) if self.kb_dir.exists() else []
        for path in files:
            self._load_file(path)

        if self.chunks:
            self.vectorizer.fit([c.content + " " + c.display_title for c in self.chunks])
            self.vectors = [
                self.vectorizer.transform(c.content + " " + c.display_title) for c in self.chunks
            ]
            for idx, chunk in enumerate(self.chunks):
                for term in set(tokenize(chunk.content + " " + chunk.display_title)):
                    self.inverted.setdefault(term, []).append(idx)
        self._loaded = True

    def _load_file(self, path: Path) -> None:
        text = path.read_text(encoding="utf-8", errors="ignore")
        doc_title = _first_heading(text) or path.stem
        doc_id = path.stem
        source = f"knowledge_base/{path.name}"

        # 按二级/三级标题切分；无标题时整体作为一块
        sections = _split_sections(text)
        order = 0
        for section_title, body in sections:
            body = body.strip()
            if not body:
                continue
            for piece in _split_by_size(body, settings.RAG_CHUNK_SIZE, settings.RAG_CHUNK_OVERLAP):
                self.chunks.append(
                    Chunk(
                        doc_id=doc_id,
                        source=source,
                        title=doc_title,
                        section=section_title,
                        content=piece,
                        order=order,
                    )
                )
                order += 1

    # ------------------------------------------------------------------
    # 检索
    # ------------------------------------------------------------------
    def retrieve(self, query: str, top_k: Optional[int] = None) -> List[Evidence]:
        self.ensure_loaded()
        top_k = top_k or settings.RAG_TOP_K
        if not query or not self.chunks:
            return []

        query_vec = self.vectorizer.transform(query)
        query_terms = set(tokenize(query))

        # 关键词倒排索引 → 候选集（命中任一词条的块）
        candidates: set[int] = set()
        for term in query_terms:
            candidates.update(self.inverted.get(term, []))
        # 候选过少时回退全量打分，保证召回
        if len(candidates) < top_k:
            candidates = set(range(len(self.chunks)))

        scored: List[tuple[float, int]] = []
        for idx in candidates:
            score = cosine(query_vec, self.vectors[idx])
            # 标题/章节命中加权（关键词倒排的实际价值）
            title_terms = set(tokenize(self.chunks[idx].display_title))
            overlap = len(query_terms & title_terms)
            if overlap:
                score += 0.06 * overlap
            if score > 0:
                scored.append((score, idx))

        if not scored:
            # 完全没有重合时，退化为词频最相近的前 top_k
            scored = sorted(
                ((cosine(query_vec, v), i) for i, v in enumerate(self.vectors)),
                key=lambda x: x[0],
                reverse=True,
            )[:top_k]

        scored.sort(key=lambda x: (-x[0], self.chunks[x[1]].order))

        evidence: List[Evidence] = []
        seen: set[tuple[str, str]] = set()
        for score, idx in scored:
            chunk = self.chunks[idx]
            key = (chunk.source, chunk.section)
            if key in seen:
                continue
            seen.add(key)
            evidence.append(
                Evidence(
                    source=chunk.source,
                    title=chunk.display_title,
                    score=round(float(score), 4),
                    content=truncate(chunk.content, 320),
                    kind="local",
                )
            )
            if len(evidence) >= top_k:
                break
        return evidence

    def stats(self) -> dict:
        self.ensure_loaded()
        return {
            "documents": len({c.source for c in self.chunks}),
            "chunks": len(self.chunks),
            "terms": len(self.inverted),
            "backend": "lightweight",
        }


# ----------------------------------------------------------------------
# 内部工具
# ----------------------------------------------------------------------
def _first_heading(text: str) -> Optional[str]:
    m = HEADING_RE.search(text)
    return m.group(2).strip() if m else None


def _split_sections(text: str) -> List[tuple[str, str]]:
    """按 Markdown 标题切分为 (章节标题, 正文) 列表。"""
    matches = list(HEADING_RE.finditer(text))
    if not matches:
        return [("", text)]

    sections: List[tuple[str, str]] = []
    for i, m in enumerate(matches):
        title = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        sections.append((title, body))
    return sections


def _split_by_size(text: str, size: int, overlap: int) -> List[str]:
    """长文本按段落聚合切块，块间保留 overlap 字符重叠。"""
    if len(text) <= size:
        return [text]

    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    pieces: List[str] = []
    buffer = ""
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(buffer) + len(para) + 1 <= size:
            buffer = f"{buffer}\n{para}" if buffer else para
            continue
        if buffer:
            pieces.append(buffer)
            tail = buffer[-overlap:] if overlap > 0 else ""
            buffer = f"{tail}\n{para}" if tail else para
        else:
            # 单段超长，硬切
            for i in range(0, len(para), size - overlap):
                pieces.append(para[i : i + size])
            buffer = ""
    if buffer:
        pieces.append(buffer)
    return [p for p in pieces if p.strip()]

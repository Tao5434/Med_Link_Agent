"""中文文本处理工具：分词、向量化、余弦相似度。

用于需求 2.4「知识库为本地 Markdown，采用轻量关键词倒排/余弦相似度检索」。
不依赖任何第三方 NLP 库，保证离线可用。
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, Iterable, List

# 中文停用词（轻量）
STOPWORDS = {
    "的", "了", "和", "是", "在", "有", "就", "不", "人", "都", "一", "一个", "上", "也",
    "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好", "自己", "这",
    "什么", "怎么", "可以", "可能", "如果", "以及", "或者", "但是", "因为", "所以", "进行",
    "出现", "需要", "建议", "情况", "问题", "相关", "通常", "一般", "比较", "还是", "已经",
    "对于", "由于", "并且", "同时", "以下", "以上", "可能", "比如", "例如", "等", "与",
    "及", "为", "以", "对", "从", "被", "把", "该", "其", "其中", "并", "或", "而", "则",
}

# 医疗领域关键词表：用于提升召回精度（关键词倒排）
MEDICAL_TERMS = [
    "发热", "发烧", "咳嗽", "咳痰", "黄痰", "咽痛", "流涕", "鼻塞", "乏力", "头痛", "头晕",
    "胸痛", "胸闷", "呼吸困难", "气促", "心悸", "高血压", "低血压", "糖尿病", "血糖",
    "恶心", "呕吐", "腹泻", "腹痛", "肚子疼", "小肚疼", "便秘", "腹胀", "反酸", "烧心",
    "腰痛", "腰酸", "关节痛", "骨折", "外伤", "皮疹", "瘙痒", "过敏", "荨麻疹",
    "月经", "痛经", "经期", "白带", "怀孕", "妊娠", "尿频", "尿痛", "血尿", "排尿",
    "眼科", "视力", "眼痛", "耳鸣", "失眠", "焦虑", "抑郁", "情绪",
    "布洛芬", "对乙酰氨基酚", "感冒灵", "阿莫西林", "头孢", "降压药", "降糖药", "剂量",
    "相互作用", "禁忌", "慎用", "不良反应", "特殊人群", "孕妇", "哺乳期", "儿童", "老年人",
    "血常规", "白细胞", "中性粒细胞", "淋巴细胞", "血红蛋白", "血小板", "C反应蛋白",
    "肝功能", "肾功能", "肌酐", "转氨酶", "血脂", "CT", "胸部CT", "结节", "阴影",
    "急诊", "就医", "挂号", "科室", "分诊", "风险", "红旗信号",
]

_ASCII_RE = re.compile(r"[A-Za-z][A-Za-z0-9\+\-]{1,}")
_NUM_RE = re.compile(r"\d+(?:\.\d+)?")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
_PUNCT_RE = re.compile(r"[^\w\u4e00-\u9fff]+")


def normalize(text: str) -> str:
    if not text:
        return ""
    return _PUNCT_RE.sub(" ", text).strip()


def tokenize(text: str, bigram: bool = True) -> List[str]:
    """中英文混合分词。

    * 英文/数字按词切分；
    * 中文按「关键词表命中 + 单字 + 相邻双字（bigram）」切分，
      无需外部分词库即可获得可用的召回效果。
    """
    if not text:
        return []
    text = text.strip()
    tokens: List[str] = []

    for m in _ASCII_RE.finditer(text):
        tokens.append(m.group(0).lower())
    for m in _NUM_RE.finditer(text):
        tokens.append(m.group(0))

    for m in _CJK_RE.finditer(text):
        seg = m.group(0)
        # 命中领域关键词
        for term in MEDICAL_TERMS:
            if term in seg:
                tokens.append(term)
        chars = [c for c in seg if c not in STOPWORDS]
        tokens.extend(chars)
        if bigram:
            for i in range(len(seg) - 1):
                bg = seg[i : i + 2]
                if bg[0] in STOPWORDS or bg[1] in STOPWORDS:
                    continue
                tokens.append(bg)

    return [t for t in tokens if t and t not in STOPWORDS]


class TfidfVectorizer:
    """极简 TF-IDF 向量化器（词表由语料构建）。"""

    def __init__(self) -> None:
        self.df: Counter = Counter()
        self.n_docs: int = 0

    def fit(self, corpus: Iterable[str]) -> "TfidfVectorizer":
        self.df = Counter()
        self.n_docs = 0
        for doc in corpus:
            self.n_docs += 1
            for term in set(tokenize(doc)):
                self.df[term] += 1
        return self

    def idf(self, term: str) -> float:
        if self.n_docs <= 0:
            return 1.0
        df = self.df.get(term, 0)
        return math.log((1 + self.n_docs) / (1 + df)) + 1.0

    def transform(self, text: str) -> Dict[str, float]:
        tokens = tokenize(text)
        if not tokens:
            return {}
        counts = Counter(tokens)
        total = sum(counts.values())
        vec: Dict[str, float] = {}
        for term, cnt in counts.items():
            tf = cnt / total
            vec[term] = tf * self.idf(term)
        return _l2_normalize(vec)


def _l2_normalize(vec: Dict[str, float]) -> Dict[str, float]:
    norm = math.sqrt(sum(v * v for v in vec.values()))
    if norm <= 0:
        return vec
    return {k: v / norm for k, v in vec.items()}


def cosine(vec_a: Dict[str, float], vec_b: Dict[str, float]) -> float:
    """余弦相似度（输入已做 L2 归一化时即为点积）。"""
    if not vec_a or not vec_b:
        return 0.0
    if len(vec_a) > len(vec_b):
        vec_a, vec_b = vec_b, vec_a
    return sum(v * vec_b.get(k, 0.0) for k, v in vec_a.items())


def split_sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[。！？；\n])", text)
    return [p.strip() for p in parts if p.strip()]


def truncate(text: str, limit: int, suffix: str = "…") -> str:
    if not text:
        return ""
    text = text.strip()
    return text if len(text) <= limit else text[:limit] + suffix

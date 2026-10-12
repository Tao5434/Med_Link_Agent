"""医疗安全合规处理（需求 FR-SAFETY）。

对最终回答执行：
1. 替换绝对化 / 诊断性表达；
2. 剔除具体处方剂量表述；
3. 保证免责声明存在。
"""
from __future__ import annotations

import re
from typing import Tuple

from config.settings import settings

# 绝对化 / 诊断性表达 → 合规表达
REPLACEMENTS: list[tuple[str, str]] = [
    ("确诊为", "需要由医生评估是否为"),
    ("可以确诊", "需要由医生进一步评估"),
    ("一定是", "可能为"),
    ("肯定是", "可能为"),
    ("必定是", "可能为"),
    ("就是", "可能为"),
    ("百分之百", "大概率"),
    ("包治", "有助于改善"),
    ("根治", "长期管理"),
    ("药到病除", "症状可能缓解"),
    ("必须服用", "是否用药需要医生评估"),
    ("必须吃", "是否用药需要医生评估"),
    ("应该服用", "是否用药建议咨询医生"),
    ("建议服用", "是否用药建议咨询医生"),
    ("剂量是", "具体剂量需要遵医嘱"),
    ("每次服用", "具体用法用量需要遵医嘱"),
    ("一天三次", "具体用法用量需要遵医嘱"),
    ("每日三次", "具体用法用量需要遵医嘱"),
    ("吃几片", "具体用法用量需要遵医嘱"),
    ("毫克", "（具体剂量需遵医嘱）"),
    ("mg", "（具体剂量需遵医嘱）"),
    ("不用去医院", "仍需留意症状变化，必要时就医"),
    ("不需要就医", "仍需留意症状变化，必要时就医"),
    ("没有大问题", "目前未识别到明确高危信号"),
]

# 需要整体遮蔽的处方化表达
DOSAGE_PATTERNS = [
    re.compile(r"(每次|每日|每天|一日)\s*\d+(\.\d+)?\s*(片|粒|袋|支|毫升|ml|mg|g|克)"),
    re.compile(r"\d+(\.\d+)?\s*(mg|ml)\s*(每|/)\s*(日|天|次)"),
    re.compile(r"一次\s*\d+\s*(片|粒|袋)"),
]

RED_FLAG_HINT = "如出现症状加重或新的不适，请及时线下就医。"


def replace_absolute_expressions(text: str) -> Tuple[str, list[str]]:
    hits: list[str] = []
    for src, dst in REPLACEMENTS:
        if src in text:
            text = text.replace(src, dst)
            hits.append(src)
    return text, hits


def strip_dosage(text: str) -> Tuple[str, list[str]]:
    hits: list[str] = []
    for pattern in DOSAGE_PATTERNS:
        for m in pattern.finditer(text):
            hits.append(m.group(0))
        text = pattern.sub("具体用法用量需要遵医嘱", text)
    return text, hits


def ensure_disclaimer(text: str) -> Tuple[str, bool]:
    disclaimer = settings.DISCLAIMER
    if disclaimer in text:
        return text, False
    text = text.rstrip()
    if not text.endswith(("。", "！", "？", ".", "!", "?")):
        text += "。"
    return f"{text}\n\n{disclaimer}", True


def compliance_guard(text: str) -> Tuple[str, dict]:
    """执行完整合规处理。

    :return: (处理后的文本, 审计信息)
    """
    if not text:
        text = ""
    text, replaced = replace_absolute_expressions(text)
    text, dosages = strip_dosage(text)
    text, appended = ensure_disclaimer(text)
    return text, {
        "replaced_expressions": replaced,
        "stripped_dosage": dosages,
        "disclaimer_appended": appended,
        "compliant": True,
    }


def is_compliant(text: str) -> bool:
    """判断文本是否已满足合规红线。"""
    if settings.DISCLAIMER not in text:
        return False
    for bad in ("确诊为", "一定是", "剂量是"):
        if bad in text:
            return False
    for pattern in DOSAGE_PATTERNS:
        if pattern.search(text):
            return False
    return True

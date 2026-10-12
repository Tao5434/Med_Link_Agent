"""报告查询与 AI 解读（需求 FR-REPORT）。

为每个用户内置 3 份模拟报告：血常规、胸部 CT、肝肾功能。
"""
from __future__ import annotations

from typing import Dict, List, Optional

# 报告模板（每个用户都拥有这 3 份）
REPORT_TEMPLATES: List[Dict] = [
    {
        "id": "RPT-001",
        "title": "血常规",
        "type": "检验",
        "department": "内科",
        "report_date": "2026-09-12",
        "institution": "诊小通互联网医院 · 检验中心",
        "summary": "白细胞与中性粒细胞比例升高，提示可能存在感染或炎症反应。",
        "items": [
            {"name": "白细胞计数 WBC", "value": "12.6", "unit": "10^9/L", "ref": "3.5~9.5", "flag": "偏高"},
            {"name": "中性粒细胞百分比 NEUT%", "value": "82.4", "unit": "%", "ref": "40~75", "flag": "偏高"},
            {"name": "淋巴细胞百分比 LYMPH%", "value": "12.1", "unit": "%", "ref": "20~50", "flag": "偏低"},
            {"name": "红细胞计数 RBC", "value": "4.72", "unit": "10^12/L", "ref": "4.3~5.8", "flag": "正常"},
            {"name": "血红蛋白 HGB", "value": "143", "unit": "g/L", "ref": "130~175", "flag": "正常"},
            {"name": "血小板计数 PLT", "value": "236", "unit": "10^9/L", "ref": "125~350", "flag": "正常"},
            {"name": "C 反应蛋白 CRP", "value": "28.5", "unit": "mg/L", "ref": "0~8", "flag": "偏高"},
        ],
    },
    {
        "id": "RPT-002",
        "title": "胸部 CT（平扫）",
        "type": "检查",
        "department": "呼吸科",
        "report_date": "2026-09-13",
        "institution": "诊小通互联网医院 · 影像中心",
        "summary": "右肺下叶少许斑片状模糊影，考虑炎性改变可能，建议结合临床并复查。",
        "items": [
            {"name": "右肺下叶", "value": "斑片状模糊影", "unit": "", "ref": "未见异常", "flag": "异常"},
            {"name": "左肺", "value": "纹理清晰", "unit": "", "ref": "未见异常", "flag": "正常"},
            {"name": "纵隔淋巴结", "value": "未见肿大", "unit": "", "ref": "未见肿大", "flag": "正常"},
            {"name": "胸腔积液", "value": "未见", "unit": "", "ref": "未见", "flag": "正常"},
            {"name": "胸膜", "value": "未见增厚", "unit": "", "ref": "未见增厚", "flag": "正常"},
        ],
    },
    {
        "id": "RPT-003",
        "title": "肝肾功能",
        "type": "检验",
        "department": "消化科",
        "report_date": "2026-09-14",
        "institution": "诊小通互联网医院 · 检验中心",
        "summary": "丙氨酸氨基转移酶轻度升高，肾功能指标在正常范围内。",
        "items": [
            {"name": "丙氨酸氨基转移酶 ALT", "value": "58", "unit": "U/L", "ref": "9~50", "flag": "偏高"},
            {"name": "天门冬氨酸氨基转移酶 AST", "value": "34", "unit": "U/L", "ref": "15~40", "flag": "正常"},
            {"name": "总胆红素 TBIL", "value": "14.2", "unit": "μmol/L", "ref": "3.4~20.5", "flag": "正常"},
            {"name": "白蛋白 ALB", "value": "43.1", "unit": "g/L", "ref": "40~55", "flag": "正常"},
            {"name": "肌酐 CREA", "value": "76", "unit": "μmol/L", "ref": "57~97", "flag": "正常"},
            {"name": "尿素 UREA", "value": "5.1", "unit": "mmol/L", "ref": "3.1~8.0", "flag": "正常"},
        ],
    },
]

ABNORMAL_FLAG = "正常"

# 报告类型：中文 → 入库英文枚举（reports.report_type）
REPORT_TYPE_DB = {"检验": "laboratory", "检查": "examination"}

# 常见异常指标的科普解释
ITEM_EXPLAIN: Dict[str, str] = {
    "白细胞计数": "白细胞升高常见于细菌感染、炎症反应或应激状态，也可见于剧烈运动、情绪紧张等生理性因素。",
    "中性粒细胞": "中性粒细胞比例升高多与细菌感染或急性炎症相关，需要结合症状与体征综合判断。",
    "淋巴细胞": "淋巴细胞比例降低可见于急性感染应激期，通常需要结合白细胞总数一起解读。",
    "C 反应蛋白": "C 反应蛋白是炎症的敏感指标，升高提示体内存在炎症反应，但不能说明具体部位与病因。",
    "右肺下叶": "肺内斑片状模糊影常见于炎性改变，也可能与其他因素有关，通常需要结合症状、血常规并由医生读片复核。",
    "丙氨酸氨基转移酶": "转氨酶轻度升高可能与熬夜、饮酒、脂肪肝、药物影响或近期感染有关，建议复查并结合病史评估。",
    "天门冬氨酸氨基转移酶": "转氨酶升高提示肝细胞可能存在一定程度的应激或损伤，需结合其他肝功能指标判断。",
    "肌酐": "肌酐是评估肾功能的常用指标，升高可能提示肾脏排泄功能下降，需结合尿素、尿检等综合评估。",
}

DEFAULT_EXPLAIN = "该指标超出参考范围，可能与多种因素相关，需要医生结合您的症状、病史与其他检查综合判断。"


def get_reports(user_id: str = "guest") -> List[Dict]:
    """获取报告列表（每个用户内置 3 份）。"""
    reports = []
    for tpl in REPORT_TEMPLATES:
        item = dict(tpl)
        item["user_id"] = user_id
        item["abnormal_count"] = sum(1 for i in tpl["items"] if i["flag"] != ABNORMAL_FLAG)
        item["risk_level"] = "中风险" if item["abnormal_count"] else "低风险"
        reports.append(item)
    return reports


def get_report(report_id: str, user_id: str = "guest") -> Optional[Dict]:
    for report in get_reports(user_id):
        if report["id"] == report_id:
            return report
    return None


def abnormal_items(report: Dict) -> List[Dict]:
    """异常项判定依据 items[].flag != "正常"（需求 3.4）。"""
    return [i for i in (report.get("items") or []) if i.get("flag") != ABNORMAL_FLAG]


def build_analysis(report: Dict) -> str:
    """生成指标明细的规则分析文本（降级与提示词共用）。"""
    abnormal = abnormal_items(report)
    if not abnormal:
        return (
            f"本次「{report['title']}」各项指标均在参考范围内，"
            "未发现明显异常，建议保持定期体检。"
        )
    lines = [f"本次「{report['title']}」共 {len(abnormal)} 项指标超出参考范围："]
    for item in abnormal:
        key = next((k for k in ITEM_EXPLAIN if k in item["name"]), None)
        explain = ITEM_EXPLAIN.get(key, DEFAULT_EXPLAIN) if key else DEFAULT_EXPLAIN
        lines.append(
            f"· {item['name']}：{item['value']}{item['unit']}（参考 {item['ref']}，{item['flag']}）。{explain}"
        )
    return "\n".join(lines)


def build_interpretation(report: Dict) -> str:
    """规则兜底的完整解读（需求 3.4：report_fallback）。"""
    abnormal = abnormal_items(report)
    department = report.get("department", "内科")
    risk = "中风险" if abnormal else "低风险"

    parts = [build_analysis(report), ""]
    if abnormal:
        parts.append(
            f"综合来看，目前存在 {len(abnormal)} 项异常指标，风险等级评估为{risk}。"
            f"建议携带本报告到「{department}」门诊，由医生结合您的症状、"
            "既往病史与用药情况进一步评估，必要时复查相关指标。"
        )
    else:
        parts.append(
            f"风险等级评估为{risk}。如近期仍有不适症状，建议到「{department}」门诊进一步咨询。"
        )
    return "\n".join(parts)

"""本地症状分析 / 风险评估规则引擎。

作用（需求 3.1）：
* 为 ContextAgent 提供本地症状线索与风险评估「参考线索」；
* 作为 ReasoningAgent 的**降级兜底**（``fallback_structured``），
  保证无大模型时依然能输出结构化的分诊结论（验收项 AC-10）。

注意：规则结果只作为线索，不得直接作为最终医学结论。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from config.settings import settings

# ----------------------------------------------------------------------
# 科室 → 症状关键词映射（用于本地线索与规则兜底）
# ----------------------------------------------------------------------
DEPARTMENT_KEYWORDS: Dict[str, List[str]] = {
    "呼吸科": [
        "咳嗽", "咳痰", "黄痰", "白痰", "咽痛", "喉咙痛", "气喘", "哮喘", "气促",
        "呼吸困难", "支气管", "肺炎", "肺部", "鼻塞", "流涕", "打喷嚏", "胸闷气短",
    ],
    "消化科": [
        "腹泻", "拉肚子", "腹痛", "肚子疼", "小肚疼", "肚疼", "恶心", "呕吐", "反酸",
        "烧心", "腹胀", "便秘", "胃痛", "胃胀", "便血", "黑便", "消化不良", "食欲不振",
    ],
    "神经内科": [
        "头痛", "头晕", "眩晕", "失眠", "手麻", "脚麻", "抽搐", "偏头痛", "面瘫",
        "说话不清", "记忆力下降", "耳鸣", "神经痛",
    ],
    "内科": [
        "发热", "发烧", "乏力", "浑身酸痛", "胸痛", "胸闷", "心悸", "心慌", "高血压",
        "血压高", "感冒", "全身不适", "低烧", "畏寒", "盗汗", "水肿",
    ],
    "骨科": [
        "腰痛", "腰酸", "关节痛", "骨折", "扭伤", "颈椎", "脖子痛", "肩膀痛", "膝盖痛",
        "腿疼", "背痛", "骨刺", "腰椎", "落枕",
    ],
    "皮肤科": [
        "皮疹", "瘙痒", "痒", "荨麻疹", "湿疹", "痘痘", "痤疮", "皮肤", "红斑",
        "脱发", "疣", "癣", "水泡",
    ],
    "妇产科": [
        "月经", "痛经", "经期", "经量", "白带", "怀孕", "妊娠", "妇科", "阴道",
        "排卵", "宫外孕", "孕", "产后",
    ],
    "泌尿外科": [
        "尿频", "尿急", "尿痛", "血尿", "排尿", "前列腺", "结石", "夜尿", "尿不尽",
    ],
    "内分泌科": [
        "血糖", "糖尿病", "甲状腺", "多饮", "多尿", "体重下降", "消瘦", "多汗",
        "月经不调伴体重变化", "尿酸", "痛风",
    ],
    "眼科": ["眼睛", "视力", "眼痛", "红眼", "流泪", "眼睑", "看东西模糊", "飞蚊"],
    "肾脏病中心": ["肌酐", "蛋白尿", "肾功能", "肾炎", "肾病", "肾", "尿蛋白", "透析"],
    "男科": ["男科", "勃起", "早泄", "精液", "包皮", "睾丸", "性功能"],
    "生殖医学科": ["备孕", "不孕", "不育", "生育", "试管婴儿", "生殖", "优生"],
    "外科": ["阑尾", "疝气", "肿块", "外伤", "伤口", "脓肿", "手术", "摔伤", "磕伤", "结石手术"],
    "药学门诊": [
        "吃药", "用药", "服药", "药物", "剂量", "相互作用", "能不能一起吃", "一起吃",
        "禁忌", "副作用", "不良反应", "停药", "中药", "西药", "哺乳期用药", "孕妇用药",
        "布洛芬", "对乙酰氨基酚", "感冒灵", "阿莫西林", "头孢", "阿司匹林", "降压药", "降糖药",
    ],
    "急诊科": ["急诊", "急救", "抢救", "120", "马上就医", "立刻就医", "紧急"],
}

# 高风险红旗信号（附录 B：高风险 = 含高危红旗症状）
RED_FLAG_PATTERNS: List[Tuple[str, str]] = [
    (r"剧烈胸痛|胸痛.*(出汗|濒死|压榨)|压榨性胸痛", "剧烈胸痛"),
    (r"呼吸困难|喘不上气|喘不过气|窒息|憋气", "呼吸困难"),
    (r"意识不清|昏迷|叫不醒|意识模糊|谵妄", "意识障碍"),
    (r"晕厥|晕倒|昏倒|休克|面色苍白.*出汗", "晕厥/休克"),
    (r"抽搐|抽风|惊厥|癫痫发作", "抽搐"),
    (r"大出血|呕血|咯血|吐血|便血|黑便|血便", "出血"),
    (r"剧烈腹痛|腹部剧痛|肚子剧痛|腹痛.*难以忍受|板状腹", "剧烈腹痛"),
    (r"高热不退|持续高热|40\s*[℃度]|39\.[5-9]\s*[℃度]", "持续高热"),
    (r"偏瘫|半身不遂|一侧无力|嘴歪|口角歪斜|说话不清|言语不清", "神经系统急症"),
    (r"剧烈头痛|炸裂样头痛|头痛.*呕吐.*颈部|颈部僵硬", "剧烈头痛"),
    (r"怀孕.*(腹痛|出血)|妊娠.*(腹痛|出血)|宫外孕", "妊娠急症"),
    (r"血压\s*(1[89]\d|2\d\d)|高血压危象", "血压危象"),
    (r"自杀|不想活|轻生|自残", "心理危机"),
    (r"严重过敏|喉头水肿|全身皮疹.*呼吸困难", "严重过敏"),
    (r"摔伤.*头|头部外伤|车祸|高处坠落", "严重外伤"),
    (r"血糖\s*(<\s*3|2[0-9]|[3-9]\d)\s*(mmol)?|低血糖昏迷", "血糖危象"),
    (r"血氧.*(9[0-4]|8\d)|氧饱和度.*(9[0-4]|8\d)", "低氧血症"),
]

# 中风险：含持续/需观察症状
MEDIUM_FLAG_PATTERNS: List[Tuple[str, str]] = [
    (r"发热|发烧|体温\s*3[89]", "发热"),
    (r"持续|反复|一直|好几天|三天|一周|两周|一个月|加重|越来越", "症状持续或加重"),
    (r"腹泻|拉肚子|呕吐|恶心", "消化道症状"),
    (r"腹痛|肚子疼|肚疼", "腹痛"),
    (r"咳嗽|咳痰", "咳嗽咳痰"),
    (r"头晕|眩晕|心悸|心慌|胸闷", "循环/神经症状"),
    (r"血压\s*(1[4-7]\d)", "血压偏高"),
    (r"血糖\s*(7|8|9|1[0-9])(\.\d)?\s*(mmol)?", "血糖偏高"),
    (r"体重下降|消瘦|贫血|乏力明显", "全身消耗表现"),
    (r"疼痛.*(夜间|影响睡眠|影响生活)", "疼痛影响生活"),
    (r"结节|阴影|占位|异常指标|指标异常", "检查异常"),
    (r"孕期|妊娠|哺乳|老人|儿童|婴儿", "特殊人群"),
]

SCENE_KEYWORDS = {
    "medication": [
        "吃药", "用药", "服药", "药物", "剂量", "相互作用", "能不能一起吃", "一起吃",
        "禁忌", "副作用", "不良反应", "停药", "换药", "中药", "西药", "饭前", "饭后",
    ],
    "triage": [
        "挂什么科", "哪个科", "看什么科", "分诊", "推荐科室", "去哪个科室", "应该挂",
    ],
    "consultation": [
        "怎么回事", "严重吗", "要不要去医院", "怎么处理", "怎么办", "需要注意",
        "是什么病", "帮我看看",
    ],
}

SCENE_LABELS = {
    "triage": "智能分诊",
    "consultation": "线上问诊",
    "medication": "用药咨询",
}


def match_department(text: str) -> Tuple[str, List[str], Dict[str, int]]:
    """基于关键词命中把症状映射到科室。

    :return: (推荐科室, 命中的症状词, 各科室得分)
    """
    if not text:
        return "内科", [], {}
    scores: Dict[str, int] = {}
    hits: List[str] = []
    for dept, keywords in DEPARTMENT_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                scores[dept] = scores.get(dept, 0) + 1
                if kw not in hits:
                    hits.append(kw)

    if not scores:
        return "内科", hits, scores

    # 权重微调：药物类问题优先药学门诊；急症关键词优先内科
    if "药学门诊" in scores:
        scores["药学门诊"] += 1
    priority = settings.DEPARTMENTS
    best = max(
        scores.items(),
        key=lambda kv: (kv[1], -priority.index(kv[0]) if kv[0] in priority else -999),
    )
    return best[0], hits, scores


def assess_risk(text: str, patient_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """本地风险评估（参考线索）。"""
    text = text or ""
    red_flags: List[str] = []
    medium_flags: List[str] = []

    for pattern, label in RED_FLAG_PATTERNS:
        if re.search(pattern, text):
            if label not in red_flags:
                red_flags.append(label)

    for pattern, label in MEDIUM_FLAG_PATTERNS:
        if re.search(pattern, text):
            if label not in medium_flags:
                medium_flags.append(label)

    # 高危既往史 / 特殊人群加权
    ctx = patient_context or {}
    age = str(ctx.get("age") or "")
    age_num = None
    m = re.search(r"\d+", age)
    if m:
        age_num = int(m.group(0))
    if age_num is not None and (age_num >= 70 or age_num <= 3):
        medium_flags.append("高龄/低龄特殊人群")

    chronic = str(ctx.get("chronic_diseases") or "")
    for disease in ("高血压", "糖尿病", "冠心病", "脑梗", "慢阻肺", "肿瘤", "肾病"):
        if disease in chronic:
            medium_flags.append(f"基础疾病：{disease}")

    if red_flags:
        level = "高风险"
    elif medium_flags:
        level = "中风险"
    else:
        level = "低风险"

    return {
        "risk_level": level,
        "red_flags": red_flags,
        "medium_flags": medium_flags,
        "reasons": red_flags + medium_flags,
    }


def route_scene(message: str, requested: str = "auto") -> Tuple[str, str]:
    """场景路由（RouterAgent 的规则部分）。

    :return: (场景, 路由依据)
    """
    if requested and requested not in ("auto", "", None):
        return requested, "请求显式指定场景"

    text = message or ""
    scores: Dict[str, int] = {}
    for scene, keywords in SCENE_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                scores[scene] = scores.get(scene, 0) + 1

    drug_hits = sum(1 for kw in DEPARTMENT_KEYWORDS["药学门诊"] if kw in text)
    if drug_hits:
        scores["medication"] = scores.get("medication", 0) + drug_hits

    if not scores:
        return "triage", "未命中场景关键词，默认走智能分诊"

    best = max(scores.items(), key=lambda kv: kv[1])[0]
    return best, f"命中「{SCENE_LABELS.get(best, best)}」关键词 {scores[best]} 处"


def build_search_query(message: str, patient_context: Optional[Dict[str, Any]], history: List[Dict]) -> str:
    """构造检索查询词（需求 3.2：追问场景使用最近若干条历史）。"""
    parts: List[str] = []
    if patient_context:
        ctx_text = " ".join(
            str(patient_context.get(k) or "")
            for k in ("chronic_diseases", "allergy_history", "medication_history")
        ).strip()
        if ctx_text:
            parts.append(ctx_text)
    parts.append(message or "")

    # 使用最近 4 条历史补充上下文，解决「刚才说的症状挂什么科」类追问
    recent = history[-4:] if history else []
    for item in recent:
        content = str(item.get("content") or "")
        if content:
            parts.append(content)
    return " ".join(p for p in parts if p).strip()[:500]


def risk_advice(level: str) -> str:
    if level == "高风险":
        return "建议立即线下就医或前往急诊，必要时拨打急救电话。"
    if level == "中风险":
        return "建议记录症状变化，必要时尽快到门诊就诊评估。"
    return "目前未识别明确高危信号，可先健康观察并调整生活方式，症状加重应及时就医。"


def fallback_structured(
    message: str,
    scene: str,
    patient_context: Optional[Dict[str, Any]],
    evidence: List[Dict[str, Any]],
    local_assessment: Optional[Dict[str, Any]] = None,
    degraded_reason: str = "",
) -> Dict[str, Any]:
    """规则兜底结果（需求 3.1 异常与降级 / 3.8 降级第 5 步）。"""
    assessment = local_assessment or assess_risk(message, patient_context)
    risk_level = assessment.get("risk_level", "低风险")
    department, hits, _ = match_department(message)

    if scene == "medication":
        department = "药学门诊"
    # 高风险统一建议急诊相关科室时仍保持系统科室范围内
    if risk_level == "高风险" and department == "内科":
        department = "内科"

    red_flags = assessment.get("red_flags") or []
    medium_flags = assessment.get("medium_flags") or []

    ctx = patient_context or {}
    ctx_text = "、".join(
        f"{k}：{ctx.get(k)}" for k in ("age", "gender", "chronic_diseases", "allergy_history", "medication_history")
        if ctx.get(k)
    ) or "未提供"

    if scene == "medication":
        conclusion = (
            f"您咨询的是用药相关问题（命中线索：{'、'.join(hits) if hits else '未识别明确药品名'}）。"
            "药物能否同服、是否需要调整，需结合具体药品、剂量、肝肾功能与合并疾病，"
            "建议携带正在服用的药品到药学门诊或由医生、药师评估。"
        )
    else:
        conclusion = (
            f"根据您描述的情况（命中线索：{'、'.join(hits) if hits else '未识别明确症状关键词'}），"
            f"建议优先到「{department}」就诊评估。"
        )

    if red_flags:
        conclusion += f" 已识别到需要警惕的信号：{'、'.join(red_flags)}，请尽快线下就医。"

    follow_up = []
    if not ctx.get("age"):
        follow_up.append("请问患者的年龄和性别？")
    if not ctx.get("chronic_diseases"):
        follow_up.append("是否有高血压、糖尿病等既往病史？")
    if not ctx.get("allergy_history"):
        follow_up.append("是否有药物过敏史？")
    follow_up.append("症状持续多久了？有没有加重或缓解的因素？")

    advice = [
        risk_advice(risk_level),
        "保持充足休息与水分摄入，避免自行加用未经评估的药物。",
        "如症状出现明显变化，请及时线下就医。",
    ]

    reason = "；".join(
        filter(
            None,
            [
                f"患者信息：{ctx_text}",
                f"本地症状-科室线索：{'、'.join(hits)}" if hits else "本地未命中明确症状关键词",
                f"风险线索：{'、'.join(red_flags + medium_flags)}" if (red_flags or medium_flags) else "未识别明确风险线索",
                f"知识库参考 {len(evidence)} 条" if evidence else "知识库未召回相关条目",
                f"降级原因：{degraded_reason}" if degraded_reason else "",
            ],
        )
    )

    return {
        "recommended_department": department,
        "risk_level": risk_level,
        "conclusion": conclusion,
        "reason": reason,
        "red_flags": red_flags,
        "follow_up": follow_up,
        "health_advice": advice,
        "source": "rule_fallback",
    }


def structured_to_answer(structured: Dict[str, Any], scene: str) -> str:
    """把结构化结果渲染为面向用户的自然语言回答。"""
    parts: List[str] = []
    dept = structured.get("recommended_department") or ""
    risk = structured.get("risk_level") or "低风险"
    conclusion = structured.get("conclusion") or ""

    if scene == "medication":
        if dept:
            parts.append(f"建议咨询科室：{dept}")
    elif dept:
        parts.append(f"推荐就诊科室：{dept}")
    parts.append(f"风险等级：{risk}")

    if conclusion:
        parts.append(conclusion)

    red_flags = structured.get("red_flags") or []
    if red_flags:
        parts.append(f"需要警惕的信号：{'、'.join(red_flags)}。")

    follow_up = structured.get("follow_up") or []
    if follow_up:
        parts.append("建议补充信息：" + " ".join(follow_up[:3]))

    advice = structured.get("health_advice") or []
    if advice:
        parts.append("健康建议：" + " ".join(advice[:3]))

    return "\n".join(parts).strip()


def symptom_hints(text: str) -> List[str]:
    hints: List[str] = []
    for keywords in DEPARTMENT_KEYWORDS.values():
        for kw in keywords:
            if kw in (text or "") and kw not in hints:
                hints.append(kw)
    return hints

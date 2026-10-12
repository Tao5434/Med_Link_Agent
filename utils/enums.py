"""数据库枚举值与中文展示值的双向映射。

数据库注释里对枚举的写法是「英文枚举；中文」，例如
``risk_level`` 为 ``low / medium / high；低 / 中 / 高风险``。
本项目统一 **入库存英文枚举**（与各表 DEFAULT、CHECK 语义一致），
**出库在 Service 层转回中文**，前端拿到的仍然是「中风险」这类可直接展示的值。
"""
from __future__ import annotations

# ---------------- 风险等级 ----------------
RISK_TO_DB = {"低风险": "low", "中风险": "medium", "高风险": "high"}
RISK_FROM_DB = {v: k for k, v in RISK_TO_DB.items()}


def risk_to_db(value: str) -> str:
    return RISK_TO_DB.get(str(value or "").strip(), "low")


def risk_from_db(value: str) -> str:
    text = str(value or "").strip()
    if text in RISK_FROM_DB:
        return RISK_FROM_DB[text]
    if text in RISK_TO_DB:  # 兼容历史中文数据
        return text
    return "低风险"


# ---------------- 就诊时段 ----------------
PERIOD_TO_DB = {"上午": "morning", "下午": "afternoon"}
PERIOD_FROM_DB = {v: k for k, v in PERIOD_TO_DB.items()}


def period_to_db(value: str) -> str:
    return PERIOD_TO_DB.get(str(value or "").strip(), "morning")


def period_from_db(value: str) -> str:
    text = str(value or "").strip()
    if text in PERIOD_FROM_DB:
        return PERIOD_FROM_DB[text]
    if text in PERIOD_TO_DB:
        return text
    return "上午"


# ---------------- 预约状态 ----------------
STATUS_BOOKED = "booked"
STATUS_CANCELLED = "cancelled"
STATUS_TO_DB = {"已预约": STATUS_BOOKED, "已取消": STATUS_CANCELLED, STATUS_BOOKED: STATUS_BOOKED, STATUS_CANCELLED: STATUS_CANCELLED}
STATUS_FROM_DB = {STATUS_BOOKED: "已预约", STATUS_CANCELLED: "已取消"}


def status_from_db(value: str) -> str:
    return STATUS_FROM_DB.get(str(value or "").strip(), "已预约")


# ---------------- 报告类型 ----------------
REPORT_TYPE_TO_DB = {"检验": "laboratory", "检查": "examination"}
REPORT_TYPE_FROM_DB = {v: k for k, v in REPORT_TYPE_TO_DB.items()}


def report_type_from_db(value: str) -> str:
    text = str(value or "").strip()
    if text in REPORT_TYPE_FROM_DB:
        return REPORT_TYPE_FROM_DB[text]
    if text in REPORT_TYPE_TO_DB:
        return text
    return "检验"


# ---------------- 指标异常标记 ----------------
FLAG_NORMAL = "normal"
FLAG_HIGH = "high"
FLAG_LOW = "low"
FLAG_ABNORMAL = "abnormal"
FLAG_FROM_DB = {
    FLAG_NORMAL: "正常",
    FLAG_HIGH: "偏高",
    FLAG_LOW: "偏低",
    FLAG_ABNORMAL: "异常",
}
FLAG_TO_DB = {v: k for k, v in FLAG_FROM_DB.items()}


def flag_from_db(value: str) -> str:
    text = str(value or "").strip()
    if text in FLAG_FROM_DB:
        return FLAG_FROM_DB[text]
    if text in FLAG_TO_DB:
        return text
    return "正常"


def flag_to_db(value: str) -> str:
    return FLAG_TO_DB.get(str(value or "").strip(), FLAG_ABNORMAL)


# ---------------- 性别 ----------------
GENDER_TO_DB = {"男": "male", "女": "female", "其他": "other"}
GENDER_FROM_DB = {v: k for k, v in GENDER_TO_DB.items()}


def gender_to_db(value: str) -> str:
    text = str(value or "").strip()
    if text in GENDER_TO_DB:
        return GENDER_TO_DB[text]
    if text in GENDER_FROM_DB:
        return text
    return "other"


def gender_from_db(value: str) -> str:
    text = str(value or "").strip()
    if text in GENDER_FROM_DB:
        return GENDER_FROM_DB[text]
    if text in GENDER_TO_DB:
        return text
    return ""


# ---------------- 场景 ----------------
SCENE_FROM_DB = {"triage": "分诊", "consultation": "问诊", "medication": "用药"}
SCENE_FULL_FROM_DB = {"triage": "智能分诊", "consultation": "线上问诊", "medication": "用药咨询"}

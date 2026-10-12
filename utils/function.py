"""通用工具函数。"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta
from typing import Optional


def md5_encrypt(text: str) -> str:
    """
    md5加密
    :param text: 加密的文本
    :return: 加密后的文本
    """
    data = text.encode("utf-8")
    md5_obj = hashlib.md5(data)
    return md5_obj.hexdigest()


def now_str() -> str:
    """统一时间格式：YYYY-MM-DD HH:MM:SS。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def new_session_id() -> str:
    return str(uuid.uuid4())


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def date_after(days: int = 0) -> str:
    return (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")


def parse_date(value: str) -> Optional[datetime]:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(str(value)[: len(fmt) + 2].strip(), fmt)
        except ValueError:
            continue
    return None


def weekday_cn(date_str: str) -> str:
    dt = parse_date(date_str)
    if not dt:
        return ""
    return ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][dt.weekday()]


def appointment_code(appointment_id: int) -> str:
    """预约单号展示格式：YL + 6 位数字（需求 5）。"""
    return f"YL{int(appointment_id):06d}"

"""健康档案表数据访问（`health_profiles`）。

字段：id(char36) / user_id(int) / age(tinyint) / gender /
      chronic_diseases(JSON) / allergy_history(JSON) / medication_history(JSON) / update_time

注意 ``user_id`` 在此表是 **int**，关联 ``user.id``；其余业务表用的是 char(36)。
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Dict, Optional

from utils.db import db
from utils.enums import gender_from_db, gender_to_db


class HealthProfileDao:
    @staticmethod
    def get(user_id: int) -> Optional[dict]:
        row = db.query_one(
            "SELECT id, user_id, age, gender, chronic_diseases, allergy_history, "
            "medication_history, update_time FROM health_profiles WHERE user_id = %s "
            "ORDER BY update_time DESC LIMIT 1",
            (user_id,),
        )
        return HealthProfileDao._decode(row) if row else None

    @staticmethod
    def upsert(user_id: int, profile: Dict[str, Any]) -> None:
        age = _to_int(profile.get("age"))
        gender = gender_to_db(profile.get("gender"))
        chronic = _dumps(profile.get("chronic_diseases"))
        allergy = _dumps(profile.get("allergy_history"))
        medication = _dumps(profile.get("medication_history"))

        exists = HealthProfileDao.get(user_id)
        if exists:
            db.update(
                "UPDATE health_profiles SET age = %s, gender = %s, chronic_diseases = %s, "
                "allergy_history = %s, medication_history = %s, update_time = NOW() "
                "WHERE id = %s",
                (age, gender, chronic, allergy, medication, exists["id"]),
            )
        else:
            db.execute(
                "INSERT INTO health_profiles (id, user_id, age, gender, chronic_diseases, "
                "allergy_history, medication_history, update_time) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())",
                (str(uuid.uuid4()), user_id, age, gender, chronic, allergy, medication),
            )

    @staticmethod
    def _decode(row: dict) -> dict:
        row["gender"] = gender_from_db(row.get("gender"))
        for key in ("chronic_diseases", "allergy_history", "medication_history"):
            row[key] = _loads(row.get(key))
        return row

    @staticmethod
    def clear_all() -> None:
        db.delete("DELETE FROM health_profiles")


def _to_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return max(0, min(int(float(str(value))), 255))
    except (TypeError, ValueError):
        return None


def _dumps(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        return json.dumps([value], ensure_ascii=False)
    return json.dumps(value, ensure_ascii=False)


def _loads(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None

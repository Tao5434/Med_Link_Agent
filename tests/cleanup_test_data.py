"""清理验收自测脚本产生的测试账号及其业务数据。

`tests/test_acceptance.py` 为了验证「号源约满」等场景，会批量注册
`user*/bk*/late*` 形式的临时账号。本脚本把这些临时账号及其名下的
会话、消息、问诊记录、预约、报告、健康档案一并删除，
**不会触碰 admin、zhangsan 等真实账号**。

运行：
    python tests/cleanup_test_data.py           # 清理
    python tests/cleanup_test_data.py --dry-run # 只统计不删除
"""
from __future__ import annotations

import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

from utils.db import db  # noqa: E402

# 仅匹配测试脚本生成的账号：user123456 / bk1234560 / late123456
TEST_ACCOUNT_PATTERN = r"^(user|bk|late)[0-9]+$"


def cleanup(dry_run: bool = False) -> dict:
    db.init()

    rows = db.query_all(
        "SELECT id, account FROM `user` WHERE account REGEXP %s ORDER BY id",
        (TEST_ACCOUNT_PATTERN,),
    )
    ids = [r["id"] for r in rows]
    kept = [
        r["account"]
        for r in db.query_all(
            "SELECT account FROM `user` WHERE account NOT REGEXP %s ORDER BY id",
            (TEST_ACCOUNT_PATTERN,),
        )
    ]

    summary = {"test_accounts": len(ids), "accounts": [r["account"] for r in rows], "kept": kept}
    if dry_run or not ids:
        return summary

    id_list = ",".join(str(i) for i in ids)
    uid_list = ",".join(f"'{i}'" for i in ids)  # 业务表的 user_id 是 char(36)

    with db.transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"DELETE a FROM appointments a WHERE a.user_id IN ({uid_list})"
            )
            summary["appointments"] = cur.rowcount

            cur.execute(f"DELETE e FROM encounters e WHERE e.user_id IN ({uid_list})")
            summary["encounters"] = cur.rowcount

            cur.execute(
                f"DELETE m FROM messages m JOIN sessions s ON m.session_id = s.id "
                f"WHERE s.user_id IN ({uid_list})"
            )
            summary["messages"] = cur.rowcount

            cur.execute(f"DELETE FROM sessions WHERE user_id IN ({uid_list})")
            summary["sessions"] = cur.rowcount

            cur.execute(
                f"DELETE ri FROM report_items ri JOIN reports r ON r.id = ri.report_id "
                f"WHERE r.user_id IN ({uid_list})"
            )
            summary["report_items"] = cur.rowcount

            cur.execute(f"DELETE FROM reports WHERE user_id IN ({uid_list})")
            summary["reports"] = cur.rowcount

            cur.execute(f"DELETE FROM health_profiles WHERE user_id IN ({id_list})")
            summary["health_profiles"] = cur.rowcount

            cur.execute(f"DELETE FROM `user` WHERE id IN ({id_list})")
            summary["user"] = cur.rowcount

    # 重算医生已预约数，避免残留计数
    db.execute(
        "UPDATE doctor_schedules ds SET ds.booked_slots = ("
        "  SELECT COUNT(*) FROM appointments a WHERE a.doctor = ds.doctor "
        "    AND a.department = (SELECT d.department_name FROM departments d "
        "                        WHERE d.department_code = ds.department_code LIMIT 1) "
        "    AND a.status = 'booked')"
    )
    return summary


def sweep_orphan_files(dry_run: bool = False) -> dict:
    """清理 ``data/uploads`` 下没有对应 ``report_files`` 记录的残留文件。

    上传流程是「先落盘、再写库」，如果写库阶段失败就会留下孤儿文件，
    这里做一次兜底清理。
    """
    from config.settings import settings

    uploads_root = settings.UPLOAD_DIR
    if not uploads_root.exists():
        return {"orphan_files": 0, "orphan_bytes": 0, "removed": []}

    known = {
        row["file_path"].replace("\\", "/")
        for row in db.query_all("SELECT file_path FROM report_files")
    }

    orphans = []
    total_bytes = 0
    for path in uploads_root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(settings.DATA_DIR).as_posix()
        if rel not in known:
            orphans.append(path)
            total_bytes += path.stat().st_size

    removed = []
    if not dry_run:
        for path in orphans:
            try:
                path.unlink()
                removed.append(path.name)
            except OSError:
                pass
    return {
        "orphan_files": len(orphans),
        "orphan_bytes": total_bytes,
        "removed": removed,
    }


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    result = cleanup(dry_run=dry)
    print(f"匹配到的测试账号：{result['test_accounts']} 个")
    if result["accounts"]:
        print("  " + "、".join(result["accounts"][:10]) +
              ("…" if len(result["accounts"]) > 10 else ""))
    print(f"保留的账号：{'、'.join(result['kept']) or '（无）'}")
    if not dry:
        for key in ("user", "sessions", "messages", "encounters", "appointments",
                    "reports", "report_items", "health_profiles"):
            if key in result:
                print(f"已删除 {key}: {result[key]}")

    orphan = sweep_orphan_files(dry_run=dry)
    print(f"上传目录孤儿文件：{orphan['orphan_files']} 个"
          f"（{orphan['orphan_bytes'] / 1024:.1f} KB）"
          + ("，已删除" if not dry else "，dry-run 未删除"))

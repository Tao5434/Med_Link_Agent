"""报告主表与指标明细表数据访问（`reports` / `report_items`）。

报告为每个用户按需生成并落库（3 份：血常规 / 胸部 CT / 肝肾功能），
之后读取都走数据库，不再依赖内存常量。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from utils.db import db
from utils.enums import flag_from_db, flag_to_db, report_type_from_db

# 指标编码前缀（item_code）
_ITEM_CODE = {
    "白细胞计数 WBC": "WBC",
    "中性粒细胞百分比 NEUT%": "NEUT",
    "淋巴细胞百分比 LYMPH%": "LYMPH",
    "红细胞计数 RBC": "RBC",
    "血红蛋白 HGB": "HGB",
    "血小板计数 PLT": "PLT",
    "C 反应蛋白 CRP": "CRP",
    "右肺下叶": "CT-RLL",
    "左肺": "CT-LLL",
    "纵隔淋巴结": "CT-MED",
    "胸腔积液": "CT-PE",
    "胸膜": "CT-PLE",
    "丙氨酸氨基转移酶 ALT": "ALT",
    "天门冬氨酸氨基转移酶 AST": "AST",
    "总胆红素 TBIL": "TBIL",
    "白蛋白 ALB": "ALB",
    "肌酐 CREA": "CREA",
    "尿素 UREA": "UREA",
}


class ReportDao:
    # ------------------------------------------------------------------
    @staticmethod
    def list_by_user(user_id: str) -> List[Dict[str, Any]]:
        reports = db.query_all(
            "SELECT id, report_no, user_id, report_name, report_type, hospital, department, "
            "report_date, summary, create_time FROM reports WHERE user_id = %s "
            "ORDER BY report_date ASC, id ASC",
            (user_id,),
        )
        # 一次查出该用户所有附件，避免逐条报告再查一次
        files: Dict[int, dict] = {}
        for row in db.query_all(
            "SELECT id, report_id, file_name, file_path, file_size, content_type, parse_note, "
            "upload_time FROM report_files WHERE user_id = %s ORDER BY id ASC",
            (user_id,),
        ):
            files[row["report_id"]] = row
        for report in reports:
            report["items"] = ReportDao.items_of(report["id"])
            report["file"] = files.get(report["id"])
        return reports

    @staticmethod
    def get(report_id: int, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if user_id:
            report = db.query_one(
                "SELECT id, report_no, user_id, report_name, report_type, hospital, department, "
                "report_date, summary FROM reports WHERE id = %s AND user_id = %s",
                (report_id, user_id),
            )
        else:
            report = db.query_one(
                "SELECT id, report_no, user_id, report_name, report_type, hospital, department, "
                "report_date, summary FROM reports WHERE id = %s",
                (report_id,),
            )
        if report:
            report["items"] = ReportDao.items_of(report["id"])
            report["file"] = ReportDao.file_of(report["id"])
        return report

    @staticmethod
    def items_of(report_id: int) -> List[Dict[str, Any]]:
        rows = db.query_all(
            "SELECT id, item_name, item_code, item_value, unit, reference_range, abnormal_flag, "
            "sort_order FROM report_items WHERE report_id = %s ORDER BY sort_order ASC, id ASC",
            (report_id,),
        )
        return [ReportDao._decode_item(r) for r in rows]

    @staticmethod
    def _decode_item(row: dict) -> dict:
        row["abnormal_flag"] = flag_from_db(row.get("abnormal_flag"))
        return row

    # ------------------------------------------------------------------
    @staticmethod
    def create(report: Dict[str, Any]) -> int:
        return db.insert_one(
            "INSERT INTO reports (report_no, user_id, report_name, report_type, hospital, "
            "department, report_date, summary, create_time) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())",
            (
                report.get("report_no"),
                report.get("user_id"),
                report.get("report_name"),
                report.get("report_type"),
                report.get("hospital"),
                report.get("department"),
                report.get("report_date"),
                report.get("summary"),
            ),
        )

    @staticmethod
    def add_items(report_id: int, items: List[Dict[str, Any]]) -> None:
        if not items:
            return
        rows = []
        for index, item in enumerate(items):
            name = item.get("name") or item.get("item_name") or ""
            rows.append(
                (
                    report_id,
                    name,
                    item.get("item_code") or _ITEM_CODE.get(name),
                    item.get("value") or item.get("item_value"),
                    item.get("unit"),
                    item.get("ref") or item.get("reference_range"),
                    flag_to_db(item.get("flag") or item.get("abnormal_flag")),
                    item.get("sort_order", index),
                )
            )
        db.execute_many(
            "INSERT INTO report_items (report_id, item_name, item_code, item_value, unit, "
            "reference_range, abnormal_flag, sort_order, create_time) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())",
            rows,
        )

    @staticmethod
    def update_summary(report_id: int, summary: str) -> int:
        return db.update("UPDATE reports SET summary = %s WHERE id = %s", (summary, report_id))

    @staticmethod
    def count_by_user(user_id: str) -> int:
        row = db.query_one("SELECT COUNT(*) AS c FROM reports WHERE user_id = %s", (user_id,))
        return int(row["c"]) if row else 0

    @staticmethod
    def count_builtin_by_user(user_id: str) -> int:
        """内置演示报告的数量（report_no 以 RPT 开头，上传报告以 UPL 开头）。"""
        row = db.query_one(
            "SELECT COUNT(*) AS c FROM reports WHERE user_id = %s AND report_no LIKE 'RPT%%'",
            (user_id,),
        )
        return int(row["c"]) if row else 0

    @staticmethod
    def delete_by_user(user_id: str) -> None:
        with db.transaction() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE ri FROM report_items ri JOIN reports r ON r.id = ri.report_id "
                    "WHERE r.user_id = %s",
                    (user_id,),
                )
                cur.execute("DELETE FROM reports WHERE user_id = %s", (user_id,))

    @staticmethod
    def delete(report_id: int, user_id: Optional[str] = None) -> int:
        """删除一份报告及其指标明细与附件，返回删除的报告数。"""
        with db.transaction() as conn:
            with conn.cursor() as cur:
                if user_id:
                    cur.execute(
                        "DELETE FROM report_items WHERE report_id IN "
                        "(SELECT id FROM reports WHERE id = %s AND user_id = %s)",
                        (report_id, user_id),
                    )
                    cur.execute(
                        "DELETE FROM report_files WHERE report_id IN "
                        "(SELECT id FROM reports WHERE id = %s AND user_id = %s)",
                        (report_id, user_id),
                    )
                    affected = cur.execute(
                        "DELETE FROM reports WHERE id = %s AND user_id = %s",
                        (report_id, user_id),
                    )
                else:
                    cur.execute("DELETE FROM report_items WHERE report_id = %s", (report_id,))
                    cur.execute("DELETE FROM report_files WHERE report_id = %s", (report_id,))
                    affected = cur.execute("DELETE FROM reports WHERE id = %s", (report_id,))
        return affected

    # ------------------------------------------------------------------
    # 报告附件（上传功能）
    # ------------------------------------------------------------------
    @staticmethod
    def add_file(
        report_id: int,
        user_id: str,
        file_name: str,
        file_path: str,
        file_size: int,
        content_type: str,
        parse_note: str = "",
    ) -> int:
        return db.insert_one(
            "INSERT INTO report_files (report_id, user_id, file_name, file_path, file_size, "
            "content_type, parse_note, upload_time) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())",
            (report_id, user_id, file_name, file_path, file_size, content_type, parse_note[:255]),
        )

    @staticmethod
    def file_of(report_id: int) -> Optional[dict]:
        return db.query_one(
            "SELECT id, report_id, user_id, file_name, file_path, file_size, content_type, "
            "parse_note, upload_time FROM report_files WHERE report_id = %s "
            "ORDER BY id DESC LIMIT 1",
            (report_id,),
        )

    @staticmethod
    def delete_file(report_id: int) -> int:
        return db.delete("DELETE FROM report_files WHERE report_id = %s", (report_id,))

    @staticmethod
    def clear_all() -> None:
        with db.transaction() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM report_files")
                cur.execute("DELETE FROM report_items")
                cur.execute("DELETE FROM reports")

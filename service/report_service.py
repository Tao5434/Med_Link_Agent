"""报告查询、上传与 AI 解读服务（需求 3.4 FR-REPORT）。

报告数据来自数据库：用户首次访问时，把内置的 3 份模拟报告
（血常规 / 胸部 CT / 肝肾功能）写入 ``reports`` + ``report_items``；
用户上传的报告同样落库，并在 ``report_files`` 中保留原始附件。
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.settings import settings
from dao.report_dao import ReportDao
from service import report_data, report_parser
from utils.compliance import compliance_guard
from utils.enums import REPORT_TYPE_TO_DB, flag_from_db, report_type_from_db

from agent import prompts
from agent.llm import llm_client

logger = logging.getLogger(__name__)


class ReportUploadError(ValueError):
    """报告上传校验失败（对应用户可见的提示）。"""


def _human_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / 1024 / 1024:.2f} MB"


class ReportService:
    # ------------------------------------------------------------------
    @staticmethod
    def ensure_user_reports(user_id: str) -> None:
        """用户还没有内置报告时，把内置模板写入数据库（只写一次）。

        判断依据是 ``report_no`` 以 ``RPT`` 开头的报告数，
        这样即使用户先上传了报告，内置的 3 份演示报告依然会补齐。
        """
        if ReportDao.count_builtin_by_user(user_id) > 0:
            return
        base = datetime.now()
        for index, tpl in enumerate(report_data.REPORT_TEMPLATES):
            report_id = ReportDao.create(
                {
                    "report_no": f"RPT{user_id}{index + 1:02d}{base.strftime('%m%d')}",
                    "user_id": user_id,
                    "report_name": tpl["title"],
                    "report_type": report_data.REPORT_TYPE_DB.get(tpl.get("type"), "laboratory"),
                    "hospital": tpl.get("institution"),
                    "department": tpl.get("department"),
                    "report_date": (base - timedelta(days=14 - index * 2)).strftime("%Y-%m-%d"),
                    "summary": tpl.get("summary"),
                }
            )
            ReportDao.add_items(report_id, tpl.get("items") or [])
            logger.info("为用户 %s 初始化报告：%s (id=%s)", user_id, tpl["title"], report_id)

    # ------------------------------------------------------------------
    @staticmethod
    def list_reports(user_id: str) -> List[dict]:
        ReportService.ensure_user_reports(user_id)
        return [ReportService._to_card(r) for r in ReportDao.list_by_user(user_id)]

    @staticmethod
    def _to_card(report: dict) -> dict:
        abnormal = [i for i in report.get("items", []) if i.get("abnormal_flag") != "正常"]
        file_row = report.get("file") or None
        return {
            "id": report["id"],
            "report_no": report.get("report_no"),
            "title": report.get("report_name"),
            "type": report_type_from_db(report.get("report_type")),
            "department": report.get("department") or "",
            "institution": report.get("hospital") or "",
            "report_date": str(report.get("report_date") or ""),
            "summary": report.get("summary") or "",
            "abnormal_count": len(abnormal),
            "risk_level": "中风险" if abnormal else "低风险",
            "source": "upload" if file_row else "builtin",
            "file": (
                {
                    "name": file_row.get("file_name"),
                    "size": int(file_row.get("file_size") or 0),
                    "size_text": _human_size(int(file_row.get("file_size") or 0)),
                    "content_type": file_row.get("content_type") or "",
                    "parse_note": file_row.get("parse_note") or "",
                    "upload_time": str(file_row.get("upload_time") or ""),
                }
                if file_row
                else None
            ),
            "items": [
                {
                    "name": i.get("item_name"),
                    "code": i.get("item_code"),
                    "value": i.get("item_value"),
                    "unit": i.get("unit") or "",
                    "ref": i.get("reference_range") or "",
                    "flag": i.get("abnormal_flag") or "正常",
                }
                for i in report.get("items", [])
            ],
        }

    # ------------------------------------------------------------------
    @staticmethod
    def interpret(report_id: int, user_id: str) -> Optional[Dict]:
        """解读指定报告：异常项 → 科普解释 + 就医建议。"""
        ReportService.ensure_user_reports(user_id)
        raw = ReportDao.get(report_id, user_id)
        if not raw:
            return None
        card = ReportService._to_card(raw)
        abnormal = [i for i in card["items"] if i["flag"] != "正常"]
        risk_level = "中风险" if abnormal else "低风险"
        analysis = report_data.build_analysis(card)

        interpretation = ReportService._llm_interpret(card, abnormal)
        used_llm = bool(interpretation)
        if not interpretation:
            interpretation = report_data.build_interpretation(card)

        guarded, audit = compliance_guard(interpretation)

        return {
            "id": card["id"],
            "title": card["title"],
            "type": card["type"],
            "department": card["department"],
            "report_date": card["report_date"],
            "institution": card["institution"],
            "risk_level": risk_level,
            "abnormal_count": len(abnormal),
            "analysis": analysis,
            "interpretation": guarded,
            "items": card["items"],
            "summary": card["summary"],
            "compliance": audit,
            "interpreter": "llm" if used_llm else "report_fallback",
        }

    # ------------------------------------------------------------------
    @staticmethod
    def _llm_interpret(report: Dict, abnormal: List[Dict]) -> Optional[str]:
        if not (llm_client.available and llm_client.probe()):
            return None

        item_lines = "\n".join(
            f"- {i['name']}：{i['value']}{i['unit']}（参考范围 {i['ref']}，结果 {i['flag']}）"
            for i in report.get("items", [])
        )
        user_prompt = (
            f"报告名称：{report['title']}（{report.get('type', '检验')}）\n"
            f"检查机构：{report.get('institution', '')}\n"
            f"报告结论：{report.get('summary', '')}\n"
            f"指标明细：\n{item_lines}\n\n"
            f"其中异常项 {len(abnormal)} 个。请给出通俗的科普解释与就医建议，"
            f"并说明建议挂哪个科室（当前建议科室：{report.get('department', '内科')}）。"
        )
        try:
            return llm_client.chat(
                [
                    {"role": "system", "content": prompts.REPORT_INTERPRET_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=600,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("报告 AI 解读失败，使用规则兜底: %s", exc)
            return None

    # ------------------------------------------------------------------
    # 报告上传
    # ------------------------------------------------------------------
    @staticmethod
    def upload(
        user: dict,
        filename: str,
        data: bytes,
        content_type: str = "",
        report_name: str = "",
        report_type: str = "",
        hospital: str = "",
        department: str = "",
        report_date: str = "",
    ) -> Dict[str, Any]:
        """保存上传的报告文件、解析指标并落库。

        :return: {"report": 报告卡片, "parse": 解析说明}
        """
        user_id = user["user_id"]
        filename = (filename or "").strip()
        if not filename:
            raise ReportUploadError("未获取到文件名，请重新选择文件")
        if not data:
            raise ReportUploadError("上传的文件为空")

        ext = Path(filename).suffix.lower().lstrip(".")
        if ext not in settings.UPLOAD_ALLOWED_EXT:
            raise ReportUploadError(
                f"不支持的文件类型 .{ext}，请上传：{'、'.join(settings.UPLOAD_ALLOWED_EXT)}"
            )

        max_bytes = settings.UPLOAD_MAX_MB * 1024 * 1024
        if len(data) > max_bytes:
            raise ReportUploadError(
                f"文件超过大小限制（{settings.UPLOAD_MAX_MB} MB），当前 "
                f"{_human_size(len(data))}"
            )

        # 1) 落盘：data/uploads/<user_id>/<uuid>.<ext>
        rel_dir = Path("uploads") / user_id
        abs_dir = settings.DATA_DIR / rel_dir
        abs_dir.mkdir(parents=True, exist_ok=True)
        stored_name = f"{uuid.uuid4().hex}{Path(filename).suffix.lower()}"
        abs_path = abs_dir / stored_name
        abs_path.write_bytes(data)
        rel_path = (rel_dir / stored_name).as_posix()

        # 2) 文本抽取 + 指标识别（正则优先，模型兜底）
        text, note = report_parser.extract_text(filename, data)
        items = report_parser.parse_items(text)
        parser_used = "regex" if items else "none"

        if not items and text.strip() and llm_client.available and llm_client.probe():
            items = ReportService._llm_extract_items(text)
            if items:
                parser_used = "llm"

        # 3) 元信息：表单优先，其次自动推断
        meta = report_parser.guess_meta(text, filename)
        name = (report_name or "").strip() or meta["report_name"]
        type_db = (
            REPORT_TYPE_TO_DB.get((report_type or "").strip(), meta["report_type"])
            if (report_type or "").strip()
            else meta["report_type"]
        )
        dept = (department or "").strip() or report_parser.guess_department(text, name) or ""
        hosp = (hospital or "").strip()
        visit_date = _safe_date(report_date) or date.today().strftime("%Y-%m-%d")

        if not items:
            note = f"{note}；未自动识别到指标明细，可人工补录后重新解读"

        summary = (
            f"用户上传报告（{note}）。自动识别 {len(items)} 项指标，"
            f"其中异常 {sum(1 for i in items if i.get('flag') != '正常')} 项。"
        )

        report_no = f"UPL{user_id}{datetime.now().strftime('%y%m%d%H%M%S')}"
        report_id = ReportDao.create(
            {
                "report_no": report_no,
                "user_id": user_id,
                "report_name": name,
                "report_type": type_db,
                "hospital": hosp,
                "department": dept,
                "report_date": visit_date,
                "summary": summary,
            }
        )
        if items:
            ReportDao.add_items(report_id, items)
        ReportDao.add_file(
            report_id=report_id,
            user_id=user_id,
            file_name=filename,
            file_path=rel_path,
            file_size=len(data),
            content_type=content_type or "",
            parse_note=note,
        )

        logger.info(
            "用户 %s 上传报告 %s（%s，%d 字节），解析出 %d 项指标（%s）",
            user_id, report_no, filename, len(data), len(items), parser_used,
        )

        raw = ReportDao.get(report_id, user_id)
        return {
            "report": ReportService._to_card(raw) if raw else None,
            "parse": {
                "text_length": len(text),
                "item_count": len(items),
                "parser": parser_used,
                "note": note,
                "file_name": filename,
                "file_size": len(data),
                "file_size_text": _human_size(len(data)),
            },
        }

    @staticmethod
    def _llm_extract_items(text: str) -> List[dict]:
        """大模型兜底：从自由文本中抽取指标明细。"""
        prompt = (
            "下面是一份检验/检查报告的文本。请抽取其中的指标明细，"
            "只输出 JSON，格式为：\n"
            '{"items":[{"name":"指标名称","value":"结果","unit":"单位",'
            '"ref":"参考范围","flag":"正常|偏高|偏低|异常"}]}\n'
            "规则：flag 必须从 正常/偏高/偏低/异常 中选一个；"
            "没有参考范围时 ref 留空；无法判断异常时 flag 填「异常」。\n"
            "只输出 JSON，不要输出解释。\n\n报告文本：\n" + text[:6000]
        )
        try:
            data = llm_client.chat_json(
                [
                    {"role": "system", "content": "你是医学检验报告结构化助手。"},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=1500,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("大模型抽取指标失败：%s", exc)
            return []

        raw_items = (data or {}).get("items")
        if not isinstance(raw_items, list):
            return []

        items: List[dict] = []
        for entry in raw_items[:200]:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or "").strip()
            if not name:
                continue
            flag = str(entry.get("flag") or "异常").strip()
            if flag not in ("正常", "偏高", "偏低", "异常"):
                flag = "异常"
            items.append(
                {
                    "name": name[:100],
                    "code": None,
                    "value": str(entry.get("value") or "").strip()[:50],
                    "unit": str(entry.get("unit") or "").strip()[:20],
                    "ref": str(entry.get("reference_range") or entry.get("ref") or "").strip()[:50],
                    "flag": flag,
                }
            )
        return items

    # ------------------------------------------------------------------
    @staticmethod
    def delete(report_id: int, user_id: str) -> bool:
        """删除报告及其附件文件。"""
        raw = ReportDao.get(report_id, user_id)
        if not raw:
            return False
        file_row = raw.get("file")
        affected = ReportDao.delete(report_id, user_id)
        if affected and file_row:
            try:
                target = (settings.DATA_DIR / file_row["file_path"]).resolve()
                uploads_root = settings.UPLOAD_DIR.resolve()
                # 只允许删除 uploads 目录内的文件
                if str(target).startswith(str(uploads_root)) and target.is_file():
                    target.unlink()
            except OSError as exc:
                logger.warning("删除报告附件失败：%s", exc)
        return affected > 0

    @staticmethod
    def file_of(report_id: int, user_id: str) -> Optional[Dict[str, Any]]:
        """获取报告附件信息（用于下载）。"""
        raw = ReportDao.get(report_id, user_id)
        if not raw or not raw.get("file"):
            return None
        file_row = raw["file"]
        target = (settings.DATA_DIR / file_row["file_path"]).resolve()
        uploads_root = settings.UPLOAD_DIR.resolve()
        if not str(target).startswith(str(uploads_root)) or not target.is_file():
            return None
        return {
            "absolute_path": target,
            "file_name": file_row["file_name"],
            "content_type": file_row.get("content_type") or "application/octet-stream",
        }


def _safe_date(value: str) -> Optional[str]:
    """把用户输入归一化为 YYYY-MM-DD，非法则返回 None。"""
    text = (value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


# 兼容：report_data 中不再需要 flag 转换，这里统一由 ReportService 处理
_ = flag_from_db

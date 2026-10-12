"""报告查询、上传与 AI 解读接口（需求 3.4 FR-REPORT）。

报告数据来自数据库 ``reports`` / ``report_items``；
用户上传的报告在 ``report_files`` 中保留原始附件。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse

from config.settings import settings
from service.report_service import ReportService, ReportUploadError
from utils.response_model import error_message, success_data, success_data_message
from utils.security import current_user

report_router = APIRouter(prefix="/api/reports", tags=["报告查询"])


@report_router.get("", summary="我的报告列表")
async def list_reports(user: dict = Depends(current_user)):
    reports = ReportService.list_reports(user["user_id"])
    uploaded = sum(1 for r in reports if r.get("source") == "upload")
    return success_data(
        {
            "reports": reports,
            "total": len(reports),
            "uploaded_total": uploaded,
            "upload_max_mb": settings.UPLOAD_MAX_MB,
            "upload_allowed_ext": settings.UPLOAD_ALLOWED_EXT,
        }
    )


@report_router.post("/upload", summary="上传报告文件并自动解析指标")
async def upload_report(
    file: UploadFile = File(..., description="报告文件（PDF / 文本 / 图片 / Word / Excel）"),
    report_name: str = Form("", description="报告名称，留空自动识别"),
    report_type: str = Form("", description="报告类型：检验 / 检查，留空自动识别"),
    hospital: str = Form("", description="医院名称"),
    department: str = Form("", description="开单科室"),
    report_date: str = Form("", description="报告日期 YYYY-MM-DD"),
    user: dict = Depends(current_user),
):
    data = await file.read()
    try:
        result = ReportService.upload(
            user=user,
            filename=file.filename or "",
            data=data,
            content_type=file.content_type or "",
            report_name=report_name,
            report_type=report_type,
            hospital=hospital,
            department=department,
            report_date=report_date,
        )
    except ReportUploadError as exc:
        return error_message(str(exc))
    return success_data_message(result, "报告上传成功")


@report_router.get("/{report_id}/interpret", summary="报告 AI 解读")
async def interpret_report(report_id: int, user: dict = Depends(current_user)):
    result = ReportService.interpret(report_id, user["user_id"])
    if not result:
        return error_message("报告不存在")
    return success_data(result)


@report_router.get("/{report_id}/file", summary="下载报告原始附件")
async def download_report_file(report_id: int, user: dict = Depends(current_user)):
    info = ReportService.file_of(report_id, user["user_id"])
    if not info:
        return error_message("该报告没有可下载的附件")
    return FileResponse(
        path=str(info["absolute_path"]),
        filename=info["file_name"],
        media_type=info["content_type"],
    )


@report_router.delete("/{report_id}", summary="删除报告（含附件）")
async def delete_report(report_id: int, user: dict = Depends(current_user)):
    if not ReportService.delete(report_id, user["user_id"]):
        return error_message("报告不存在或无权删除")
    return success_data_message({"ok": True, "report_id": report_id}, "报告已删除")

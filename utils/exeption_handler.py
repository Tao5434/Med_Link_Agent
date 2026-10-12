"""全局异常处理（统一响应结构）。"""
from __future__ import annotations

import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """服务器内部错误。"""
    logger.exception("未捕获异常: %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"code": 500, "message": "服务器内部错误", "data": str(exc)},
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """HTTP 异常（含 400「当前号源已约满」等业务异常）。"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code, "message": exc.detail, "data": None},
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """参数验证异常。"""
    errors = exc.errors()
    for err in errors:
        err.pop("ctx", None)
        if isinstance(err.get("input"), (bytes, bytearray)):
            err["input"] = err["input"].decode("utf-8", "replace")
    return JSONResponse(
        status_code=422,
        content={"code": 422, "message": "输入参数错误", "data": errors},
    )

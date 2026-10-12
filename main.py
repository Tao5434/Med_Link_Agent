"""诊小通 Agent 后端服务入口（FastAPI）。

启动：
    python main.py                 # 默认监听 0.0.0.0:8012
    uvicorn main:app --reload      # 开发模式

接口文档：http://127.0.0.1:8012/docs
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.middleware.cors import CORSMiddleware

from config.settings import settings
from routers.api import api_routers
from utils.db import db
from utils.exeption_handler import (
    global_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("med_link_agent")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时初始化数据库与知识库，并打印运行态摘要。"""
    from utils.db import DatabaseError

    try:
        db.init()
    except DatabaseError as exc:
        # MySQL 不可用属于致命错误：直接终止启动，避免"服务看起来正常但数据没落库"
        logger.error("数据库初始化失败：%s", exc)
        logger.error(
            "请确认 MySQL 已启动，并检查 .env 中的 MYSQL_HOST / MYSQL_PORT / "
            "MYSQL_USER / MYSQL_PASSWORD / MYSQL_DATABASE 配置。"
        )
        raise

    info = db.health()
    logger.info(
        "数据库：MySQL %s:%s/%s（server %s）",
        info.get("host"),
        info.get("port"),
        info.get("database"),
        info.get("server_version"),
    )

    # 启动自检：确认关键表可读，且种子数据在位
    try:
        from dao.departments_dao import DepartmentsDao
        from dao.doctor_schedule_dao import DoctorScheduleDao
        from dao.user_dao import UserDao

        logger.info(
            "数据自检：科室 %s 个 / 医生排班 %s 条 / 用户 %s 个",
            len(DepartmentsDao.get_names(force=True)),
            DoctorScheduleDao.count(),
            UserDao.count(),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("数据自检失败：%s", exc)

    try:
        from rag.rag import MedRag

        stats = MedRag.stats()
        logger.info(
            "本地知识库：%s 篇文档 / %s 个知识块（检索后端 %s）",
            stats.get("documents"),
            stats.get("chunks"),
            stats.get("backend"),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("知识库加载失败：%s", exc)

    logger.info("大模型：%s（model=%s）", "已启用" if settings.llm_enabled() else "未启用", settings.LLM_MODEL)
    logger.info("服务已就绪：http://127.0.0.1:%s/docs", settings.PORT)
    yield


app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "互联网医疗智能分诊、问诊、用药、报告查询与预约挂号平台后端服务。\n\n"
        "核心链路：Router → Context → RAG ∥ Research → Reasoning → Formatter → Safety"
    ),
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# 跨域中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册所有路由
for router in api_routers:
    app.include_router(router)

# 注册全局异常处理
app.add_exception_handler(Exception, global_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)


if __name__ == "__main__":
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
